from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import auth_service

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
async def login_page(request: Request):
    """Render login page."""
    # If already logged in, redirect
    user_id = request.session.get("user_id")
    if user_id:
        role = request.session.get("role", "user")
        if role == "admin":
            return RedirectResponse(url="/admin/dashboard", status_code=302)
        return RedirectResponse(url="/user/dashboard", status_code=302)

    return templates.TemplateResponse("auth/login.html", {
        "request": request,
        "error": None,
    })


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Authenticate user and create session."""
    user = auth_service.authenticate_user(db, username.strip(), password)
    if not user:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Invalid username or password",
        })

    # Set session
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["full_name"] = user.full_name
    request.session["role"] = user.role

    if user.role == "admin":
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    return RedirectResponse(url="/user/dashboard", status_code=302)


@router.get("/register")
async def register_page(request: Request):
    """Render registration page."""
    return templates.TemplateResponse("auth/register.html", {
        "request": request,
        "error": None,
    })


@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    full_name: str = Form(...),
    db: Session = Depends(get_db),
):
    """Register a new user."""
    # Validation
    if password != confirm_password:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "Passwords do not match",
        })

    if len(password) < 6:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "Password must be at least 6 characters",
        })

    if auth_service.get_user_by_username(db, username.strip()):
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "Username already exists",
        })

    if auth_service.get_user_by_email(db, email.strip()):
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "Email already registered",
        })

    # Create user
    auth_service.create_user(
        db,
        username=username.strip(),
        email=email.strip(),
        password=password,
        full_name=full_name.strip(),
        role="user",
    )

    return RedirectResponse(url="/login?registered=1", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
