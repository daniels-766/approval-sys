from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.models.user import User

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
