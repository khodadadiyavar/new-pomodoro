import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    database_backend: str = "sqlite"
    database_path: str = "data/deepwork.db"
    secret_key: str = "change-me"
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
        return cls(
            database_backend=os.environ.get("DEEPWORK_DB_BACKEND", "sqlite"),
            database_path=os.environ.get("DEEPWORK_DB_PATH", "data/deepwork.db"),
            secret_key=os.environ.get("DEEPWORK_SECRET_KEY", "change-me"),
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
