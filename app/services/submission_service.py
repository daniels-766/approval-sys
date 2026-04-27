import os
import string
import random
import csv
import io
from datetime import datetime
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from fastapi import UploadFile
from app.models.category import Category
from app.models.division import Division
from app.models.submission import Submission, SubmissionAttachment, SubmissionAudit
from app.models.user import User
from app.config import settings


VALID_STATUSES = ("pending", "need_revision", "approved", "rejected")


def _generate_submission_code(db: Session) -> str:
    """Generate a unique submission code like SUB-20260427-001."""
    today = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"SUB-{today}-"

    # Find the last submission code for today
    last = (
        db.query(Submission)
        .filter(Submission.submission_code.like(f"{prefix}%"))
        .order_by(Submission.id.desc())
        .first()
    )

    if last:
        last_num = int(last.submission_code.split("-")[-1])
        new_num = last_num + 1
    else:
        new_num = 1

    return f"{prefix}{new_num:03d}"


def _generate_random_filename(original_filename: str) -> str:
    """Generate a random 16-character filename preserving the original extension."""
    ext = os.path.splitext(original_filename)[1].lower()
    chars = string.ascii_letters + string.digits
    random_name = "".join(random.choices(chars, k=16))
    return f"{random_name}{ext}"


async def save_upload_file(file: UploadFile) -> tuple[str, str]:
    """Save uploaded file with a random 16-char filename. Returns (saved_path, original_name)."""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    original_name = file.filename or "unknown"
    saved_name = _generate_random_filename(original_name)
    file_path = os.path.join(settings.UPLOAD_DIR, saved_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    return saved_name, original_name


async def save_upload_files(files: list[UploadFile] | None) -> list[tuple[str, str]]:
    """Save multiple uploaded files and return saved/original name pairs."""
    saved_files = []
    for file in files or []:
        if file and file.filename:
            saved_files.append(await save_upload_file(file))
    return saved_files


def _add_audit(
    db: Session,
    submission: Submission,
    action: str,
    status_from: str | None,
    status_to: str | None,
    actor_id: int | None = None,
    notes: str | None = None,
) -> SubmissionAudit:
    audit = SubmissionAudit(
        submission=submission,
        actor_id=actor_id,
        action=action,
        status_from=status_from,
        status_to=status_to,
        notes=notes,
    )
    db.add(audit)
    return audit


def create_submission(
    db: Session,
    user_id: int,
    name: str,
    purpose: str,
    nominal: Decimal,
    category_id: int,
    document_path: str | None = None,
    document_original_name: str | None = None,
    attachments: list[tuple[str, str]] | None = None,
) -> Submission:
    """Create a new submission."""
    code = _generate_submission_code(db)
    attachment_pairs = list(attachments or [])
    if document_path and document_original_name:
        attachment_pairs.insert(0, (document_path, document_original_name))
    submission = Submission(
        submission_code=code,
        user_id=user_id,
        name=name,
        purpose=purpose,
        nominal=nominal,
        category_id=category_id,
        document_path=document_path,
        document_original_name=document_original_name,
    )
    submission.attachments = [
        SubmissionAttachment(file_path=file_path, original_name=original_name)
        for file_path, original_name in attachment_pairs
    ]
    db.add(submission)
    _add_audit(db, submission, "created", None, "pending", actor_id=user_id)
    db.commit()
    db.refresh(submission)
    return submission


def get_submissions_by_user(db: Session, user_id: int):
    """Get all submissions for a specific user."""
    return (
        db.query(Submission)
        .filter(Submission.user_id == user_id)
        .order_by(Submission.created_at.desc())
        .all()
    )


def get_all_submissions(
    db: Session,
    status_filter: str | None = None,
    keyword: str | None = None,
    category_id: int | None = None,
    division_id: int | None = None,
    user_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_nominal: Decimal | None = None,
    max_nominal: Decimal | None = None,
):
    """Get all submissions, optionally filtered by dashboard search criteria."""
    query = db.query(Submission)
    if status_filter and status_filter in VALID_STATUSES:
        query = query.filter(Submission.status == status_filter)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.join(Submission.user).filter(
            or_(
                Submission.submission_code.ilike(pattern),
                Submission.name.ilike(pattern),
                Submission.purpose.ilike(pattern),
                User.full_name.ilike(pattern),
                User.username.ilike(pattern),
            )
        )
    if category_id:
        query = query.filter(Submission.category_id == category_id)
    if division_id:
        query = query.join(Submission.user).join(User.divisions).filter(Division.id == division_id)
    if user_id:
        query = query.filter(Submission.user_id == user_id)
    if date_from:
        query = query.filter(func.date(Submission.created_at) >= date_from)
    if date_to:
        query = query.filter(func.date(Submission.created_at) <= date_to)
    if min_nominal is not None:
        query = query.filter(Submission.nominal >= min_nominal)
    if max_nominal is not None:
        query = query.filter(Submission.nominal <= max_nominal)
    return query.order_by(Submission.created_at.desc()).all()


def get_submission_by_id(db: Session, submission_id: int) -> Submission | None:
    """Get submission by ID."""
    return db.query(Submission).filter(Submission.id == submission_id).first()


def approve_submission(
    db: Session, submission_id: int, admin_id: int, notes: str | None = None
) -> Submission | None:
    """Approve a submission."""
    submission = get_submission_by_id(db, submission_id)
    if not submission or submission.status not in ("pending", "need_revision"):
        return None
    previous_status = submission.status
    submission.status = "approved"
    submission.reviewed_by = admin_id
    submission.reviewed_at = datetime.utcnow()
    submission.admin_notes = notes
    _add_audit(db, submission, "approved", previous_status, "approved", admin_id, notes)
    db.commit()
    db.refresh(submission)
    return submission


def reject_submission(
    db: Session, submission_id: int, admin_id: int, notes: str | None = None
) -> Submission | None:
    """Reject a submission."""
    submission = get_submission_by_id(db, submission_id)
    if not submission or submission.status not in ("pending", "need_revision"):
        return None
    previous_status = submission.status
    submission.status = "rejected"
    submission.reviewed_by = admin_id
    submission.reviewed_at = datetime.utcnow()
    submission.admin_notes = notes
    _add_audit(db, submission, "rejected", previous_status, "rejected", admin_id, notes)
    db.commit()
    db.refresh(submission)
    return submission


def request_revision_submission(
    db: Session, submission_id: int, admin_id: int, notes: str | None = None
) -> Submission | None:
    """Ask the submitter to revise a pending submission."""
    submission = get_submission_by_id(db, submission_id)
    if not submission or submission.status != "pending":
        return None
    previous_status = submission.status
    submission.status = "need_revision"
    submission.reviewed_by = admin_id
    submission.reviewed_at = datetime.utcnow()
    submission.admin_notes = notes
    _add_audit(
        db,
        submission,
        "need_revision",
        previous_status,
        "need_revision",
        admin_id,
        notes,
    )
    db.commit()
    db.refresh(submission)
    return submission


def revise_submission(
    db: Session,
    submission_id: int,
    user_id: int,
    name: str,
    purpose: str,
    nominal: Decimal,
    category_id: int,
    attachments: list[tuple[str, str]] | None = None,
) -> Submission | None:
    """Update a submission that is waiting for user revision and resubmit it."""
    submission = get_submission_by_id(db, submission_id)
    if (
        not submission
        or submission.user_id != user_id
        or submission.status != "need_revision"
    ):
        return None

    previous_status = submission.status
    submission.name = name
    submission.purpose = purpose
    submission.nominal = nominal
    submission.category_id = category_id
    submission.status = "pending"
    submission.reviewed_by = None
    submission.reviewed_at = None
    submission.admin_notes = None
    for file_path, original_name in attachments or []:
        submission.attachments.append(
            SubmissionAttachment(file_path=file_path, original_name=original_name)
        )
    _add_audit(
        db,
        submission,
        "revised",
        previous_status,
        "pending",
        actor_id=user_id,
        notes="User submitted revisions",
    )
    db.commit()
    db.refresh(submission)
    return submission


def get_submission_stats(db: Session) -> dict:
    """Get submission statistics for admin dashboard."""
    total = db.query(func.count(Submission.id)).scalar() or 0
    pending = (
        db.query(func.count(Submission.id))
        .filter(Submission.status == "pending")
        .scalar()
        or 0
    )
    approved = (
        db.query(func.count(Submission.id))
        .filter(Submission.status == "approved")
        .scalar()
        or 0
    )
    rejected = (
        db.query(func.count(Submission.id))
        .filter(Submission.status == "rejected")
        .scalar()
        or 0
    )
    need_revision = (
        db.query(func.count(Submission.id))
        .filter(Submission.status == "need_revision")
        .scalar()
        or 0
    )
    return {
        "total": total,
        "pending": pending,
        "need_revision": need_revision,
        "approved": approved,
        "rejected": rejected,
    }


def get_user_submission_stats(db: Session, user_id: int) -> dict:
    """Get submission statistics for one user dashboard."""
    query = db.query(Submission).filter(Submission.user_id == user_id)
    return {
        "total": query.count(),
        "pending": query.filter(Submission.status == "pending").count(),
        "need_revision": query.filter(Submission.status == "need_revision").count(),
        "approved": query.filter(Submission.status == "approved").count(),
        "rejected": query.filter(Submission.status == "rejected").count(),
    }


def export_submissions_csv(submissions: list[Submission]) -> str:
    """Export submissions to a CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "code",
            "submitted_by",
            "name",
            "category",
            "nominal",
            "status",
            "created_at",
            "reviewed_by",
            "reviewed_at",
            "notes",
        ],
    )
    writer.writeheader()
    for submission in submissions:
        writer.writerow(
            {
                "code": submission.submission_code,
                "submitted_by": submission.user.full_name if submission.user else "",
                "name": submission.name,
                "category": submission.category.name if submission.category else "",
                "nominal": str(submission.nominal),
                "status": submission.status,
                "created_at": submission.created_at.isoformat()
                if submission.created_at
                else "",
                "reviewed_by": submission.reviewer.full_name
                if submission.reviewer
                else "",
                "reviewed_at": submission.reviewed_at.isoformat()
                if submission.reviewed_at
                else "",
                "notes": submission.admin_notes or "",
            }
        )
    return output.getvalue()
