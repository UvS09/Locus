# Locus

Locus is an internal HMSI work management application for tracking projects, milestones, activities, and tasks across teams. It gives administrators control over users, teams, and roles; managers visibility into team delivery and employee analytics; and employees a focused workspace for assigned and created work.

## What It Does

- Admin dashboard for users, custom roles, teams, audit logs, and portfolio reporting.
- Manager dashboard for project progress, blocked/overdue work, recent updates, and employee analytics.
- Employee dashboard for personal work tracking and status snapshots.
- Project hierarchy: Project -> Milestone -> Activity -> Task.
- Automatic owner assignment: the creator becomes the owner.
- Recursive progress tracking from tasks up to activities, milestones, and projects.
- Blocked work keeps its last progress percentage and is visually struck off.
- Notifications, comments, audit history, and Excel export for manager reports.

## Tech Stack

- Backend: FastAPI
- Templates/UI: Jinja2, Bootstrap, custom CSS
- Database: SQLAlchemy ORM with SQLite for local development and PostgreSQL for production
- Auth: JWT stored in HTTP-only cookies
- Config: Pydantic Settings with `.env`
- Tests: Pytest and FastAPI TestClient
- Deployment: Uvicorn, Docker, Docker Compose

## Local Setup

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

### Windows Command Prompt

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

## First Admin

In local development, use the signup page to create the first administrator if no users exist:

```text
http://127.0.0.1:8000/signup
```

After the first admin exists, user creation is handled from the Admin dashboard.

## Running Tests

```bash
.venv/bin/python -m pytest -q
```

On Windows PowerShell:

```powershell
.venv\Scripts\python -m pytest -q
```

## Docker

```bash
docker compose up --build
```

The web app runs on port `8000`; PostgreSQL runs on port `5432`.

## Deploying to Vercel

This repository supports both local `uvicorn` usage and Vercel deployment from the same FastAPI app.

Set these environment variables in Vercel:

```text
APP_ENV=production
APP_DEBUG=false
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
SECRET_KEY=replace-with-a-long-random-secret
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
INIT_DB_ON_STARTUP=true
```

Notes:

- Use a managed PostgreSQL database. Do not use local SQLite on Vercel.
- The Vercel entrypoint is `api/index.py`, which imports the same `app` object used by `uvicorn app.main:app`.
- Static files and templates are loaded with absolute paths so they work in both environments.
- Keep `INIT_DB_ON_STARTUP=true` if you want the app to create tables and run seed logic during cold starts. If you later switch fully to Alembic-managed migrations, you can set it to `false`.

## Key Files

- `app/main.py` - FastAPI app factory and router registration.
- `app/config.py` - environment-driven settings.
- `app/database.py` - SQLAlchemy engine/session/database initialization.
- `app/models/` - database tables and relationships.
- `app/routes/` - HTTP endpoints and template rendering.
- `app/services/` - business rules, authorization checks, reporting, notifications, and audit logic.
- `app/repositories/` - database query helpers.
- `app/templates/` - Jinja2 pages.
- `app/static/` - CSS, JavaScript, and image assets.
- `SYSTEM_DESIGN.md` - architecture and design overview.
- `docs/DATA_FLOW.md` - end-to-end explanation of how data and control move through the app.
