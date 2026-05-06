from datetime import date
from decimal import Decimal

from decimal import InvalidOperation
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


router = APIRouter(prefix="/approver", tags=["approver"])
templates = Jinja2Templates(directory="app/templates")


def require_approver(request: Request) -> int | None:
    user_id = request.session.get("user_id")
    role = request.session.get("role")
    if not user_id or role != "approver":
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
async def approver_dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)

    submissions = submission_service.get_submissions_by_user(db, approver_id)
    stats = submission_service.get_user_submission_stats(db, approver_id)
    categories = category_service.get_all_categories(db, active_only=True)
    notifications = notification_service.get_unread_notifications(db, approver_id)
    return templates.TemplateResponse(
        "approver/dashboard.html",
        {
            "request": request,
            "stats": stats,
            "submissions": submissions,
            "categories": categories,
            "notifications": notifications,
            "session": request.session,
            "error": None,
            "form_data": {},
            "show_create_modal": bool(request.query_params.get("open_create")),
        },
    )


@router.get("/submission/create")
async def approver_create_submission_page(request: Request, db: Session = Depends(get_db)):
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/approver/dashboard?open_create=1", status_code=302)


@router.post("/submission/create")
async def approver_create_submission(
    request: Request,
    name: str = Form(...),
    purpose: str = Form(...),
    nominal: str = Form(...),
    category_id: int = Form(...),
    document: UploadFile = File(None),
    documents: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)

    try:
        clean_nominal = nominal.replace(",", "").replace(" ", "")
        nominal_value = Decimal(clean_nominal)
        if nominal_value <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        submissions = submission_service.get_submissions_by_user(db, approver_id)
        stats = submission_service.get_user_submission_stats(db, approver_id)
        categories = category_service.get_all_categories(db, active_only=True)
        notifications = notification_service.get_unread_notifications(db, approver_id)
        return templates.TemplateResponse(
            "approver/dashboard.html",
            {
                "request": request,
                "submissions": submissions,
                "stats": stats,
                "categories": categories,
                "session": request.session,
                "notifications": notifications,
                "error": "Invalid nominal value",
                "form_data": {
                    "name": name,
                    "purpose": purpose,
                    "nominal": nominal,
                    "category_id": category_id,
                },
                "show_create_modal": True,
            },
        )

    doc_path = None
    doc_original = None
    if document and document.filename:
        doc_path, doc_original = await submission_service.save_upload_file(document)
    attachments = await submission_service.save_upload_files(documents)

    submission_service.create_submission(
        db=db,
        user_id=approver_id,
        name=name.strip(),
        purpose=purpose.strip(),
        nominal=nominal_value,
        category_id=category_id,
        document_path=doc_path,
        document_original_name=doc_original,
        attachments=attachments,
    )
    return RedirectResponse(url="/approver/dashboard?created=1", status_code=302)


@router.get("/approvals")
async def approver_approvals(
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
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)

    approver = auth_service.get_user_by_id(db, approver_id)
    stats = submission_service.get_submission_stats(db)
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
    submissions = [
        s
        for s in submissions
        if (s.user and s.user.role == "user")
        and (
            submission_service.can_user_act_on_submission(db, s, approver, "approve")
            or submission_service.can_user_act_on_submission(db, s, approver, "reject")
            or submission_service.can_user_act_on_submission(db, s, approver, "revision")
        )
    ]
    categories = category_service.get_all_categories(db)
    divisions = division_service.get_all_divisions(db)
    users = db.query(User).filter(User.role == "user").order_by(User.full_name).all()
    notifications = notification_service.get_unread_notifications(db, approver_id)
    visual_stats = submission_service.get_visual_stats(db)

    return templates.TemplateResponse(
        "approver/approvals.html",
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
            "current_filter": status or "all",
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


@router.get("/approvals/export")
async def approver_export_approvals(
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
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)

    approver = auth_service.get_user_by_id(db, approver_id)
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
    submissions = [
        s
        for s in submissions
        if (s.user and s.user.role == "user")
        and (
            submission_service.can_user_act_on_submission(db, s, approver, "approve")
            or submission_service.can_user_act_on_submission(db, s, approver, "reject")
            or submission_service.can_user_act_on_submission(db, s, approver, "revision")
        )
    ]
    csv_text = submission_service.export_submissions_csv(submissions)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename=\"approvals-report.csv\"'},
    )


@router.get("/submission/{submission_id}")
async def approver_review_submission(
    request: Request, submission_id: int, db: Session = Depends(get_db)
):
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)

    submission = submission_service.get_submission_by_id(db, submission_id)
    if not submission:
        return RedirectResponse(url="/approver/dashboard", status_code=302)

    approver = auth_service.get_user_by_id(db, approver_id)
    can_approve = bool(
        approver and submission_service.can_user_act_on_submission(db, submission, approver, "approve")
    )
    can_reject = bool(
        approver and submission_service.can_user_act_on_submission(db, submission, approver, "reject")
    )
    can_revision = bool(
        approver and submission_service.can_user_act_on_submission(db, submission, approver, "revision")
    )

    required_role = submission_service.get_required_role_for_submission_step(db, submission)
    total_steps = submission_service.get_total_steps_for_submission(db, submission)

    notifications = notification_service.get_unread_notifications(db, approver_id)
    error = request.query_params.get("error")
    error_msg = None
    if error == "not_allowed":
        error_msg = "You are not allowed to perform that action for the current approval step."

    return templates.TemplateResponse(
        "approver/review.html",
        {
            "request": request,
            "submission": submission,
            "notifications": notifications,
            "session": request.session,
            "error": error_msg,
            "can_approve": can_approve,
            "can_reject": can_reject,
            "can_revision": can_revision,
            "can_pay": False,
            "required_role": required_role,
            "total_steps": total_steps,
        },
    )


@router.get("/profile")
async def approver_profile(request: Request, db: Session = Depends(get_db)):
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)

    user = auth_service.get_user_by_id(db, approver_id)
    if not user:
        return RedirectResponse(url="/logout", status_code=302)

    stats = submission_service.get_submission_stats_for_user(db, approver_id)
    notifications = notification_service.get_unread_notifications(db, approver_id)
    return templates.TemplateResponse(
        "approver/profile.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "notifications": notifications,
            "session": request.session,
        },
    )


@router.post("/submission/{submission_id}/approve")
async def approver_approve_submission(
    request: Request,
    submission_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)
    updated = submission_service.approve_submission(db, submission_id, approver_id, notes.strip() or None)
    if not updated:
        return RedirectResponse(url=f"/approver/submission/{submission_id}?error=not_allowed", status_code=302)
    return RedirectResponse(url="/approver/dashboard?approved=1", status_code=302)


@router.post("/submission/{submission_id}/reject")
async def approver_reject_submission(
    request: Request,
    submission_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)
    updated = submission_service.reject_submission(db, submission_id, approver_id, notes.strip() or None)
    if not updated:
        return RedirectResponse(url=f"/approver/submission/{submission_id}?error=not_allowed", status_code=302)
    return RedirectResponse(url="/approver/dashboard?rejected=1", status_code=302)


@router.post("/submission/{submission_id}/revision")
async def approver_request_revision(
    request: Request,
    submission_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    approver_id = require_approver(request)
    if not approver_id:
        return RedirectResponse(url="/login", status_code=302)
    updated = submission_service.request_revision_submission(db, submission_id, approver_id, notes.strip() or None)
    if not updated:
        return RedirectResponse(url=f"/approver/submission/{submission_id}?error=not_allowed", status_code=302)
    return RedirectResponse(url="/approver/dashboard?revision=1", status_code=302)
