import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Category, Submission, SubmissionAttachment, SubmissionAudit, User  # noqa: F401
from app.routes import admin, auth, user
from app.services.auth_service import create_user, get_user_by_username


app = FastAPI(title="Approval System", version="1.0.0")

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

os.makedirs("app/static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(admin.router)


@app.middleware("http")
async def session_timeout_middleware(request: Request, call_next):
    """Auto logout after 5 minutes of inactivity."""
    # Skip for login/logout and static files
    path = request.url.path
    if path.startswith("/static") or path in ["/login", "/logout", "/register"]:
        return await call_next(request)

    TIMEOUT_SECONDS = 300  # 5 minutes
    user_id = request.session.get("user_id")

    if user_id:
        last_activity = request.session.get("last_activity")
        current_time = time.time()

        if last_activity:
            elapsed_time = current_time - float(last_activity)
            if elapsed_time > TIMEOUT_SECONDS:
                request.session.clear()
                # If it's an AJAX request (like the notification read), return 401
                if "application/json" in request.headers.get("accept", ""):
                    from fastapi.responses import JSONResponse
                    return JSONResponse({"detail": "Session expired"}, status_code=401)
                return RedirectResponse(url="/login?error=Session expired due to inactivity", status_code=302)

        # Update last activity time
        request.session["last_activity"] = current_time

    response = await call_next(request)
    return response


app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)


@app.on_event("startup")
def on_startup():
    """Create tables, apply tiny schema compatibility updates, and seed admin."""
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "mysql":
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE submissions "
                    "MODIFY status VARCHAR(30) NOT NULL DEFAULT 'pending'"
                )
            )

    db = SessionLocal()
    try:
        if not get_user_by_username(db, "admin"):
            create_user(
                db,
                username="admin",
                email="admin@system.local",
                password="admin123",
                full_name="Administrator",
                role="admin",
            )
            print("[STARTUP] Default admin created - username: admin / password: admin123")
        else:
            print("[STARTUP] Admin user already exists")
    finally:
        db.close()


@app.get("/")
async def root(request: Request):
    """Redirect to login or dashboard based on session."""
    user_id = request.session.get("user_id")
    if user_id:
        role = request.session.get("role", "user")
        if role == "admin":
            return RedirectResponse(url="/admin/dashboard", status_code=302)
        return RedirectResponse(url="/user/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)
