import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.config import AppConfig
from app.db import init_db
from app.services import DeepWorkService


class FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)


class FakePostgresConnection:
    def __init__(self, rows_by_sql=None):
        self.rows_by_sql = rows_by_sql or {}
        self.executed = []
        self.autocommit = False

    def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        self.executed.append((statement, params))
        return FakeCursor(self.rows_by_sql.get(statement, []))

    def executescript(self, script):
        for statement in script.split(";"):
            trimmed = " ".join(statement.split())
            if trimmed:
                self.executed.append((trimmed, None))
        return None

    def commit(self):
        return None

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DatabaseInitializationTests(unittest.TestCase):
    def test_sqlite_init_is_idempotent_and_preserves_existing_data(self):
        with TemporaryDirectory() as temp_dir:
            config = AppConfig(
                database_backend="sqlite",
                database_path=str(Path(temp_dir) / "deepwork.db"),
                secret_key="test-secret",
            )
            service = DeepWorkService(config)

            service.init_db()
            user = service.bootstrap_admin("admin@example.com", "password")
            service.create_goal(user["id"], "Existing goal", "keep me")

            service.init_db()
            reloaded = DeepWorkService(config)

            self.assertEqual(reloaded.count_users(), 1)
            self.assertEqual(len(reloaded.list_goals(user["id"])), 1)

    def test_postgres_init_creates_database_when_missing_then_applies_schema(self):
        config = AppConfig(
            database_backend="postgres",
            secret_key="test-secret",
            postgres_host="db.example.internal",
            postgres_port=5432,
            postgres_database="deepwork",
            postgres_user="deepwork",
            postgres_password="password",
            postgres_maintenance_database="postgres",
        )
        admin_connection = FakePostgresConnection(
            rows_by_sql={
                "SELECT 1 FROM pg_database WHERE datname = ?": [],
            }
        )
        app_connection = FakePostgresConnection()

        with patch("app.db._connect_postgres", side_effect=[admin_connection, app_connection]):
            init_db(config)

        self.assertIn(('SELECT 1 FROM pg_database WHERE datname = ?', ('deepwork',)), admin_connection.executed)
        self.assertIn(('CREATE DATABASE "deepwork"', None), admin_connection.executed)
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS users" in sql for sql, _ in app_connection.executed))

    def test_postgres_init_reuses_existing_database_without_create(self):
        config = AppConfig(
            database_backend="postgres",
            secret_key="test-secret",
            postgres_host="db.example.internal",
            postgres_port=5432,
            postgres_database="deepwork",
            postgres_user="deepwork",
            postgres_password="password",
            postgres_maintenance_database="postgres",
        )
        admin_connection = FakePostgresConnection(
            rows_by_sql={
                "SELECT 1 FROM pg_database WHERE datname = ?": [{"?column?": 1}],
            }
        )
        app_connection = FakePostgresConnection()

        with patch("app.db._connect_postgres", side_effect=[admin_connection, app_connection]):
            init_db(config)

        self.assertNotIn(('CREATE DATABASE "deepwork"', None), admin_connection.executed)
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS users" in sql for sql, _ in app_connection.executed))


if __name__ == "__main__":
    unittest.main()
