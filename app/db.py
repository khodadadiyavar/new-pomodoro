import sqlite3
from pathlib import Path

from app.config import AppConfig


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS weekly_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    reflection TEXT NOT NULL DEFAULT '',
    next_week_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    finalized_at TEXT,
    UNIQUE(user_id, week_start)
);

CREATE TABLE IF NOT EXISTS weekly_goal_commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weekly_review_id INTEGER NOT NULL REFERENCES weekly_reviews(id) ON DELETE CASCADE,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    target_minutes INTEGER NOT NULL,
    carry_forward_status TEXT NOT NULL DEFAULT 'keep-active',
    reflection TEXT NOT NULL DEFAULT '',
    UNIQUE(weekly_review_id, goal_id)
);

CREATE TABLE IF NOT EXISTS focus_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    planned_minutes INTEGER NOT NULL,
    actual_minutes INTEGER NOT NULL DEFAULT 0,
    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    last_state_change_at TEXT NOT NULL,
    ended_at TEXT,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goal_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS weekly_reviews (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    reflection TEXT NOT NULL DEFAULT '',
    next_week_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    finalized_at TEXT,
    UNIQUE(user_id, week_start)
);

CREATE TABLE IF NOT EXISTS weekly_goal_commitments (
    id BIGSERIAL PRIMARY KEY,
    weekly_review_id BIGINT NOT NULL REFERENCES weekly_reviews(id) ON DELETE CASCADE,
    goal_id BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    target_minutes INTEGER NOT NULL,
    carry_forward_status TEXT NOT NULL DEFAULT 'keep-active',
    reflection TEXT NOT NULL DEFAULT '',
    UNIQUE(weekly_review_id, goal_id)
);

CREATE TABLE IF NOT EXISTS focus_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    planned_minutes INTEGER NOT NULL,
    actual_minutes INTEGER NOT NULL DEFAULT 0,
    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    last_state_change_at TEXT NOT NULL,
    ended_at TEXT,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS milestones (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goal_notes (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _load_psycopg():
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError(
            "PostgreSQL support requires the 'psycopg' package to be installed."
        ) from error
    return psycopg


def _translate_placeholders(sql: str, backend: str) -> str:
    if backend == "postgres":
        return sql.replace("?", "%s")
    return sql


def _split_script(script: str):
    statements = []
    for statement in script.split(";"):
        trimmed = statement.strip()
        if trimmed:
            statements.append(trimmed)
    return statements


class CompatConnection:
    def __init__(self, connection, backend: str):
        self.connection = connection
        self.backend = backend

    def execute(self, sql: str, params=None):
        adapted = _translate_placeholders(sql, self.backend)
        if params is None:
            return self.connection.execute(adapted)
        return self.connection.execute(adapted, params)

    def executescript(self, script: str):
        if self.backend == "sqlite":
            return self.connection.executescript(script)
        last_cursor = None
        for statement in _split_script(script):
            last_cursor = self.connection.execute(statement)
        return last_cursor

    def commit(self):
        return self.connection.commit()

    def close(self):
        return self.connection.close()

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.connection.__exit__(exc_type, exc, tb)


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _require_postgres_setting(config: AppConfig, attr_name: str, env_name: str):
    value = getattr(config, attr_name)
    if value in {None, ""}:
        raise ValueError(f"{env_name} must be set when using the postgres backend.")
    return value


def _connect_sqlite(database_path: str) -> CompatConnection:
    if database_path != ":memory:":
        db_path = Path(database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return CompatConnection(connection, "sqlite")


def _connect_postgres(
    config: AppConfig,
    database_name: str = "",
    autocommit: bool = False,
) -> CompatConnection:
    psycopg = _load_psycopg()
    connection = psycopg.connect(
        host=_require_postgres_setting(config, "postgres_host", "DEEPWORK_POSTGRES_HOST"),
        port=config.postgres_port,
        dbname=database_name
        or _require_postgres_setting(
            config, "postgres_database", "DEEPWORK_POSTGRES_DATABASE"
        ),
        user=_require_postgres_setting(config, "postgres_user", "DEEPWORK_POSTGRES_USER"),
        password=_require_postgres_setting(
            config, "postgres_password", "DEEPWORK_POSTGRES_PASSWORD"
        ),
        sslmode=config.postgres_sslmode,
        row_factory=psycopg.rows.dict_row,
    )
    connection.autocommit = autocommit
    return CompatConnection(connection, "postgres")


def connect(
    config: AppConfig,
    database_name: str = "",
    autocommit: bool = False,
):
    if config.database_backend == "postgres":
        return _connect_postgres(config, database_name=database_name, autocommit=autocommit)
    return _connect_sqlite(config.database_path)


def _init_sqlite(config: AppConfig):
    with connect(config) as connection:
        connection.executescript(SQLITE_SCHEMA)


def _init_postgres(config: AppConfig):
    target_database = _require_postgres_setting(
        config, "postgres_database", "DEEPWORK_POSTGRES_DATABASE"
    )
    maintenance_database = config.postgres_maintenance_database or "postgres"

    with _connect_postgres(
        config,
        database_name=maintenance_database,
        autocommit=True,
    ) as admin_connection:
        exists = admin_connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = ?",
            (target_database,),
        ).fetchone()
        if not exists:
            admin_connection.execute(f"CREATE DATABASE {_quote_identifier(target_database)}")

    with _connect_postgres(config, database_name=target_database) as app_connection:
        app_connection.executescript(POSTGRES_SCHEMA)


def init_db(config: AppConfig):
    if config.database_backend == "postgres":
        _init_postgres(config)
        return
    _init_sqlite(config)
