import unittest
from unittest.mock import patch

import serve


VALID_PAYLOAD = {
    "product_id": "P123",
    "review_version": "v42",
    "reviews": [
        {
            "review_id": "r1",
            "score": 5.0,
            "text": (
                "Image quality is sharp and setup is straightforward."
            ),
        },
        {
            "review_id": "r2",
            "score": 3.0,
            "text": "Documentation needs improvement.",
        },
    ],
}


class ServeIntegrationTests(unittest.TestCase):
    def setUp(self):
        serve.app.config["TESTING"] = True
        self.client = serve.app.test_client()

    def test_clean_candidate_returns_completed(self):
        with (
            patch.object(serve, "load_model"),
            patch.object(serve, "_model", object()),
            patch.object(
                serve,
                "generate_candidate",
                return_value=(
                    "Reviewers praise the sharp images and straightforward "
                    "setup, while documentation could be improved."
                ),
            ),
        ):
            response = self.client.post(
                "/v1/summaries",
                json=VALID_PAYLOAD,
            )

        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "completed")
        self.assertIsInstance(data["summary"], str)
        self.assertEqual(data["validation_codes"], [])

    def test_format_leak_returns_safe_abstention(self):
        with (
            patch.object(serve, "load_model"),
            patch.object(serve, "_model", object()),
            patch.object(
                serve,
                "generate_candidate",
                return_value=(
                    "rating=5 | review=Image quality is sharp."
                ),
            ),
        ):
            response = self.client.post(
                "/v1/summaries",
                json=VALID_PAYLOAD,
            )

        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "unavailable")
        self.assertIsNone(data["summary"])
        self.assertEqual(data["source_review_ids"], [])
        self.assertIn(
            "MODEL_FORMAT_LEAK",
            data["validation_codes"],
        )

    def test_invalid_request_returns_422(self):
        response = self.client.post(
            "/v1/summaries",
            json={
                "product_id": "P123",
                "review_version": "v42",
                "reviews": "not-a-list",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.get_json()["error"],
            "invalid_request",
        )

    def test_model_unavailable_returns_503(self):
        with (
            patch.object(serve, "load_model"),
            patch.object(serve, "_model", None),
            patch.object(serve, "_load_error", "ModelLoadError"),
        ):
            response = self.client.post(
                "/v1/summaries",
                json=VALID_PAYLOAD,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "fallback_model_unavailable",
        )

    def test_ready_hides_internal_model_path(self):
        config = serve.ModelConfig(
            model_type="base",
            model_path="google-t5/t5-small",
            model_version="untuned-v1",
        )

        with (
            patch.object(serve, "load_model"),
            patch.object(serve, "_model", object()),
            patch.object(serve, "_model_config", config),
            patch.object(serve, "_device", "cuda"),
        ):
            response = self.client.get("/health/ready")

        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["model_type"], "base")
        self.assertEqual(data["model_version"], "untuned-v1")
        self.assertEqual(data["device"], "cuda")
        self.assertNotIn("model_path", data)


if __name__ == "__main__":
    unittest.main()