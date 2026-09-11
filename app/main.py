from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, settings

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


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint confirming application status."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/", response_class=HTMLResponse)
def root(request: Request) -> HTMLResponse:
    """Development verification page confirming templates and routing function properly."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "environment": settings.app_env,
            "status": "online",
        },
    )
