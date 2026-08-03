FROM docker.io/library/python:3.12-alpine3.22

WORKDIR /app

COPY ./src/user-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/user-service/main.py main.py

EXPOSE ${USER_SERVICE_PORT}
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8082"]

