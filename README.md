# Deep Work 4DX

A self-hosted web app for private deep-work execution and weekly 4DX-style accountability.

## What it includes

- local account auth with admin bootstrap
- private multi-user data isolation on one server
- goal tracking with milestones and notes
- in-app focus timer with automatic session logging
- weekly target-hour commitments and review workflow
- lightweight history view

## Run locally

```bash
python3 run.py
```

Then open `http://127.0.0.1:8000`.

## Run with Docker Compose

```bash
docker compose up --build
```

The default Compose setup uses SQLite, listens on port `8000`, and stores data in the `deepwork_data` volume.
Set `DEEPWORK_SECRET_KEY` in your shell or an env file before starting Compose.
To switch to PostgreSQL, set `DEEPWORK_DB_BACKEND=postgres` and fill in the `DEEPWORK_POSTGRES_*` variables before startup.

## Run on Kubernetes

Apply the bundled manifest:

```bash
kubectl apply -f deploy/kubernetes.yaml
```

Before applying it in a real cluster, replace the placeholder value for `DEEPWORK_SECRET_KEY` in the `Secret` object.
For PostgreSQL-backed deployments, switch `DEEPWORK_DB_BACKEND` to `postgres` and provide the `DEEPWORK_POSTGRES_*` values in the ConfigMap and Secret.

## Environment variables

- `DEEPWORK_DB_BACKEND` (`sqlite` or `postgres`)
- `HOST`
- `PORT`
- `DEEPWORK_DB_PATH`
- `DEEPWORK_SECRET_KEY`
- `DEEPWORK_WEEK_START`
- `DEEPWORK_FOCUS_MINUTES`
- `DEEPWORK_SHORT_BREAK_MINUTES`
- `DEEPWORK_LONG_BREAK_MINUTES`
- `DEEPWORK_LONG_BREAK_INTERVAL`
- `DEEPWORK_POSTGRES_HOST`
- `DEEPWORK_POSTGRES_PORT`
- `DEEPWORK_POSTGRES_DATABASE`
- `DEEPWORK_POSTGRES_USER`
- `DEEPWORK_POSTGRES_PASSWORD`
- `DEEPWORK_POSTGRES_MAINTENANCE_DATABASE`
- `DEEPWORK_POSTGRES_SSLMODE`

## Database initialization behavior

- SQLite: the app creates the database file and schema if missing, and reuses existing data if the file is already initialized.
- PostgreSQL: the app connects with the provided credentials, creates the target database if it does not exist yet, then applies the schema idempotently.
- Existing data is never dropped automatically during startup.

## Tests

```bash
python3 -m unittest discover -s tests
```
