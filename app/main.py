from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, settings
from app.models.user import User
from app.routes.auth import get_current_user, router as auth_router
from app.routes.game import router as game_router

# Initialize FastAPI application
app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

# Mount static files directory
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "app" / "static")),
    name="static",
)

# Configure Jinja2 templates directory
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Include Application Routers
app.include_router(auth_router)
app.include_router(game_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint confirming application status."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/", response_class=HTMLResponse)
def root(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> HTMLResponse:
    """Development verification page confirming templates, routing, and user session."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "environment": settings.app_env,
            "status": "online",
            "user": user,
        },
    )
