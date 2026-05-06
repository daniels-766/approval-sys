from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import submission_service, category_service, notification_service, auth_service

router = APIRouter(prefix="/user", tags=["user"])
templates = Jinja2Templates(directory="app/templates")


def require_user(request: Request):
    """Check if user is logged in and can act as a requester (user/approver)."""
    user_id = request.session.get("user_id")
    role = request.session.get("role")
    if not user_id or role not in ("user", "approver"):
        return None
    return user_id


def render_user_dashboard(
    request: Request,
    db: Session,
    user_id: int,
    error: str | None = None,
    form_data: dict | None = None,
    show_create_modal: bool = False,
):
    """Render the unified dashboard and create-submission experience."""
    submissions = submission_service.get_submissions_by_user(db, user_id)
    stats = submission_service.get_user_submission_stats(db, user_id)
    user = auth_service.get_user_by_id(db, user_id)
    # Filter categories: all active categories are global now
    from app.models.category import Category
    categories = db.query(Category).filter(Category.is_active == True).order_by(Category.name).all()
    
    notifications = notification_service.get_unread_notifications(db, user_id)
    return templates.TemplateResponse("user/dashboard.html", {
        "request": request,
        "submissions": submissions,
        "stats": stats,
        "categories": categories,
        "session": request.session,
        "notifications": notifications,
        "error": error,
        "form_data": form_data or {},
        "show_create_modal": show_create_modal or bool(request.query_params.get("open_create")),
    })


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """User dashboard showing their submissions."""
    user_id = require_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    return render_user_dashboard(request, db, user_id)


@router.get("/submission/create")
async def create_submission_page(request: Request, db: Session = Depends(get_db)):
    """Redirect the legacy create page to the dashboard modal."""
    user_id = require_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    return RedirectResponse(url="/user/dashboard?open_create=1", status_code=302)


@router.post("/submission/create")
async def create_submission(
    request: Request,
    name: str = Form(...),
    purpose: str = Form(...),
    nominal: str = Form(...),
    category_id: int = Form(...),
    document: UploadFile = File(None),
    documents: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    """Handle submission creation with file upload."""
    user_id = require_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    # Parse nominal — remove commas and spaces
    try:
        clean_nominal = nominal.replace(",", "").replace(" ", "")
        nominal_value = Decimal(clean_nominal)
        if nominal_value <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        return render_user_dashboard(
            request,
            db,
            user_id,
            error="Invalid nominal value",
            form_data={
                "name": name,
                "purpose": purpose,
                "nominal": nominal,
                "category_id": category_id,
            },
            show_create_modal=True,
        )

    # Handle file uploads. Keep the old single-file field for backward compatibility.
    doc_path = None
    doc_original = None
    if document and document.filename:
        doc_path, doc_original = await submission_service.save_upload_file(document)
    attachments = await submission_service.save_upload_files(documents)

    submission = submission_service.create_submission(
        db=db,
        user_id=user_id,
        name=name.strip(),
        purpose=purpose.strip(),
        nominal=nominal_value,
        category_id=category_id,
        document_path=doc_path,
        document_original_name=doc_original,
        attachments=attachments,
    )

    return RedirectResponse(url="/user/dashboard?created=1", status_code=302)


@router.get("/submission/{submission_id}")
async def submission_detail(
    request: Request, submission_id: int, db: Session = Depends(get_db)
):
    """View submission detail."""
    user_id = require_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    submission = submission_service.get_submission_by_id(db, submission_id)
    if not submission or submission.user_id != user_id:
        return RedirectResponse(url="/user/dashboard", status_code=302)

    return templates.TemplateResponse(request, "user/detail.html", {
        "submission": submission,
        "categories": category_service.get_all_categories(db, active_only=True),
        "session": request.session,
        "error": None,
    })


@router.post("/submission/{submission_id}/update")
async def update_submission_revision(
    request: Request,
    submission_id: int,
    name: str = Form(...),
    purpose: str = Form(...),
    nominal: str = Form(...),
    category_id: int = Form(...),
    documents: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    """Allow users to edit and resubmit submissions marked as need_revision."""
    user_id = require_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    submission = submission_service.get_submission_by_id(db, submission_id)
    if not submission or submission.user_id != user_id:
        return RedirectResponse(url="/user/dashboard", status_code=302)

    categories = category_service.get_all_categories(db, active_only=True)
    try:
        clean_nominal = nominal.replace(",", "").replace(" ", "")
        nominal_value = Decimal(clean_nominal)
        if nominal_value <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        return templates.TemplateResponse(request, "user/detail.html", {
            "submission": submission,
            "categories": categories,
            "session": request.session,
            "error": "Invalid nominal value",
        })

    attachments = await submission_service.save_upload_files(documents)
    updated = submission_service.revise_submission(
        db=db,
        submission_id=submission_id,
        user_id=user_id,
        name=name.strip(),
        purpose=purpose.strip(),
        nominal=nominal_value,
        category_id=category_id,
        attachments=attachments,
    )
    if not updated:
        return RedirectResponse(url=f"/user/submission/{submission_id}", status_code=302)

    return RedirectResponse(url=f"/user/submission/{submission_id}?revised=1", status_code=302)

@router.get("/profile")
async def profile_page(request: Request, db: Session = Depends(get_db)):
    """Render user profile page."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    user = auth_service.get_user_by_id(db, user_id)
    if not user:
        return RedirectResponse(url="/logout", status_code=302)
    
    # Stats for profile
    stats = submission_service.get_submission_stats_for_user(db, user_id)
    notifications = notification_service.get_unread_notifications(db, user_id)

    return templates.TemplateResponse("user/profile.html", {
        "request": request,
        "user": user,
        "stats": stats,
        "notifications": notifications,
        "session": request.session,
    })

@router.post("/profile/update")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    current_password: str = Form(None),
    new_password: str = Form(None),
    db: Session = Depends(get_db)
):
    """Update user profile information."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    user = auth_service.get_user_by_id(db, user_id)
    
    # Simple profile update
    user.full_name = full_name.strip()
    user.email = email.strip()
    request.session["full_name"] = user.full_name
    
    # Password change logic
    error = None
    if current_password and new_password:
        if auth_service.verify_password(current_password, user.password_hash):
            user.password_hash = auth_service.get_password_hash(new_password)
        else:
            error = "Current password incorrect"
            
    db.commit()
    
    if error:
        return RedirectResponse(url=f"/user/profile?error={error}", status_code=302)
        
    return RedirectResponse(url="/user/profile?updated=1", status_code=302)
