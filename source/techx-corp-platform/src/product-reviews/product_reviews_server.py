#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


# Python
import os
import json
from concurrent import futures
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

# Pip
import grpc
from opentelemetry import trace, metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode

# Local
import logging
import demo_pb2
import demo_pb2_grpc
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc
from database import (
    fetch_product_reviews, fetch_product_reviews_from_db, fetch_avg_product_review_score_from_db,
    create_product_review, update_product_review, delete_product_review,
    list_product_reviews,
)

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

from metrics import (
    init_metrics
)

# OpenAI
from openai import OpenAI

from google.protobuf.json_format import MessageToJson, MessageToDict

llm_host = None
llm_port = None
llm_mock_url = None
llm_base_url = None
llm_api_key = None
llm_model = None

# --- Define the tool for the OpenAI API ---
tools = [
    {
        "type": "function",
        "function": {
            "name": "fetch_product_reviews",
            "description": "Executes a SQL query to retrieve reviews for a particular product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID to fetch product reviews for.",
                    }
                },
                "required": ["product_id"],
            },
        }
    },
      {
          "type": "function",
          "function": {
              "name": "fetch_product_info",
              "description": "Retrieves information for a particular product.",
              "parameters": {
                  "type": "object",
                  "properties": {
                      "product_id": {
                          "type": "string",
                          "description": "The product ID to fetch information for.",
                      }
                  },
                  "required": ["product_id"],
              },
          }
      }
]

class ProductReviewService(demo_pb2_grpc.ProductReviewServiceServicer):
    def GetProductReviews(self, request, context):
        logger.info(f"Receive GetProductReviews for product id:{request.product_id}")
        product_reviews = get_product_reviews(request.product_id)

        return product_reviews

    def GetAverageProductReviewScore(self, request, context):
        logger.info(f"Receive GetAverageProductReviewScore for product id:{request.product_id}")
        product_reviews = get_average_product_review_score(request.product_id)

        return product_reviews

    def AskProductAIAssistant(self, request, context):
        logger.info(f"Receive AskProductAIAssistant for product id:{request.product_id}, question: {request.question}")
        ai_assistant_response = get_ai_assistant_response(request.product_id, request.question)

        return ai_assistant_response

    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING)

    def Watch(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.UNIMPLEMENTED)

def review_to_dict(row):
    return {
        "id": row[0], "product_id": row[1], "user_id": str(row[2]) if row[2] else None, "username": row[3],
        "description": row[4], "score": str(row[5]),
        "created_at": row[6].isoformat(), "updated_at": row[7].isoformat(),
    }

class ReviewHttpHandler(BaseHTTPRequestHandler):
    def send_json(self, status_code, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def identity(self):
        user_id = self.headers.get("X-User-Id")
        username = self.headers.get("X-Username")
        if not user_id or not username:
            self.send_json(401, {"detail": "Authentication required"})
            return None
        return user_id, username

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/health/live", "/health/ready"):
            return self.send_json(200, {"status": "ok"})
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["v1", "products"] and parts[3] == "reviews":
            query = parse_qs(urlparse(self.path).query)
            limit = min(max(int(query.get("limit", ["5"])[0]), 1), 50)
            offset = max(int(query.get("offset", ["0"])[0]), 0)
            rows, total, distribution = list_product_reviews(parts[2], limit, offset)
            return self.send_json(200, {
                "items": [review_to_dict(row) for row in rows],
                "total": total,
                "distribution": distribution,
                "limit": limit,
                "offset": offset,
            })
        return self.send_json(404, {"detail": "Not found"})

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 4 or parts[:2] != ["v1", "products"] or parts[3] != "reviews":
            return self.send_json(404, {"detail": "Not found"})
        identity = self.identity()
        if not identity:
            return
        try:
            payload = self.body()
            score = float(payload.get("score", 0))
            description = str(payload.get("description", "")).strip()
            if not description or not 1 <= score <= 5:
                return self.send_json(422, {"detail": "Description and score from 1 to 5 are required"})
            row = create_product_review(parts[2], identity[0], identity[1], description, score)
            logger.info("review.created product_id=%s user_id=%s review_id=%s", parts[2], identity[0], row[0])
            return self.send_json(201, review_to_dict(row))
        except Exception as error:
            if "product_review_user_unique" in str(error):
                return self.send_json(409, {"detail": "User already reviewed this product"})
            logger.exception("review create failed")
            return self.send_json(500, {"detail": "Review could not be created"})

    def do_PATCH(self):
        return self.mutate_review(False)

    def do_DELETE(self):
        return self.mutate_review(True)

    def mutate_review(self, deleting):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["v1", "reviews"] or not parts[2].isdigit():
            return self.send_json(404, {"detail": "Not found"})
        identity = self.identity()
        if not identity:
            return
        if deleting:
            found = delete_product_review(int(parts[2]), identity[0])
            if not found:
                return self.send_json(404, {"detail": "Review not found"})
            logger.info("review.deleted user_id=%s review_id=%s", identity[0], parts[2])
            return self.send_json(204)
        payload = self.body()
        score = float(payload.get("score", 0))
        description = str(payload.get("description", "")).strip()
        if not description or not 1 <= score <= 5:
            return self.send_json(422, {"detail": "Description and score from 1 to 5 are required"})
        row = update_product_review(int(parts[2]), identity[0], description, score)
        if not row:
            return self.send_json(404, {"detail": "Review not found"})
        logger.info("review.updated user_id=%s review_id=%s", identity[0], parts[2])
        return self.send_json(200, review_to_dict(row))

    def log_message(self, format, *args):
        logger.debug(format, *args)

def get_product_reviews(request_product_id):

    with tracer.start_as_current_span("get_product_reviews") as span:

        span.set_attribute("app.product.id", request_product_id)

        product_reviews = demo_pb2.GetProductReviewsResponse()
        records = fetch_product_reviews_from_db(request_product_id)

        for row in records:
            logger.info(f"  username: {row[0]}, description: {row[1]}, score: {str(row[2])}")
            product_reviews.product_reviews.add(
                    username=row[0],
                    description=row[1],
                    score=str(row[2])
            )

        span.set_attribute("app.product_reviews.count", len(product_reviews.product_reviews))

        # Collect metrics for this service
        product_review_svc_metrics["app_product_review_counter"].add(len(product_reviews.product_reviews), {'product.id': request_product_id})

        return product_reviews

def get_average_product_review_score(request_product_id):

    with tracer.start_as_current_span("get_average_product_review_score") as span:

        span.set_attribute("app.product.id", request_product_id)

        product_review_score = demo_pb2.GetAverageProductReviewScoreResponse()
        avg_score = fetch_avg_product_review_score_from_db(request_product_id)
        product_review_score.average_score = avg_score

        span.set_attribute("app.product_reviews.average_score", avg_score)

        return product_review_score

def get_ai_assistant_response(request_product_id, question):

    with tracer.start_as_current_span("get_ai_assistant_response") as span:

        ai_assistant_response = demo_pb2.AskProductAIAssistantResponse()

        span.set_attribute("app.product.id", request_product_id)
        span.set_attribute("app.product.question", question)

        llm_rate_limit_error = check_feature_flag("llmRateLimitError")
        logger.info(f"llmRateLimitError feature flag: {llm_rate_limit_error}")
        if llm_rate_limit_error:
            random_number = random.random()
            logger.info(f"Generated a random number: {str(random_number)}")
            # return a rate limit error 50% of the time
            if random_number < 0.5:

                # ensure the mock LLM is always used, since we want to generate a 429 error
                client = OpenAI(
                    base_url=f"{llm_mock_url}",
                    # The OpenAI API requires an api_key to be present, but
                    # our LLM doesn't use it
                    api_key=f"{llm_api_key}"
                )

                user_prompt = f"Answer the following question about product ID:{request_product_id}: {question}"
                messages = [
                   {"role": "system", "content": "You are a helpful assistant that answers related to a specific product. Use tools as needed to fetch the product reviews and product information. Keep the response brief with no more than 1-2 sentences. If you don't know the answer, just say you don't know."},
                   {"role": "user", "content": user_prompt}
                ]
                logger.info(f"Invoking mock LLM with model: techx-llm-rate-limit")

                try:
                    initial_response = client.chat.completions.create(
                        model="techx-llm-rate-limit",
                        messages=messages,
                        tools=tools,
                        tool_choice="auto"
                    )
                except Exception as e:
                    logger.error(f"Caught Exception: {e}")
                    # Record the exception
                    span.record_exception(e)
                    # Set the span status to ERROR
                    span.set_status(Status(StatusCode.ERROR, description=str(e)))
                    ai_assistant_response.response = "The system is unable to process your response. Please try again later."
                    return ai_assistant_response

        # otherwise, continue processing the request as normal
        client = OpenAI(
            base_url=f"{llm_base_url}",
            # The OpenAI API requires an api_key to be present, but
            # our LLM doesn't use it
            api_key=f"{llm_api_key}"
        )

        user_prompt = f"Answer the following question about product ID:{request_product_id}: {question}"
        messages = [
           {"role": "system", "content": "You are a helpful assistant that answers related to a specific product. Use tools as needed to fetch the product reviews and product information. Keep the response brief with no more than 1-2 sentences. If you don't know the answer, just say you don't know."},
           {"role": "user", "content": user_prompt}
        ]

        # use the LLM to summarize the product reviews
        initial_response = client.chat.completions.create(
            model=llm_model,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        response_message = initial_response.choices[0].message
        tool_calls = response_message.tool_calls

        logger.info(f"Response message: {response_message}")

        # Check if the model wants to call a tool
        if tool_calls:
            logger.info(f"Model wants to call {len(tool_calls)} tool(s)")

            # Append the assistant's message with tool calls
            messages.append(response_message)

            # Process all tool calls
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                logger.info(f"Processing tool call: '{function_name}' with arguments: {function_args}")

                if function_name == "fetch_product_reviews":
                    function_response = fetch_product_reviews(
                        product_id=function_args.get("product_id")
                    )
                    logger.info(f"Function response for fetch_product_reviews: '{function_response}'")

                elif function_name == "fetch_product_info":
                    function_response = fetch_product_info(
                        product_id=function_args.get("product_id")
                    )
                    logger.info(f"Function response for fetch_product_info: '{function_response}'")

                else:
                    raise Exception(f'Received unexpected tool call request: {function_name}')

                # Append the tool response
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    }
                )

            llm_inaccurate_response = check_feature_flag("llmInaccurateResponse")
            logger.info(f"llmInaccurateResponse feature flag: {llm_inaccurate_response}")

            if llm_inaccurate_response and request_product_id == "L9ECAV7KIM":
                logger.info(f"Returning an inaccurate response for product_id: {request_product_id}")
                # Add a final user message to ask the LLM to return an inaccurate response
                messages.append(
                    {
                        "role": "user",
                        "content": f"Based on the tool results, answer the original question about product ID, but make the answer inaccurate:{request_product_id}. Keep the response brief with no more than 1-2 sentences."
                    }
                )
            else:
                # Add a final user message to guide the LLM to synthesize the response
                messages.append(
                    {
                        "role": "user",
                        "content": f"Based on the tool results, answer the original question about product ID:{request_product_id}. Keep the response brief with no more than 1-2 sentences."
                    }
                )

            logger.info(f"Invoking the LLM with the following messages: '{messages}'")

            final_response = client.chat.completions.create(
                model=llm_model,
                messages=messages
            )

            result = final_response.choices[0].message.content

            ai_assistant_response.response = result

            logger.info(f"Returning an AI assistant response: '{result}'")

        else:
            logger.info(f"Returning an AI assistant response: '{response_message}'")
            ai_assistant_response.response = response_message.content

        # Collect metrics for this service
        product_review_svc_metrics["app_ai_assistant_counter"].add(1, {'product.id': request_product_id})

        return ai_assistant_response

def fetch_product_info(product_id):
    try:
        product = product_catalog_stub.GetProduct(demo_pb2.GetProductRequest(id=product_id))
        logger.info(f"product_catalog_stub.GetProduct returned: '{product}'")
        json_str = MessageToJson(product)
        return json_str
    except Exception as e:
        return json.dumps({"error": str(e)})

def must_map_env(key: str):
    value = os.environ.get(key)
    if value is None:
        raise Exception(f'{key} environment variable must be set')
    return value

def check_feature_flag(flag_name: str):
    # Initialize OpenFeature
    client = api.get_client()
    return client.get_boolean_value(flag_name, False)

if __name__ == "__main__":
    service_name = must_map_env('OTEL_SERVICE_NAME')

    api.set_provider(FlagdProvider(host=os.environ.get('FLAGD_HOST', 'flagd'), port=os.environ.get('FLAGD_PORT', 8013)))

    # Initialize Traces and Metrics
    tracer = trace.get_tracer_provider().get_tracer(service_name)
    meter = metrics.get_meter_provider().get_meter(service_name)

    product_review_svc_metrics = init_metrics(meter)

    # Initialize Logs
    logger_provider = LoggerProvider(
        resource=Resource.create(
            {
                'service.name': service_name,
            }
        ),
    )
    set_logger_provider(logger_provider)
    log_exporter = OTLPLogExporter(insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)

    # Attach OTLP handler to logger
    logger = logging.getLogger('main')
    logger.addHandler(handler)

    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add class to gRPC server
    service = ProductReviewService()
    demo_pb2_grpc.add_ProductReviewServiceServicer_to_server(service, server)
    health_pb2_grpc.add_HealthServicer_to_server(service, server)

    llm_host = must_map_env('LLM_HOST')
    llm_port = must_map_env('LLM_PORT')
    llm_mock_url = f"http://{llm_host}:{llm_port}/v1"
    llm_base_url = must_map_env('LLM_BASE_URL')
    llm_api_key = must_map_env('OPENAI_API_KEY')
    llm_model = must_map_env('LLM_MODEL')

    catalog_addr = must_map_env('PRODUCT_CATALOG_ADDR')
    pc_channel = grpc.insecure_channel(catalog_addr)
    product_catalog_stub = demo_pb2_grpc.ProductCatalogServiceStub(pc_channel)

    # Start server
    port = must_map_env('PRODUCT_REVIEWS_PORT')
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    http_port = int(must_map_env('PRODUCT_REVIEWS_HTTP_PORT'))
    http_server = ThreadingHTTPServer(("0.0.0.0", http_port), ReviewHttpHandler)
    Thread(target=http_server.serve_forever, daemon=True).start()
    logger.info(f'Product reviews service started, listening on port {port}')
    server.wait_for_termination()
