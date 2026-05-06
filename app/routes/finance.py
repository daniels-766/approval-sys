from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services import (
    submission_service,
    notification_service,
    auth_service,
    category_service,
    division_service,
)


router = APIRouter(prefix="/finance", tags=["finance"])
templates = Jinja2Templates(directory="app/templates")


def require_finance(request: Request) -> int | None:
    user_id = request.session.get("user_id")
    role = request.session.get("role")
    if not user_id or role != "finance":
        return None
    return int(user_id)


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    return Decimal(value.replace(",", "").strip())


@router.get("/dashboard")
async def finance_dashboard(
    request: Request,
    status: str | None = None,
    keyword: str | None = None,
    category_id: str | None = None,
    division_id: str | None = None,
    user_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_nominal: str | None = None,
    max_nominal: str | None = None,
    db: Session = Depends(get_db),
):
    finance_id = require_finance(request)
    if not finance_id:
        return RedirectResponse(url="/login", status_code=302)

    # Finance dashboard defaults to "Need Payment" (approved).
    if status is None:
        return RedirectResponse(
            url=str(request.url.include_query_params(status="approved")),
            status_code=302,
        )

    # Normalize URL so the dashboard state matches querystring (important for Export link).
    if status not in ("approved", "paid", "all"):
        return RedirectResponse(
            url=str(request.url.include_query_params(status="approved")),
            status_code=302,
        )

    stats = submission_service.get_submission_stats(db)
    normalized_status = None if status == "all" else status
    submissions = submission_service.get_all_submissions(
        db,
        status_filter=normalized_status,
        keyword=keyword,
        category_id=_parse_int(category_id),
        division_id=_parse_int(division_id),
        user_id=_parse_int(user_id),
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
        min_nominal=_parse_decimal(min_nominal),
        max_nominal=_parse_decimal(max_nominal),
    )
    # Finance only sees approved/paid.
    submissions = [s for s in submissions if s.status in ("approved", "paid")]

    notifications = notification_service.get_unread_notifications(db, finance_id)
    categories = category_service.get_all_categories(db)
    divisions = division_service.get_all_divisions(db)
    users = db.query(User).filter(User.role == "user").order_by(User.full_name).all()
    visual_stats = submission_service.get_visual_stats(db)
    return templates.TemplateResponse(
        "finance/dashboard.html",
        {
            "request": request,
            "stats": stats,
            "submissions": submissions,
            "categories": categories,
            "divisions": divisions,
            "users": users,
            "notifications": notifications,
            "visual_stats": visual_stats,
            "session": request.session,
            "current_filter": status,
            "filters": {
                "keyword": keyword or "",
                "category_id": _parse_int(category_id),
                "division_id": _parse_int(division_id),
                "user_id": _parse_int(user_id),
                "date_from": date_from or "",
                "date_to": date_to or "",
                "min_nominal": min_nominal or "",
                "max_nominal": max_nominal or "",
            },
        },
    )


@router.get("/dashboard/export")
async def finance_export_dashboard(
    request: Request,
    status: str | None = None,
    keyword: str | None = None,
    category_id: str | None = None,
    division_id: str | None = None,
    user_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_nominal: str | None = None,
    max_nominal: str | None = None,
    db: Session = Depends(get_db),
):
    finance_id = require_finance(request)
    if not finance_id:
        return RedirectResponse(url="/login", status_code=302)

    submissions = submission_service.get_all_submissions(
        db,
        status_filter=status,
        keyword=keyword,
        category_id=_parse_int(category_id),
        division_id=_parse_int(division_id),
        user_id=_parse_int(user_id),
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
        min_nominal=_parse_decimal(min_nominal),
        max_nominal=_parse_decimal(max_nominal),
    )
    submissions = [s for s in submissions if s.status in ("approved", "paid")]
    csv_text = submission_service.export_submissions_csv(submissions)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="payments-report.csv"'},
    )


@router.get("/submission/{submission_id}")
async def finance_view_submission(
    request: Request, submission_id: int, db: Session = Depends(get_db)
):
    finance_id = require_finance(request)
    if not finance_id:
        return RedirectResponse(url="/login", status_code=302)

    submission = submission_service.get_submission_by_id(db, submission_id)
    if not submission:
        return RedirectResponse(url="/finance/dashboard", status_code=302)

    finance_user = auth_service.get_user_by_id(db, finance_id)
    can_pay = bool(
        finance_user and submission_service.can_user_act_on_submission(db, submission, finance_user, "pay")
    )
    required_role = submission_service.get_required_role_for_submission_step(db, submission)
    total_steps = submission_service.get_total_steps_for_submission(db, submission)

    notifications = notification_service.get_unread_notifications(db, finance_id)
    error = request.query_params.get("error")
    error_msg = None
    if error == "not_allowed":
        error_msg = "You are not allowed to perform that action."

    return templates.TemplateResponse(
        "finance/review.html",
        {
            "request": request,
            "submission": submission,
            "notifications": notifications,
            "session": request.session,
            "error": error_msg,
            "can_approve": False,
            "can_reject": False,
            "can_revision": False,
            "can_pay": can_pay,
            "required_role": required_role,
            "total_steps": total_steps,
        },
    )


@router.post("/submission/{submission_id}/pay")
async def finance_pay_submission(
    request: Request,
    submission_id: int,
    notes: str = Form(""),
    documents: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    finance_id = require_finance(request)
    if not finance_id:
        return RedirectResponse(url="/login", status_code=302)
    attachments = await submission_service.save_upload_files(documents)
    updated = submission_service.pay_submission(
        db, submission_id, finance_id, notes.strip() or None, attachments=attachments
    )
    if not updated:
        return RedirectResponse(url=f"/finance/submission/{submission_id}?error=not_allowed", status_code=302)
    return RedirectResponse(url="/finance/dashboard?paid=1", status_code=302)
