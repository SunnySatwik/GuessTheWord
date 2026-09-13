from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.enums.role import UserRole
from app.exceptions import UserNotFoundError
from app.models.user import User
from app.routes.auth import get_current_user, require_role
from app.schemas.report import (
    DailyReportResponse,
    UserReportResponse,
    UserSummaryResponse,
)
from app.services.report_service import (
    get_daily_report,
    get_user_report,
    list_report_users,
)

router = APIRouter(prefix="/admin/reports", tags=["admin-reports"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_reports_page(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> Response:
    """Render the Admin Reports dashboard page. Requires ADMIN role."""
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return templates.TemplateResponse(
        request=request,
        name="admin/reports.html",
        context={
            "user": user,
        },
    )


@router.get("/daily", response_model=DailyReportResponse)
def get_daily_report_endpoint(
    date: date | None = Query(
        default=None,
        description="Report date in YYYY-MM-DD format (UTC). Defaults to today if omitted.",
    ),
    admin_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DailyReportResponse:
    """Daily summary report endpoint across all players. Requires ADMIN role."""
    target_date = date or datetime.now(timezone.utc).date()
    return get_daily_report(db, target_date)


@router.get("/user/{user_id}", response_model=UserReportResponse)
def get_user_report_endpoint(
    user_id: int,
    date: date | None = Query(
        default=None,
        description="Report date in YYYY-MM-DD format (UTC). Defaults to today if omitted.",
    ),
    admin_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> UserReportResponse:
    """Per-user activity report endpoint for a specific date. Requires ADMIN role."""
    target_date = date or datetime.now(timezone.utc).date()
    try:
        return get_user_report(db, user_id, target_date)
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/users", response_model=list[UserSummaryResponse])
def get_report_users_endpoint(
    admin_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> list[UserSummaryResponse]:
    """List all registered users for admin report configuration. Requires ADMIN role."""
    return list_report_users(db)
