import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field


DATABASE_URL = os.environ["DB_CONNECTION_STRING"]
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "168"))
password_hasher = PasswordHasher()
app = FastAPI(title="User Service", version="1.0.0")


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def emit_event(event_type: str, user_id: UUID | None, request: Request, metadata: dict | None = None) -> None:
    event = {
        "event_type": event_type,
        "user_id": str(user_id) if user_id else None,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": request.headers.get("traceparent"),
        "metadata": metadata or {},
    }
    print(json.dumps(event, separators=(",", ":")), flush=True)


def serialize_user(row) -> dict:
    return {
        "id": str(row[0]),
        "email": row[1],
        "username": row[2],
        "status": row[3],
        "created_at": row[4].isoformat(),
        "updated_at": row[5].isoformat(),
    }


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return authorization[7:]


def current_user(token: Annotated[str, Depends(bearer_token)]):
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT u.id, u.email, u.username, u.status, u.created_at, u.updated_at, s.id
            FROM identity.sessions s
            JOIN identity.users u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now()
              AND u.status = 'active'
            """,
            (token_hash(token),),
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired")
    return row


@app.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict:
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ready"}
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error


@app.post("/v1/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request) -> dict:
    try:
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO identity.users (email, username, password_hash)
                VALUES (lower(%s), %s, %s)
                RETURNING id, email, username, status, created_at, updated_at
                """,
                (str(payload.email), payload.username, password_hasher.hash(payload.password)),
            )
            row = cursor.fetchone()
    except psycopg.errors.UniqueViolation as error:
        raise HTTPException(status_code=409, detail="Email or username already exists") from error
    emit_event("user.registered", row[0], request)
    return serialize_user(row)


@app.post("/v1/auth/login")
def login(payload: LoginRequest, request: Request) -> dict:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, email, username, status, created_at, updated_at, password_hash FROM identity.users WHERE email = lower(%s)",
            (str(payload.email),),
        )
        row = cursor.fetchone()
        if not row or row[3] != "active":
            raise HTTPException(status_code=401, detail="Invalid credentials")
        try:
            password_hasher.verify(row[6], payload.password)
        except VerifyMismatchError as error:
            raise HTTPException(status_code=401, detail="Invalid credentials") from error
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        cursor.execute(
            "INSERT INTO identity.sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
            (row[0], token_hash(token), expires_at),
        )
    emit_event("user.logged_in", row[0], request)
    return {"access_token": token, "token_type": "bearer", "expires_at": expires_at.isoformat(), "user": serialize_user(row)}


@app.post("/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, user=Depends(current_user), token: str = Depends(bearer_token)) -> Response:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE identity.sessions SET revoked_at = now() WHERE token_hash = %s", (token_hash(token),))
    emit_event("user.logged_out", user[0], request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/v1/users/me")
def me(user=Depends(current_user)) -> dict:
    return serialize_user(user)


@app.patch("/v1/users/me")
def update_me(payload: UpdateUserRequest, request: Request, user=Depends(current_user)) -> dict:
    if payload.username is None:
        return serialize_user(user)
    try:
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE identity.users SET username = %s, updated_at = now() WHERE id = %s RETURNING id, email, username, status, created_at, updated_at",
                (payload.username, user[0]),
            )
            row = cursor.fetchone()
    except psycopg.errors.UniqueViolation as error:
        raise HTTPException(status_code=409, detail="Username already exists") from error
    emit_event("user.profile_updated", user[0], request, {"fields": ["username"]})
    return serialize_user(row)


@app.delete("/v1/users/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(request: Request, user=Depends(current_user)) -> Response:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE identity.users SET status = 'deleted', deleted_at = now(), updated_at = now() WHERE id = %s", (user[0],))
        cursor.execute("UPDATE identity.sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (user[0],))
    emit_event("user.deleted", user[0], request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
