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

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
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

## Docker

```bash
docker compose up --build
```

The web app runs on port `8000`; PostgreSQL runs on port `5432`.

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
