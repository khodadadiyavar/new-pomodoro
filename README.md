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

The app listens on port `8000` and stores SQLite data in the `deepwork_data` volume.
Set `DEEPWORK_SECRET_KEY` in your shell or an env file before starting Compose.

## Run on Kubernetes

Apply the bundled manifest:

```bash
kubectl apply -f deploy/kubernetes.yaml
```

Before applying it in a real cluster, replace the placeholder value for `DEEPWORK_SECRET_KEY` in the `Secret` object.

## Environment variables

- `HOST`
- `PORT`
- `DEEPWORK_DB_PATH`
- `DEEPWORK_SECRET_KEY`
- `DEEPWORK_WEEK_START`
- `DEEPWORK_FOCUS_MINUTES`
- `DEEPWORK_SHORT_BREAK_MINUTES`
- `DEEPWORK_LONG_BREAK_MINUTES`
- `DEEPWORK_LONG_BREAK_INTERVAL`

## Tests

```bash
python3 -m unittest discover -s tests
```
