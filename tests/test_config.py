import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_explicit_secret_key_wins_over_personal_mode_secret_file(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            secret_file = data_dir / "deepwork-secret.key"
            secret_file.write_text("persisted-secret", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "DEEPWORK_DB_BACKEND": "sqlite",
                    "DEEPWORK_DB_PATH": str(data_dir / "deepwork.db"),
                    "DEEPWORK_PERSONAL_MODE": "1",
                    "DEEPWORK_SECRET_KEY": "explicit-secret",
                },
                clear=True,
            ):
                config = AppConfig.from_env()

            self.assertEqual(config.secret_key, "explicit-secret")
            self.assertTrue(config.personal_mode)
            self.assertEqual(Path(config.secret_key_path), secret_file.resolve())

    def test_personal_mode_generates_and_reuses_persisted_secret_file(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "DEEPWORK_DB_BACKEND": "sqlite",
                    "DEEPWORK_DB_PATH": str(data_dir / "deepwork.db"),
                    "DEEPWORK_PERSONAL_MODE": "1",
                },
                clear=True,
            ):
                first = AppConfig.from_env()
                second = AppConfig.from_env()

            secret_file = data_dir / "deepwork-secret.key"
            self.assertTrue(secret_file.exists())
            self.assertEqual(first.secret_key, second.secret_key)
            self.assertEqual(secret_file.read_text(encoding="utf-8").strip(), first.secret_key)

    def test_placeholder_secret_in_non_personal_mode_fails_closed(self):
        with TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "DEEPWORK_DB_BACKEND": "sqlite",
                    "DEEPWORK_DB_PATH": str(Path(temp_dir) / "deepwork.db"),
                    "DEEPWORK_SECRET_KEY": "change-me",
                },
                clear=True,
            ):
                with self.assertRaises(ValueError):
                    AppConfig.from_env()


if __name__ == "__main__":
    unittest.main()
