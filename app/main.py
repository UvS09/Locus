from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.routes.admin_routes import router as admin_router
from app.routes.auth_routes import router as auth_router
from app.routes.employee_routes import router as employee_router
from app.routes.hierarchy_routes import router as hierarchy_router
from app.routes.manager_routes import router as manager_router
from app.routes.notification_routes import router as notification_router
from app.routes.root_routes import router as root_router
from app.routes.task_routes import router as task_router

settings = get_settings()


def create_application() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.app_debug)
    init_db()
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(root_router)
    app.include_router(auth_router)
    app.include_router(hierarchy_router)
    app.include_router(admin_router)
    app.include_router(manager_router)
    app.include_router(employee_router)
    app.include_router(task_router)
    app.include_router(notification_router)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    return app


app = create_application()
