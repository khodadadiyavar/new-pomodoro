# Deep Work 4DX

> A self-hosted deep-work operating system for private execution, weekly accountability, and goal-centered focus.

<p align="center">
  <img src="docs/assets/readme-preview.svg" alt="Deep Work 4DX preview showing dashboard, focus timer, and weekly review" width="1200" />
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#database-modes">Database Modes</a> ·
  <a href="#kubernetes">Kubernetes</a> ·
  <a href="#configuration-reference">Configuration</a> ·
  <a href="#development">Development</a>
</p>

Deep Work 4DX is a web app for people who want more than a timer and less than a bloated productivity suite. It gives each user a private workspace where they can define meaningful goals, run focused sessions, capture milestones and notes, and review the week through a 4DX-style scoreboard.

The project is designed for two very different deployment styles:

- `SQLite` for a fast, low-friction personal or small-server setup
- `PostgreSQL` for a more production-oriented deployment with explicit database credentials and server-managed persistence

## Visual Preview

The README artwork is a repo-local SVG composition based on the current product shape: a weekly scoreboard dashboard, an in-app focus timer, and a structured weekly review flow. It is meant to give the project a stronger landing page while staying aligned with the real UI model in the codebase.

## Why This Exists

Most tools are good at storing tasks and bad at shaping attention.

Deep Work 4DX is built around a tighter loop:

1. choose a few goals that matter this week
2. commit target hours
3. run focused sessions against those goals
4. record milestones and notes as progress happens
5. review target versus actual performance at week end

That means the app is intentionally opinionated:

- goals are first-class
- weekly commitments are measured in hours
- focus sessions belong to a goal
- milestones stay append-only
- user data is private by default even on a shared installation

## What It Does

| Area | Current capability |
| --- | --- |
| Authentication | Local email/password accounts with bootstrap admin creation |
| Multi-user | Multiple users on one installation, isolated private data |
| Goals | Create goals, track status, attach milestones and notes |
| Focus | Run in-app focus sessions with timer-driven logging |
| Weekly review | Set target hours, review actual progress, carry forward notes |
| History | View weekly totals and milestone activity |
| Deployment | Local Python run, Docker Compose, Kubernetes manifest |
| Persistence | SQLite quick-start or PostgreSQL-backed startup |

## Product Shape

This is not a generic task manager.

It is a focused system built around:

- `Dashboard` for current-week scoreboard and recent progress
- `Goals` for the long-lived work that matters
- `Focus` for starting and completing deep-work sessions
- `Weekly Review` for commitment, review, and planning
- `History` for lightweight trend visibility

## Architecture

```mermaid
flowchart LR
    Browser["Browser UI"] --> App["Deep Work 4DX App (WSGI)"]
    App --> Auth["Auth + Session Handling"]
    App --> Domain["Goals / Sessions / Weekly Review"]
    Domain --> DB["SQLite or PostgreSQL"]
    App --> Static["Server-rendered HTML + CSS + JS"]
```

### Runtime characteristics

- server-rendered web app with lightweight JavaScript for the focus timer
- one application process
- one persistence backend selected by configuration
- idempotent startup initialization
- no destructive schema reset on boot

## Quick Start

### Local Python

```bash
python3 run.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Docker Compose

```bash
docker compose up --build
```

The default Compose setup uses:

- `SQLite`
- port `8000`
- a named volume for `/data`

Before starting Compose, provide `DEEPWORK_SECRET_KEY` from your shell or env file.

## Database Modes

### SQLite mode

SQLite is the default path and is intended for quick setup.

Use:

- `DEEPWORK_DB_BACKEND=sqlite`
- `DEEPWORK_DB_PATH=/data/deepwork.db`

Startup behavior:

- creates the database file if it does not exist
- creates the schema if it is missing
- reuses existing data if the file is already initialized

### PostgreSQL mode

PostgreSQL is the production-grade option.

Use:

- `DEEPWORK_DB_BACKEND=postgres`
- `DEEPWORK_POSTGRES_HOST`
- `DEEPWORK_POSTGRES_PORT`
- `DEEPWORK_POSTGRES_DATABASE`
- `DEEPWORK_POSTGRES_USER`
- `DEEPWORK_POSTGRES_PASSWORD`
- `DEEPWORK_POSTGRES_MAINTENANCE_DATABASE`
- `DEEPWORK_POSTGRES_SSLMODE`

Startup behavior:

- connects to PostgreSQL using the configured credentials
- checks whether the target application database exists
- creates that database if it does not exist yet
- applies the schema idempotently
- never drops existing application data automatically

This assumes the configured credentials are allowed to create the target database on first startup, or that the database is pre-created by the operator.

## Kubernetes

A single-file Kubernetes manifest is included at:

```bash
deploy/kubernetes.yaml
```

Apply it with:

```bash
kubectl apply -f deploy/kubernetes.yaml
```

Before using it in a real cluster:

1. replace the placeholder `DEEPWORK_SECRET_KEY`
2. set the image name/tag you actually publish
3. decide whether the deployment should run on `sqlite` or `postgres`
4. if using PostgreSQL, fill in the `DEEPWORK_POSTGRES_*` settings and secret values

## Configuration Reference

| Variable | Purpose |
| --- | --- |
| `HOST` | Bind host for the app server |
| `PORT` | Bind port for the app server |
| `DEEPWORK_SECRET_KEY` | Cookie/session signing secret |
| `DEEPWORK_WEEK_START` | Week boundary used for reviews and scoreboards |
| `DEEPWORK_FOCUS_MINUTES` | Default focus session duration |
| `DEEPWORK_SHORT_BREAK_MINUTES` | Default short break duration |
| `DEEPWORK_LONG_BREAK_MINUTES` | Default long break duration |
| `DEEPWORK_LONG_BREAK_INTERVAL` | Cycles before long break suggestion |
| `DEEPWORK_DB_BACKEND` | `sqlite` or `postgres` |
| `DEEPWORK_DB_PATH` | SQLite database path |
| `DEEPWORK_POSTGRES_HOST` | PostgreSQL host |
| `DEEPWORK_POSTGRES_PORT` | PostgreSQL port |
| `DEEPWORK_POSTGRES_DATABASE` | Target application database |
| `DEEPWORK_POSTGRES_USER` | PostgreSQL user |
| `DEEPWORK_POSTGRES_PASSWORD` | PostgreSQL password |
| `DEEPWORK_POSTGRES_MAINTENANCE_DATABASE` | Database used for first-run existence checks and bootstrap |
| `DEEPWORK_POSTGRES_SSLMODE` | PostgreSQL SSL mode |

## Development

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run tests

```bash
python3 -m unittest discover -s tests
```

### Current stack

- Python application runtime
- WSGI server via the standard library runner
- SQLite or PostgreSQL persistence
- server-rendered HTML
- custom CSS and small client-side JavaScript for timer behavior

## Project Status

The project already includes:

- local auth and admin bootstrap
- private multi-user isolation
- goal tracking with milestones and notes
- focus session lifecycle handling
- weekly review and scoreboard flows
- SQLite and PostgreSQL startup paths
- Docker and Kubernetes packaging

The project does not yet include:

- external identity providers
- background job workers
- collaborative/team visibility
- a mobile app
- full production hardening around migrations, observability, and CI
