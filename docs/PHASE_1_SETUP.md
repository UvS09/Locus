# Phase 1: Environment Setup and First FastAPI App

## 1. Goal of this phase

Create the first runnable project skeleton with:

- package structure
- dependency manifest
- environment sample
- first FastAPI application
- health check endpoint
- Jinja2 template rendering
- static file support

## 2. Why this phase matters in the system design

Before we add databases, authentication, and business logic, we need a clean and runnable application shell. This gives us:

- a stable place to plug later layers into
- a consistent project structure from day one
- a basic request/response flow we can verify early

If we skip this and jump directly into models or auth, debugging becomes much harder because there is no known-good application baseline.

## 3. Files/folders we created or edited

- `.gitignore`
- `.env.example`
- `requirements.txt`
- `app/__init__.py`
- `app/main.py`
- `app/routes/__init__.py`
- `app/routes/root_routes.py`
- `app/models/__init__.py`
- `app/schemas/__init__.py`
- `app/repositories/__init__.py`
- `app/services/__init__.py`
- `app/middleware/__init__.py`
- `app/dependencies/__init__.py`
- `app/utils/__init__.py`
- `app/templates/base.html`
- `app/templates/home.html`
- `app/static/css/styles.css`
- `app/static/js/main.js`
- `docs/PHASE_1_SETUP.md`

## 4. Exact terminal commands to run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open the app in your browser:

```text
http://127.0.0.1:8000
```

Check the health endpoint:

```text
http://127.0.0.1:8000/health
```

## 5. Full code for each file

The source files created in this phase are the same ones present in the repository after this update.

## 6. Explanation of the code

### `app/main.py`

This is the FastAPI entry point. It:

- creates the application object
- registers the root router
- mounts the static directory under `/static`

Why this is good:

- keeps startup logic in one place
- gives us an app factory pattern we can extend later

### `app/routes/root_routes.py`

This file keeps route logic out of `main.py`. It includes:

- `GET /` to render the home page
- `GET /health` to confirm the server is alive

Why this matters:

- even in Phase 1, we start respecting route-layer boundaries

### `app/templates/`

Templates prove that server-rendered HTML works. This matches the project direction of using Jinja2 instead of immediately adding a frontend framework.

### `app/static/`

Static assets prove CSS and JavaScript mounting works now, before the UI grows larger.

### `.env.example`

This documents the first configuration values without hardcoding secrets into the app codebase.

### `requirements.txt`

This includes the planned stack early so the environment is consistent with the roadmap.

## 7. How this connects to the architecture

This phase creates the shell that later layers will attach to:

- routes already live in their own package
- templates are separated from route code
- services, repositories, models, dependencies, middleware, and utils packages already exist

That means in later phases we can fill each layer without reorganizing the project repeatedly.

## 8. How to test this phase

### Browser test

1. Start the server with `uvicorn app.main:app --reload`
2. Visit `http://127.0.0.1:8000`
3. Confirm the starter page loads with styled content

### Health check test

1. Visit `http://127.0.0.1:8000/health`
2. Confirm the response is:

```json
{"status":"ok"}
```

### Static file test

1. Open the home page
2. Confirm the page is styled rather than plain HTML

## 9. Common errors and how to fix them

### Error: `ModuleNotFoundError: No module named 'fastapi'`

Cause:

- dependencies are not installed in the active virtual environment

Fix:

- activate `.venv`
- run `pip install -r requirements.txt`

### Error: `Error loading ASGI app`

Cause:

- `uvicorn` was started from the wrong directory

Fix:

- run the command from the project root:

```bash
uvicorn app.main:app --reload
```

### Error: template not found

Cause:

- template directory path is wrong

Fix:

- keep templates under `app/templates`
- ensure `root_routes.py` points Jinja2Templates to that directory

### Error: static files not loading

Cause:

- static directory is not mounted

Fix:

- ensure `app.mount("/static", StaticFiles(directory="app/static"), name="static")` exists in `app/main.py`

## 10. Checkpoint summary before moving to the next phase

At the end of Phase 1 we have:

- a runnable FastAPI project
- the clean package skeleton
- a working route layer
- Jinja2 rendering
- static file support
- a documented setup process

This is the right foundation for Phase 2, where we add structured configuration and database setup.
