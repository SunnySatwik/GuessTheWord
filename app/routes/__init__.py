from app.routes.auth import (
    get_current_user,
    require_authenticated_user,
    require_role,
    router as auth_router,
)
from app.routes.game import router as game_router

__all__ = [
    "auth_router",
    "game_router",
    "get_current_user",
    "require_authenticated_user",
    "require_role",
]
