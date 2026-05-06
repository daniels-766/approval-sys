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
from app.models.division import Division, UserDivision
from app.models.submission import Submission, SubmissionAttachment, SubmissionAudit
from app.models.approval_step import ApprovalStep
from app.models.user import User
from app.config import settings
from app.services import notification_service
from app.utils.time_utils import get_now_naive


VALID_STATUSES = ("pending", "need_revision", "approved", "rejected", "paid")
# test


def _generate_submission_code(db: Session) -> str:
    """Generate a unique submission code like SUB-20260427-001."""
    today = get_now_naive().strftime("%Y%m%d")
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
    step_no: int | None = None,
    notes: str | None = None,
) -> SubmissionAudit:
    audit = SubmissionAudit(
        submission=submission,
        actor_id=actor_id,
        action=action,
        status_from=status_from,
        status_to=status_to,
        step_no=step_no,
        notes=notes,
    )
    db.add(audit)
    return audit


def get_approval_steps_for_category(db: Session, category_id: int) -> list[ApprovalStep]:
    return (
        db.query(ApprovalStep)
        .filter(ApprovalStep.category_id == category_id)
        .order_by(ApprovalStep.step_no.asc())
        .all()
    )


def get_user_role_in_division(db: Session, user_id: int, division_id: int) -> str:
    """Get the specific role of a user within a division."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return "user"
    
    # Admins, Finance, and Global Approvers are respected across all divisions
    if user.role in ("admin", "finance", "approver"):
        return user.role
        
    assoc = db.query(UserDivision).filter(
        UserDivision.user_id == user_id,
        UserDivision.division_id == division_id
    ).first()
    
    return assoc.role if assoc else "user"


def get_total_steps_for_submission(db: Session, submission: Submission) -> int:
    # Special routing requested:
    # - If requester is a "user": only "approver" approves (single-step).
    # - If requester is an "approver": "admin" approves (single-step).
    # This keeps the workflow predictable and prevents self-approval loops.
    try:
        requester_role = submission.user.role if submission.user else None
    except Exception:
        requester_role = None
    if requester_role in ("user", "approver"):
        return 1

    steps = get_approval_steps_for_category(db, submission.category_id)
    return len(steps) if steps else 1


def get_required_role_for_submission_step(db: Session, submission: Submission) -> str:
    # Special routing requested:
    # - requester "user"  -> required approver role is "approver"
    # - requester "approver" -> required approver role is "admin"
    # This overrides category-based workflow.
    
    # Get the division of the submission
    division_id = submission.division_id
    if not division_id and submission.category:
        division_id = submission.category.division_id
    
    # Fallback: if no division is associated with submission/category, use requester's first division
    if not division_id and submission.user and submission.user.divisions:
        division_id = submission.user.divisions[0].id
        
    requester_role = get_user_role_in_division(db, submission.user_id, division_id or 0)

    if requester_role == "user":
        return "approver"
    if requester_role == "approver":
        return "admin"

    steps = get_approval_steps_for_category(db, submission.category_id)
    if not steps:
        return "admin"
    for step in steps:
        if step.step_no == submission.current_step:
            return step.required_role
    # If config is incomplete, default to admin for safety.
    return "admin"


def can_user_act_on_submission(db: Session, submission: Submission, actor: User, action: str) -> bool:
    """
    Staff actions:
      - approve/reject/revision: only when submission.status == 'pending'
      - pay: only when status == 'approved'
    """
    if action in ("approve", "reject", "revision"):
        if submission.status != "pending":
            return False
            
        required = get_required_role_for_submission_step(db, submission)
        
        # Global Admin override
        if actor.role == "admin":
            return True
            
        # Check actor's role in the specific division of the submission
        division_id = submission.division_id
        if not division_id and submission.category:
            division_id = submission.category.division_id
            
        # Fallback: if no division is associated, use requester's first division
        if not division_id and submission.user and submission.user.divisions:
            division_id = submission.user.divisions[0].id
            
        actor_role = get_user_role_in_division(db, actor.id, division_id or 0)
        
        return actor_role == required
        
    if action == "pay":
        return actor.role in ("finance", "admin") and submission.status == "approved"
    return False


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
    # Get division_id from category
    from app.models.category import Category
    category = db.query(Category).filter(Category.id == category_id).first()
    division_id = category.division_id if category else None
    if not division_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.divisions:
            division_id = user.divisions[0].id

    submission = Submission(
        submission_code=code,
        user_id=user_id,
        name=name,
        purpose=purpose,
        nominal=nominal,
        category_id=category_id,
        division_id=division_id,
        document_path=document_path,
        document_original_name=document_original_name,
    )
    submission.attachments = [
        SubmissionAttachment(
            file_path=file_path,
            original_name=original_name,
            kind="submission",
        )
        for file_path, original_name in attachment_pairs
    ]
    db.add(submission)
    _add_audit(db, submission, "created", None, "pending", actor_id=user_id, step_no=1)
    db.commit()
    db.refresh(submission)
    
    # Notify the correct reviewer based on requester role.
    required_role = get_required_role_for_submission_step(db, submission)
    review_link = "/admin/submission/{0}".format(submission.id)
    if required_role == "approver":
        review_link = "/approver/submission/{0}".format(submission.id)
    notification_service.notify_roles(
        db,
        roles=(required_role,) if required_role == "admin" else (required_role, "admin"),
        title="New Submission",
        message=f"{submission.user.full_name} has created a new submission: {submission.name}",
        link=review_link,
        type="info",
        submission_code=submission.submission_code,
    )

    # Email confirmation for the requester.
    notification_service.create_notification_with_email(
        db,
        user_id=submission.user_id,
        title="Request Submitted",
        message=f"Your request {submission.submission_code} has been submitted successfully.",
        link=f"/user/submission/{submission.id}",
        type="success",
        submission_code=submission.submission_code,
    )
    
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
        query = query.filter(Submission.division_id == division_id)
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
    """Approve a submission (multi-step)."""
    submission = get_submission_by_id(db, submission_id)
    actor = db.query(User).filter(User.id == admin_id).first()
    if not submission or not actor or not can_user_act_on_submission(db, submission, actor, "approve"):
        return None

    previous_status = submission.status
    current_step = submission.current_step
    total_steps = get_total_steps_for_submission(db, submission)

    submission.reviewed_by = admin_id
    submission.reviewed_at = get_now_naive()
    submission.admin_notes = notes

    if current_step < total_steps:
        # Move forward to next step, still pending overall.
        submission.current_step = current_step + 1
        submission.status = "pending"
        _add_audit(
            db,
            submission,
            "approved_step",
            previous_status,
            "pending",
            actor_id=admin_id,
            step_no=current_step,
            notes=notes,
        )
        db.commit()
        db.refresh(submission)

        # Notify next reviewers based on required role for next step.
        next_required = get_required_role_for_submission_step(db, submission)
        next_link = "/admin/submission/{0}".format(submission.id)
        if next_required == "approver":
            next_link = "/approver/submission/{0}".format(submission.id)
        notification_service.notify_roles(
            db,
            roles=(next_required, "admin") if next_required != "admin" else ("admin",),
            title="Submission Needs Review",
            message=f"{submission.submission_code} is ready for step {submission.current_step} review.",
            link=next_link,
            type="info",
            submission_code=submission.submission_code,
        )
        return submission

    # Final approval
    submission.status = "approved"
    _add_audit(
        db,
        submission,
        "approved_final",
        previous_status,
        "approved",
        actor_id=admin_id,
        step_no=current_step,
        notes=notes,
    )
    # Add an explicit "waiting for payment" milestone for the timeline, once.
    existing_wait = (
        db.query(SubmissionAudit)
        .filter(SubmissionAudit.submission_id == submission.id, SubmissionAudit.action == "waiting_payment")
        .first()
    )
    if not existing_wait:
        _add_audit(
            db,
            submission,
            "waiting_payment",
            "approved",
            "approved",
            actor_id=None,
            step_no=None,
            notes="Waiting for payment",
        )
    db.commit()
    db.refresh(submission)

    # Notify User
    notification_service.create_notification_with_email(
        db,
        user_id=submission.user_id,
        title="Submission Approved",
        message=f"Your submission {submission.submission_code} has been approved.",
        link=f"/user/submission/{submission.id}",
        type="success",
        submission_code=submission.submission_code,
    )

    # Notify Finance that payment can be processed.
    notification_service.notify_roles(
        db,
        roles=("finance",),
        title="Payment Needed",
        message=f"{submission.submission_code} has been approved and is ready for payment.",
        link=f"/finance/submission/{submission.id}",
        type="warning",
        submission_code=submission.submission_code,
    )
    return submission


def reject_submission(
    db: Session, submission_id: int, admin_id: int, notes: str | None = None
) -> Submission | None:
    """Reject a submission (at current step)."""
    submission = get_submission_by_id(db, submission_id)
    actor = db.query(User).filter(User.id == admin_id).first()
    if not submission or not actor or not can_user_act_on_submission(db, submission, actor, "reject"):
        return None
    previous_status = submission.status
    submission.status = "rejected"
    submission.reviewed_by = admin_id
    submission.reviewed_at = get_now_naive()
    submission.admin_notes = notes
    _add_audit(
        db,
        submission,
        "rejected",
        previous_status,
        "rejected",
        actor_id=admin_id,
        step_no=submission.current_step,
        notes=notes,
    )
    db.commit()
    db.refresh(submission)

    # Notify User
    notification_service.create_notification_with_email(
        db,
        user_id=submission.user_id,
        title="Submission Rejected",
        message=f"Your submission {submission.submission_code} has been rejected.",
        link=f"/user/submission/{submission.id}",
        type="danger",
        submission_code=submission.submission_code,
    )
    return submission


def request_revision_submission(
    db: Session, submission_id: int, admin_id: int, notes: str | None = None
) -> Submission | None:
    """Ask the submitter to revise a pending submission."""
    submission = get_submission_by_id(db, submission_id)
    actor = db.query(User).filter(User.id == admin_id).first()
    if not submission or not actor or not can_user_act_on_submission(db, submission, actor, "revision"):
        return None
    previous_status = submission.status
    submission.status = "need_revision"
    submission.reviewed_by = admin_id
    submission.reviewed_at = get_now_naive()
    submission.admin_notes = notes
    _add_audit(
        db,
        submission,
        "need_revision",
        previous_status,
        "need_revision",
        actor_id=admin_id,
        step_no=submission.current_step,
        notes=notes,
    )
    db.commit()
    db.refresh(submission)

    # Notify User
    notification_service.create_notification_with_email(
        db,
        user_id=submission.user_id,
        title="Revision Requested",
        message=f"Admin requested a revision for {submission.submission_code}.",
        link=f"/user/submission/{submission.id}",
        type="warning",
        submission_code=submission.submission_code,
    )
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
    from app.models.category import Category
    category = db.query(Category).filter(Category.id == category_id).first()
    submission.category_id = category_id
    submission.division_id = category.division_id if category else None
    submission.status = "pending"
    submission.current_step = 1
    submission.reviewed_by = None
    submission.reviewed_at = None
    submission.admin_notes = None
    for file_path, original_name in attachments or []:
        submission.attachments.append(
            SubmissionAttachment(
                file_path=file_path,
                original_name=original_name,
                kind="submission",
            )
        )
    _add_audit(
        db,
        submission,
        "revised",
        previous_status,
        "pending",
        actor_id=user_id,
        step_no=1,
        notes="User submitted revisions",
    )
    db.commit()
    db.refresh(submission)

    # Notify the correct reviewer based on requester role.
    required_role = get_required_role_for_submission_step(db, submission)
    review_link = "/admin/submission/{0}".format(submission.id)
    if required_role == "approver":
        review_link = "/approver/submission/{0}".format(submission.id)
    notification_service.notify_roles(
        db,
        roles=(required_role,) if required_role == "admin" else (required_role, "admin"),
        title="Submission Revised",
        message=f"{submission.user.full_name} has submitted a revision for {submission.submission_code}",
        link=review_link,
        type="info",
        submission_code=submission.submission_code,
    )
    return submission


def pay_submission(
    db: Session,
    submission_id: int,
    actor_id: int,
    notes: str | None = None,
    attachments: list[tuple[str, str]] | None = None,
) -> Submission | None:
    """Mark an approved submission as paid (finance action)."""
    submission = get_submission_by_id(db, submission_id)
    actor = db.query(User).filter(User.id == actor_id).first()
    if not submission or not actor or not can_user_act_on_submission(db, submission, actor, "pay"):
        return None

    previous_status = submission.status
    submission.status = "paid"
    submission.paid_by = actor_id
    submission.paid_at = get_now_naive()
    submission.payment_notes = notes
    for file_path, original_name in attachments or []:
        submission.attachments.append(
            SubmissionAttachment(
                file_path=file_path,
                original_name=original_name,
                kind="payment",
            )
        )

    _add_audit(
        db,
        submission,
        "paid",
        previous_status,
        "paid",
        actor_id=actor_id,
        step_no=None,
        notes=notes,
    )
    db.commit()
    db.refresh(submission)

    notification_service.create_notification_with_email(
        db,
        user_id=submission.user_id,
        title="Payment Completed",
        message=f"Finance has marked {submission.submission_code} as paid.",
        link=f"/user/submission/{submission.id}",
        type="success",
        submission_code=submission.submission_code,
    )
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
    paid = (
        db.query(func.count(Submission.id))
        .filter(Submission.status == "paid")
        .scalar()
        or 0
    )
    return {
        "total": total,
        "pending": pending,
        "need_revision": need_revision,
        "approved": approved,
        "rejected": rejected,
        "paid": paid,
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
        "paid": query.filter(Submission.status == "paid").count(),
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


def delete_submission(db: Session, submission_id: int) -> bool:
    """Delete a submission and its associated files."""
    submission = get_submission_by_id(db, submission_id)
    if not submission:
        return False

    # Delete associated files
    from app.config import settings
    
    # Single document path (legacy/compat)
    if submission.document_path:
        file_path = os.path.join(settings.UPLOAD_DIR, submission.document_path)
        if os.path.exists(file_path):
            os.remove(file_path)

    # Multi attachments
    for attachment in submission.attachments:
        file_path = os.path.join(settings.UPLOAD_DIR, attachment.file_path)
        if os.path.exists(file_path):
            os.remove(file_path)

    # Delete from DB (cascades to audit and attachment records)
    db.delete(submission)
    db.commit()
    return True
def get_visual_stats(db: Session):
    """Get data for charts: monthly trends and category distribution."""
    # Monthly Trend (Last 6 months)
    # Note: SQLite specific date formatting, works for MySQL too if changed to %Y-%m
    if db.bind.dialect.name == "sqlite":
        monthly_query = db.query(
            func.strftime("%Y-%m", Submission.created_at).label("month"),
            func.count(Submission.id).label("count")
        ).group_by("month").order_by("month").limit(6).all()
    else:
        monthly_query = db.query(
            func.date_format(Submission.created_at, "%Y-%m").label("month"),
            func.count(Submission.id).label("count")
        ).group_by("month").order_by("month").limit(6).all()

    monthly_trend = {
        "labels": [row.month for row in monthly_query],
        "values": [row.count for row in monthly_query]
    }

    # Category Distribution (Top 5 categories by total nominal)
    category_query = db.query(
        Category.name,
        func.sum(Submission.nominal).label("total")
    ).join(Submission).filter(Submission.status == 'approved').group_by(Category.name).order_by(func.sum(Submission.nominal).desc()).limit(5).all()

    category_dist = {
        "labels": [row.name for row in category_query],
        "values": [float(row.total or 0) for row in category_query]
    }

    return {
        "monthly_trend": monthly_trend,
        "category_distribution": category_dist
    }

def get_submission_stats_for_user(db: Session, user_id: int):
    """Get submission statistics for a specific user."""
    return {
        "total": db.query(Submission).filter(Submission.user_id == user_id).count(),
        "pending": db.query(Submission).filter(Submission.user_id == user_id, Submission.status == "pending").count(),
        "need_revision": db.query(Submission).filter(Submission.user_id == user_id, Submission.status == "need_revision").count(),
        "approved": db.query(Submission).filter(Submission.user_id == user_id, Submission.status == "approved").count(),
        "rejected": db.query(Submission).filter(Submission.user_id == user_id, Submission.status == "rejected").count(),
    }
