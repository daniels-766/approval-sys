import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Category, Submission, SubmissionAttachment, SubmissionAudit, User, ApprovalStep  # noqa: F401
from app.routes import admin, auth, user, approver, finance
from app.services.auth_service import create_user, get_user_by_username


app = FastAPI(title="Approval System", version="1.0.0")

os.makedirs("app/static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


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

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(approver.router)
app.include_router(finance.router)


@app.on_event("startup")
def on_startup():
    """Create tables, apply tiny schema compatibility updates, and seed admin."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        if engine.dialect.name == "mysql":
            # Ensure status column type/default is compatible
            conn.execute(
                text(
                    "ALTER TABLE submissions "
                    "MODIFY status VARCHAR(30) NOT NULL DEFAULT 'pending'"
                )
            )
            # Expand user role enum for MySQL if needed.
            conn.execute(
                text(
                    "ALTER TABLE users "
                    "MODIFY role ENUM('user','approver','admin','finance') NOT NULL DEFAULT 'user'"
                )
            )

            def _mysql_has_column(table: str, col: str) -> bool:
                return bool(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
                        ),
                        {"t": table, "c": col},
                    ).scalar()
                )

            if not _mysql_has_column("submissions", "current_step"):
                conn.execute(text("ALTER TABLE submissions ADD COLUMN current_step INT NOT NULL DEFAULT 1"))
            if not _mysql_has_column("submissions", "paid_by"):
                conn.execute(text("ALTER TABLE submissions ADD COLUMN paid_by INT NULL"))
            if not _mysql_has_column("submissions", "paid_at"):
                conn.execute(text("ALTER TABLE submissions ADD COLUMN paid_at DATETIME NULL"))
            if not _mysql_has_column("submissions", "payment_notes"):
                conn.execute(text("ALTER TABLE submissions ADD COLUMN payment_notes TEXT NULL"))
            if not _mysql_has_column("submission_audits", "step_no"):
                conn.execute(text("ALTER TABLE submission_audits ADD COLUMN step_no INT NULL"))
            if not _mysql_has_column("submission_attachments", "kind"):
                conn.execute(
                    text(
                        "ALTER TABLE submission_attachments "
                        "ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'submission'"
                    )
                )

        if engine.dialect.name == "sqlite":
            # Add new columns if missing (SQLite supports ADD COLUMN).
            def _sqlite_has_column(table: str, col: str) -> bool:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                return any(r[1] == col for r in rows)

            if not _sqlite_has_column("submissions", "current_step"):
                conn.execute(text("ALTER TABLE submissions ADD COLUMN current_step INTEGER NOT NULL DEFAULT 1"))
            if not _sqlite_has_column("submissions", "paid_by"):
                conn.execute(text("ALTER TABLE submissions ADD COLUMN paid_by INTEGER NULL"))
            if not _sqlite_has_column("submissions", "paid_at"):
                conn.execute(text("ALTER TABLE submissions ADD COLUMN paid_at DATETIME NULL"))
            if not _sqlite_has_column("submissions", "payment_notes"):
                conn.execute(text("ALTER TABLE submissions ADD COLUMN payment_notes TEXT NULL"))
            if not _sqlite_has_column("submission_audits", "step_no"):
                conn.execute(text("ALTER TABLE submission_audits ADD COLUMN step_no INTEGER NULL"))
            if not _sqlite_has_column("submission_attachments", "kind"):
                conn.execute(
                    text(
                        "ALTER TABLE submission_attachments "
                        "ADD COLUMN kind TEXT NOT NULL DEFAULT 'submission'"
                    )
                )

            # Users.role Enum in SQLite is implemented as a CHECK constraint on existing DBs.
            # If the existing constraint doesn't include new roles, recreate the users table.
            users_ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
            ).scalar()
            if users_ddl and "CHECK" in users_ddl and "approver" not in users_ddl:
                conn.execute(text("PRAGMA foreign_keys=OFF"))
                conn.execute(text("ALTER TABLE users RENAME TO users_old"))
                conn.execute(
                    text(
                        "CREATE TABLE users ("
                        "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                        "username VARCHAR(50) NOT NULL UNIQUE, "
                        "email VARCHAR(100) NOT NULL UNIQUE, "
                        "password_hash VARCHAR(255) NOT NULL, "
                        "full_name VARCHAR(100) NOT NULL, "
                        "role VARCHAR(20) NOT NULL DEFAULT 'user', "
                        "is_active BOOLEAN NOT NULL DEFAULT 1, "
                        "created_at DATETIME, "
                        "updated_at DATETIME"
                        ")"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO users (id, username, email, password_hash, full_name, role, is_active, created_at, updated_at) "
                        "SELECT id, username, email, password_hash, full_name, role, is_active, created_at, updated_at "
                        "FROM users_old"
                    )
                )
                conn.execute(text("DROP TABLE users_old"))
                conn.execute(text("PRAGMA foreign_keys=ON"))

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

        # Ensure default approval steps exist for all categories.
        categories = db.query(Category).all()
        for cat in categories:
            existing = db.query(ApprovalStep).filter(ApprovalStep.category_id == cat.id).count()
            if existing == 0:
                db.add(ApprovalStep(category_id=cat.id, step_no=1, required_role="approver"))
                db.add(ApprovalStep(category_id=cat.id, step_no=2, required_role="admin"))
        db.commit()
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
        if role == "approver":
            return RedirectResponse(url="/approver/dashboard", status_code=302)
        if role == "finance":
            return RedirectResponse(url="/finance/dashboard", status_code=302)
        return RedirectResponse(url="/user/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)
