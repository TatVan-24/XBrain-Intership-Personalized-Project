#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Python
import os
import simplejson as json

# Postgres
import psycopg2

def must_map_env(key: str):
    value = os.environ.get(key)
    if value is None:
        raise Exception(f'{key} environment variable must be set')
    return value

# Retrieve Postgres environment variables
db_connection_str = must_map_env('DB_CONNECTION_STRING')

def fetch_product_reviews(product_id):
    try:
        return json.dumps(fetch_product_reviews_from_db(product_id), use_decimal=True)
    except Exception as e:
        return json.dumps({"error": str(e)})

def fetch_product_reviews_from_db(request_product_id):

    connection = None

    try:
        with psycopg2.connect(db_connection_str) as connection:

            with connection.cursor() as cursor:
                # Define the SQL query
                query = "SELECT username, description, score FROM reviews.productreviews WHERE product_id= %s AND deleted_at IS NULL ORDER BY created_at DESC"

                # Execute the query
                cursor.execute(query, (request_product_id, ))

                # Fetch all the rows from the query result
                records = cursor.fetchall()
                return records

    except Exception as e:
        raise e
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception as e:
                pass

def fetch_avg_product_review_score_from_db(request_product_id):

    connection = None

    try:
        with psycopg2.connect(db_connection_str) as connection:

            with connection.cursor() as cursor:
                # Define the SQL query
                query = "SELECT AVG(score) FROM reviews.productreviews WHERE product_id= %s AND deleted_at IS NULL"

                # Execute the query
                cursor.execute(query, (request_product_id, ))

                # Fetch all the rows from the query result
                records = cursor.fetchall()

                # Extract the average score
                if records:
                    # records will be a list like [(average_score,)]
                    average_score = records[0][0]
                else:
                    # Handle the case where no records are returned (e.g., no reviews for the product)
                    average_score = None

                # return the score as a string rounded to 1 decimal place
                return f"{average_score:.1f}" if average_score is not None else "0.0"

    except Exception as e:
        raise e
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

def create_product_review(product_id, user_id, username, description, score):
    with psycopg2.connect(db_connection_str) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO reviews.productreviews (product_id, user_id, username, description, score)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, product_id, user_id, username, description, score, created_at, updated_at""",
            (product_id, user_id, username, description, score),
        )
        return cursor.fetchone()

def list_product_reviews(product_id, limit=5, offset=0):
    with psycopg2.connect(db_connection_str) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT id, product_id, user_id, username, description, score, created_at, updated_at
               FROM reviews.productreviews WHERE product_id=%s AND deleted_at IS NULL
               ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s""",
            (product_id, limit, offset),
        )
        records = cursor.fetchall()
        cursor.execute(
            "SELECT count(*) FROM reviews.productreviews WHERE product_id=%s AND deleted_at IS NULL",
            (product_id,),
        )
        total = cursor.fetchone()[0]
        cursor.execute(
            """SELECT greatest(1, least(5, round(score)::int)) AS stars, count(*)
               FROM reviews.productreviews WHERE product_id=%s AND deleted_at IS NULL
               GROUP BY stars""",
            (product_id,),
        )
        distribution = [0, 0, 0, 0, 0]
        for stars, count in cursor.fetchall():
            distribution[stars - 1] = count
        return records, total, distribution

def update_product_review(review_id, user_id, description, score):
    with psycopg2.connect(db_connection_str) as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE reviews.productreviews SET description=%s, score=%s, updated_at=now()
               WHERE id=%s AND user_id=%s AND deleted_at IS NULL
               RETURNING id, product_id, user_id, username, description, score, created_at, updated_at""",
            (description, score, review_id, user_id),
        )
        return cursor.fetchone()

def delete_product_review(review_id, user_id):
    with psycopg2.connect(db_connection_str) as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE reviews.productreviews SET deleted_at=now(), updated_at=now()
               WHERE id=%s AND user_id=%s AND deleted_at IS NULL RETURNING id""",
            (review_id, user_id),
        )
        return cursor.fetchone() is not None
