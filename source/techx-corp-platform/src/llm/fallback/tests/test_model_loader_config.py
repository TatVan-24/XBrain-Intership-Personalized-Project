import os
import unittest
from unittest.mock import patch

from serve import (
    ModelConfigurationError,
    read_model_config,
)


class ModelLoaderConfigTests(unittest.TestCase):
    def test_reads_base_model_environment(self):
        with patch.dict(
            os.environ,
            {
                "FALLBACK_MODEL_TYPE": "base",
                "FALLBACK_MODEL_PATH": "google-t5/t5-small",
                "FALLBACK_MODEL_VERSION": "untuned-v1",
            },
            clear=True,
        ):
            config = read_model_config()

        self.assertEqual(config.model_type, "base")
        self.assertEqual(
            config.model_path,
            "google-t5/t5-small",
        )
        self.assertEqual(
            config.model_version,
            "untuned-v1",
        )

    def test_reads_peft_model_environment(self):
        with patch.dict(
            os.environ,
            {
                "FALLBACK_MODEL_TYPE": "peft",
                "FALLBACK_MODEL_PATH": "./artifacts/adapter-v1",
                "FALLBACK_MODEL_VERSION": "adapter-v1",
            },
            clear=True,
        ):
            config = read_model_config()

        self.assertEqual(config.model_type, "peft")
        self.assertEqual(
            config.model_path,
            "./artifacts/adapter-v1",
        )

    def test_rejects_unknown_model_type(self):
        with patch.dict(
            os.environ,
            {
                "FALLBACK_MODEL_TYPE": "unknown",
            },
            clear=True,
        ):
            with self.assertRaises(
                ModelConfigurationError
            ):
                read_model_config()

    def test_rejects_empty_model_path(self):
        with patch.dict(
            os.environ,
            {
                "FALLBACK_MODEL_TYPE": "base",
                "FALLBACK_MODEL_PATH": "",
            },
            clear=True,
        ):
            with self.assertRaises(
                ModelConfigurationError
            ):
                read_model_config()


if __name__ == "__main__":
    unittest.main()