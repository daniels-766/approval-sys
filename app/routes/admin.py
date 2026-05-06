from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.services import auth_service, category_service, division_service, submission_service, notification_service

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


def require_admin(request: Request):
    """Check if user is logged in and has 'admin' role."""
    user_id = request.session.get("user_id")
    role = request.session.get("role")
    if not user_id or role != "admin":
        return None
    return user_id


def require_staff(request: Request):
    """Check if user is logged in and has a staff role (approver/admin/finance)."""
    user_id = request.session.get("user_id")
    role = request.session.get("role")
    if not user_id or role not in ("approver", "admin", "finance"):
        return None
    return user_id


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


def _parse_bool(value: str | None) -> bool:
    return value in ("1", "true", "on", "yes")


@router.get("/dashboard")
async def admin_dashboard(
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
    """Admin dashboard with all submissions and stats."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    parsed_category_id = _parse_int(category_id)
    parsed_division_id = _parse_int(division_id)
    parsed_user_id = _parse_int(user_id)
    parsed_date_from = _parse_date(date_from)
    parsed_date_to = _parse_date(date_to)
    parsed_min_nominal = _parse_decimal(min_nominal)
    parsed_max_nominal = _parse_decimal(max_nominal)
    staff_user = auth_service.get_user_by_id(db, admin_id)
    stats = submission_service.get_submission_stats(db)
    submissions = submission_service.get_all_submissions(
        db,
        status_filter=status,
        keyword=keyword,
        category_id=parsed_category_id,
        division_id=parsed_division_id,
        user_id=parsed_user_id,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
        min_nominal=parsed_min_nominal,
        max_nominal=parsed_max_nominal,
    )

    # Staff scoping:
    # - admin sees everything
    # - approver sees only submissions they can act on at current step
    # - finance sees only approved/paid submissions (payment-related)
    if staff_user and staff_user.role == "approver":
        submissions = [
            s
            for s in submissions
            if submission_service.can_user_act_on_submission(db, s, staff_user, "approve")
            or submission_service.can_user_act_on_submission(db, s, staff_user, "reject")
            or submission_service.can_user_act_on_submission(db, s, staff_user, "revision")
        ]
    elif staff_user and staff_user.role == "finance":
        submissions = [s for s in submissions if s.status in ("approved", "paid")]
    # Admin sees submissions from anyone who has 'approver' authority (Global or Division-level)
    def is_effective_approver(user):
        if not user: return False
        if user.role == "approver": return True
        return any(assoc.role == "approver" for assoc in user.division_associations)

    submissions = [s for s in submissions if is_effective_approver(s.user)]
    
    categories = category_service.get_all_categories(db)
    divisions = division_service.get_all_divisions(db)
    users = (
        db.query(User)
        .order_by(User.full_name)
        .all()
    )
    
    # Fetch Notifications
    unread_notifications = notification_service.get_unread_notifications(db, admin_id)

    # Fetch Visual Stats (Charts)
    visual_stats = submission_service.get_visual_stats(db)

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "stats": stats,
        "submissions": submissions,
        "categories": categories,
        "divisions": divisions,
        "users": users,
        "notifications": unread_notifications,
        "visual_stats": visual_stats,
        "session": request.session,
        "current_filter": status or "all",
        "filters": {
            "keyword": keyword or "",
            "category_id": parsed_category_id,
            "division_id": parsed_division_id,
            "user_id": parsed_user_id,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "min_nominal": min_nominal or "",
            "max_nominal": max_nominal or "",
        },
    })

@router.get("/statistics")
async def admin_statistics(
    request: Request,
    db: Session = Depends(get_db),
):
    """Admin statistics page with charts."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    # Fetch Notifications
    notifications = notification_service.get_unread_notifications(db, admin_id)
    
    # Fetch Visual Stats (Charts)
    visual_stats = submission_service.get_visual_stats(db)

    return templates.TemplateResponse("admin/statistics.html", {
        "request": request,
        "notifications": notifications,
        "visual_stats": visual_stats,
        "session": request.session,
    })


@router.get("/dashboard/export")
async def export_dashboard(
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
    """Export filtered submissions as CSV."""
    admin_id = require_admin(request)
    if not admin_id:
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
    csv_text = submission_service.export_submissions_csv(submissions)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="submissions-report.csv"'},
    )


@router.get("/submission/{submission_id}")
async def review_submission(
    request: Request, submission_id: int, db: Session = Depends(get_db)
):
    """View submission detail for review."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    submission = submission_service.get_submission_by_id(db, submission_id)
    if not submission:
        return RedirectResponse(url="/admin/dashboard", status_code=302)

    # Notifications
    notifications = notification_service.get_unread_notifications(db, admin_id)

    staff_user = auth_service.get_user_by_id(db, admin_id)
    can_approve = bool(staff_user and submission_service.can_user_act_on_submission(db, submission, staff_user, "approve"))
    can_reject = bool(staff_user and submission_service.can_user_act_on_submission(db, submission, staff_user, "reject"))
    can_revision = bool(staff_user and submission_service.can_user_act_on_submission(db, submission, staff_user, "revision"))
    can_pay = bool(staff_user and submission_service.can_user_act_on_submission(db, submission, staff_user, "pay"))

    required_role = submission_service.get_required_role_for_submission_step(db, submission)
    total_steps = submission_service.get_total_steps_for_submission(db, submission)

    error = request.query_params.get("error")
    error_msg = None
    if error == "not_allowed":
        error_msg = "You are not allowed to perform that action for the current approval step."

    return templates.TemplateResponse("admin/review.html", {
        "request": request,
        "submission": submission,
        "notifications": notifications,
        "error": error_msg,
        "can_approve": can_approve,
        "can_reject": can_reject,
        "can_revision": can_revision,
        "can_pay": can_pay,
        "required_role": required_role,
        "total_steps": total_steps,
        "session": request.session,
    })


@router.post("/submission/{submission_id}/approve")
async def approve_submission(
    request: Request,
    submission_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    """Approve a submission."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    updated = submission_service.approve_submission(db, submission_id, admin_id, notes.strip() or None)
    if not updated:
        return RedirectResponse(url=f"/admin/submission/{submission_id}?error=not_allowed", status_code=302)
    return RedirectResponse(url="/admin/dashboard?approved=1", status_code=302)


@router.post("/submission/{submission_id}/reject")
async def reject_submission(
    request: Request,
    submission_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    """Reject a submission."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    updated = submission_service.reject_submission(db, submission_id, admin_id, notes.strip() or None)
    if not updated:
        return RedirectResponse(url=f"/admin/submission/{submission_id}?error=not_allowed", status_code=302)
    return RedirectResponse(url="/admin/dashboard?rejected=1", status_code=302)


@router.post("/submission/{submission_id}/revision")
async def request_revision(
    request: Request,
    submission_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    """Request revision for a submission."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    updated = submission_service.request_revision_submission(
        db, submission_id, admin_id, notes.strip() or None
    )
    if not updated:
        return RedirectResponse(url=f"/admin/submission/{submission_id}?error=not_allowed", status_code=302)
    return RedirectResponse(url="/admin/dashboard?revision=1", status_code=302)


@router.post("/submission/{submission_id}/pay")
async def pay_submission(
    request: Request,
    submission_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    """Mark an approved submission as paid (finance)."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    updated = submission_service.pay_submission(db, submission_id, admin_id, notes.strip() or None)
    if not updated:
        return RedirectResponse(url=f"/admin/submission/{submission_id}?error=not_allowed", status_code=302)
    return RedirectResponse(url="/admin/dashboard?paid=1", status_code=302)


@router.post("/submission/{submission_id}/delete")
async def delete_submission(
    request: Request, submission_id: int, db: Session = Depends(get_db)
):
    """Delete a submission."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    submission_service.delete_submission(db, submission_id)
    return RedirectResponse(url="/admin/dashboard?deleted=1", status_code=302)


@router.get("/users")
async def users_page(
    request: Request,
    keyword: str | None = None,
    role: str | None = None,
    active: str | None = None,
    db: Session = Depends(get_db),
):
    """User management page."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    active_filter = None
    if active == "active":
        active_filter = True
    elif active == "inactive":
        active_filter = False
    users = auth_service.get_all_users(
        db, keyword=keyword, role=role, active=active_filter
    )
    divisions = division_service.get_all_divisions(db, active_only=True)
    # Notifications
    notifications = notification_service.get_unread_notifications(db, admin_id)

    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "users": users,
        "divisions": divisions,
        "notifications": notifications,
        "session": request.session,
        "filters": {
            "keyword": keyword or "",
            "role": role or "",
            "active": active or "",
        },
    })


@router.post("/users")
async def create_admin_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    division_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    """Create a user from admin panel."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if len(password) < 6:
        return RedirectResponse(url="/admin/users?error=password", status_code=302)
    if auth_service.get_user_by_username(db, username.strip()):
        return RedirectResponse(url="/admin/users?error=username", status_code=302)
    if auth_service.get_user_by_email(db, email.strip()):
        return RedirectResponse(url="/admin/users?error=email", status_code=302)

    form_data = await request.form()
    division_ids = form_data.getlist("division_ids")
    division_roles = {}
    for div_id in division_ids:
        div_role = form_data.get(f"role_{div_id}", "user")
        division_roles[int(div_id)] = div_role

    user = auth_service.create_user(
        db,
        username=username.strip(),
        email=email.strip(),
        password=password,
        full_name=full_name.strip(),
        role=role,
        division_roles=division_roles
    )
    return RedirectResponse(url="/admin/users?created=1", status_code=302)


@router.post("/users/{user_id}/update")
async def update_admin_user(
    request: Request,
    user_id: int,
    username: str = Form(...),
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form("user"),
    is_active: str | None = Form(None),
    division_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    """Update a user from admin panel."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    existing_username = auth_service.get_user_by_username(db, username.strip())
    if existing_username and existing_username.id != user_id:
        return RedirectResponse(url="/admin/users?error=username", status_code=302)
    existing_email = auth_service.get_user_by_email(db, email.strip())
    if existing_email and existing_email.id != user_id:
        return RedirectResponse(url="/admin/users?error=email", status_code=302)
    form_data = await request.form()
    division_ids = form_data.getlist("division_ids")
    division_roles = {}
    for div_id in division_ids:
        div_role = form_data.get(f"role_{div_id}", "user")
        division_roles[int(div_id)] = div_role

    auth_service.update_user(
        db,
        user_id,
        username=username.strip(),
        email=email.strip(),
        full_name=full_name.strip(),
        role=role,
        is_active=_parse_bool(is_active),
        division_roles=division_roles,
    )
    return RedirectResponse(url="/admin/users?updated=1", status_code=302)


@router.post("/users/{user_id}/toggle")
async def toggle_admin_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    """Toggle a user's active flag."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    user = auth_service.get_user_by_id(db, user_id)
    if user and user.id != admin_id:
        auth_service.update_user(
            db,
            user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=not user.is_active,
            division_roles={assoc.division_id: assoc.role for assoc in user.division_associations},
        )
    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/password")
async def reset_admin_user_password(
    request: Request,
    user_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Reset a user's password from admin panel."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if len(password) < 6:
        return RedirectResponse(url="/admin/users?error=password", status_code=302)
    auth_service.reset_user_password(db, user_id, password)
    return RedirectResponse(url="/admin/users?password=1", status_code=302)


# ─── Category Management ────────────────────────────────────────────────────────

@router.get("/categories")
async def categories_page(request: Request, db: Session = Depends(get_db)):
    """Category management page."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    categories = category_service.get_all_categories(db)
    divisions = division_service.get_all_divisions(db, active_only=True)
    # Notifications
    notifications = notification_service.get_unread_notifications(db, admin_id)

    return templates.TemplateResponse("admin/categories.html", {
        "request": request,
        "categories": categories,
        "divisions": divisions,
        "notifications": notifications,
        "session": request.session,
    })


@router.post("/categories")
async def create_category(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    division_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Create a new category."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        category_service.create_category(db, name.strip(), description.strip() or None, division_id=division_id)
        return RedirectResponse(url="/admin/categories?created=1", status_code=302)
    except Exception:
        return RedirectResponse(url="/admin/categories?error=duplicate", status_code=302)


@router.post("/categories/{category_id}/update")
async def update_category(
    request: Request,
    category_id: int,
    name: str = Form(...),
    description: str = Form(""),
    division_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Update a category."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    category_service.update_category(
        db, category_id, name=name.strip(), description=description.strip() or None, division_id=division_id
    )
    return RedirectResponse(url="/admin/categories?updated=1", status_code=302)


@router.post("/categories/{category_id}/toggle")
async def toggle_category(
    request: Request, category_id: int, db: Session = Depends(get_db)
):
    """Toggle category active status."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    cat = category_service.get_category_by_id(db, category_id)
    if cat:
        category_service.update_category(db, category_id, is_active=not cat.is_active)
    return RedirectResponse(url="/admin/categories", status_code=302)


# ─── Division Management ─────────────────────────────────────────────────────────

@router.get("/divisions")
async def divisions_page(request: Request, db: Session = Depends(get_db)):
    """Division management page."""
    admin_id = require_admin(request)
    if not admin_id:
        return RedirectResponse(url="/login", status_code=302)

    divisions = division_service.get_all_divisions(db)
    users = (
        db.query(User)
        .filter(User.role == "user", User.is_active == True)
        .order_by(User.full_name)
        .all()
    )
    # Notifications
    notifications = notification_service.get_unread_notifications(db, admin_id)

    return templates.TemplateResponse("admin/divisions.html", {
        "request": request,
        "divisions": divisions,
        "users": users,
        "notifications": notifications,
        "session": request.session,
    })


@router.post("/divisions")
async def create_division(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create a new division."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        division_service.create_division(db, name.strip(), description.strip() or None)
        return RedirectResponse(url="/admin/divisions?created=1", status_code=302)
    except Exception:
        return RedirectResponse(url="/admin/divisions?error=duplicate", status_code=302)


@router.post("/divisions/{division_id}/update")
async def update_division(
    request: Request,
    division_id: int,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    """Update a division."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    division_service.update_division(
        db, division_id, name=name.strip(), description=description.strip() or None
    )
    return RedirectResponse(url="/admin/divisions?updated=1", status_code=302)


@router.post("/divisions/{division_id}/toggle")
async def toggle_division(
    request: Request, division_id: int, db: Session = Depends(get_db)
):
    """Toggle division active status."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    div = division_service.get_division_by_id(db, division_id)
    if div:
        division_service.update_division(db, division_id, is_active=not div.is_active)
    return RedirectResponse(url="/admin/divisions", status_code=302)


@router.post("/divisions/{division_id}/users")
async def update_division_users(
    request: Request,
    division_id: int,
    user_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    """Assign users to a division."""
    admin_id = require_admin(request)
    if not admin_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    division_service.assign_users_to_division(db, division_id, user_ids)
    return RedirectResponse(url="/admin/divisions?users_updated=1", status_code=302)
