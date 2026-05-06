from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.models.user import User
from app.services import email_service

def create_notification(db: Session, user_id: int, title: str, message: str, link: str = None, type: str = "info"):
    """Create a new notification for a user."""
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        link=link,
        type=type
    )
    db.add(notif)
    db.commit()
    return notif


def create_notification_with_email(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    link: str | None = None,
    type: str = "info",
    submission_code: str | None = None,
):
    """Create in-app notification and (optionally) send email to that user."""
    notif = create_notification(db, user_id, title, message, link=link, type=type)
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.email:
        subject, body_text, body_html = email_service.build_submission_email(
            title=title,
            message=message,
            link=link,
            submission_code=submission_code,
        )
        email_service.send_email_async([user.email], subject, body_text, body_html=body_html)
    return notif

def notify_all_admins(db: Session, title: str, message: str, link: str = None, type: str = "info"):
    """Send notification to all admin users."""
    admins = db.query(User).filter(User.role == "admin").all()
    for admin in admins:
        notif = Notification(
            user_id=admin.id,
            title=title,
            message=message,
            link=link,
            type=type
        )
        db.add(notif)
    db.commit()


def notify_roles(
    db: Session,
    roles: tuple[str, ...],
    title: str,
    message: str,
    link: str | None = None,
    type: str = "info",
    submission_code: str | None = None,
    division_id: int | None = None,
):
    """Send notification to all users having any of the given roles globally or in a specific division."""
    # Global role recipients
    recipients_query = db.query(User).filter(User.role.in_(list(roles)))
    global_recipients = recipients_query.all()
    
    # Division-specific role recipients
    division_recipients = []
    if division_id:
        from app.models.division import UserDivision
        division_recipients = (
            db.query(User)
            .join(User.division_associations)
            .filter(
                (UserDivision.division_id == division_id) &
                (UserDivision.role.in_(list(roles)))
            )
            .all()
        )
    
    # Combine and unique by ID
    recipient_map = {u.id: u for u in global_recipients}
    for u in division_recipients:
        recipient_map[u.id] = u
    
    recipients = list(recipient_map.values())

    for user in recipients:
        db.add(
            Notification(
                user_id=user.id,
                title=title,
                message=message,
                link=link,
                type=type,
            )
        )
    db.commit()

    # Email (fire-and-forget) to role recipients.
    emails = [u.email for u in recipients if getattr(u, "email", None)]
    if emails:
        subject, body_text, body_html = email_service.build_submission_email(
            title=title,
            message=message,
            link=link,
            submission_code=submission_code,
        )
        email_service.send_email_async(emails, subject, body_text, body_html=body_html)

def get_unread_notifications(db: Session, user_id: int, limit: int = 10):
    """Get unread notifications for a user."""
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )

def mark_all_as_read(db: Session, user_id: int):
    """Mark all notifications as read for a user."""
    db.query(Notification).filter(Notification.user_id == user_id, Notification.is_read == False).update({"is_read": True})
    db.commit()

def mark_as_read(db: Session, notification_id: int, user_id: int):
    """Mark a single notification as read."""
    notif = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user_id).first()
    if notif:
        notif.is_read = True
        db.commit()
        return True
    return False
