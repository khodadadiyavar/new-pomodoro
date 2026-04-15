import os
import secrets
from dataclasses import dataclass
from pathlib import Path


PLACEHOLDER_SECRET_KEYS = {"", "change-me", "replace-me-with-a-long-random-secret"}


@dataclass(frozen=True)
class AppConfig:
    database_backend: str = "sqlite"
    database_path: str = "data/deepwork.db"
    secret_key: str = "change-me"
    personal_mode: bool = False
    secret_key_path: str = ""
    week_starts_on: str = "monday"
    focus_minutes: int = 25
    short_break_minutes: int = 5
    long_break_minutes: int = 15
    long_break_interval: int = 4
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_database: str = ""
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_maintenance_database: str = "postgres"
    postgres_sslmode: str = "prefer"

    @classmethod
    def from_env(cls):
        database_backend = os.environ.get("DEEPWORK_DB_BACKEND", "sqlite")
        database_path = os.environ.get("DEEPWORK_DB_PATH", "data/deepwork.db")
        personal_mode = os.environ.get("DEEPWORK_PERSONAL_MODE", "").strip() == "1"
        secret_key_path = ""
        if personal_mode and database_backend == "sqlite":
            secret_key_path = str(Path(database_path).resolve().parent / "deepwork-secret.key")
        raw_secret = os.environ.get("DEEPWORK_SECRET_KEY", "change-me").strip()
        secret_key = raw_secret

        if raw_secret in PLACEHOLDER_SECRET_KEYS:
            if personal_mode and database_backend == "sqlite":
                secret_key = _resolve_personal_secret(secret_key_path)
            else:
                raise ValueError(
                    "DEEPWORK_SECRET_KEY must be set unless DEEPWORK_PERSONAL_MODE=1 with sqlite."
                )

        return cls(
            database_backend=database_backend,
            database_path=database_path,
            secret_key=secret_key,
            personal_mode=personal_mode,
            secret_key_path=secret_key_path,
            week_starts_on=os.environ.get("DEEPWORK_WEEK_START", "monday"),
            focus_minutes=int(os.environ.get("DEEPWORK_FOCUS_MINUTES", "25")),
            short_break_minutes=int(os.environ.get("DEEPWORK_SHORT_BREAK_MINUTES", "5")),
            long_break_minutes=int(os.environ.get("DEEPWORK_LONG_BREAK_MINUTES", "15")),
            long_break_interval=int(os.environ.get("DEEPWORK_LONG_BREAK_INTERVAL", "4")),
            postgres_host=os.environ.get("DEEPWORK_POSTGRES_HOST", ""),
            postgres_port=int(os.environ.get("DEEPWORK_POSTGRES_PORT", "5432")),
            postgres_database=os.environ.get("DEEPWORK_POSTGRES_DATABASE", ""),
            postgres_user=os.environ.get("DEEPWORK_POSTGRES_USER", ""),
            postgres_password=os.environ.get("DEEPWORK_POSTGRES_PASSWORD", ""),
            postgres_maintenance_database=os.environ.get(
                "DEEPWORK_POSTGRES_MAINTENANCE_DATABASE", "postgres"
            ),
            postgres_sslmode=os.environ.get("DEEPWORK_POSTGRES_SSLMODE", "prefer"),
        )


def _resolve_personal_secret(secret_key_path: str) -> str:
    path = Path(secret_key_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()

    secret_key = secrets.token_urlsafe(48)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secret_key)
    return secret_key
