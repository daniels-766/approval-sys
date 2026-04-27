import os

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
