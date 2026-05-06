import bcrypt
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.division import Division, UserDivision
from app.models.user import User


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Authenticate user by username and password. Returns User or None."""
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    full_name: str,
    role: str = "user",
    division_roles: dict[int, str] | None = None,
) -> User:
    """Create a new user with optional division-specific roles."""
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    db.flush()  # To get user.id

    if division_roles:
        for div_id, div_role in division_roles.items():
            assoc = UserDivision(user_id=user.id, division_id=div_id, role=div_role)
            db.add(assoc)

    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Get user by ID."""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> User | None:
    """Get user by username."""
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    """Get user by email."""
    return db.query(User).filter(User.email == email).first()


def get_all_users(
    db: Session,
    keyword: str | None = None,
    role: str | None = None,
    active: bool | None = None,
):
    """Get users with optional search/filter criteria."""
    query = db.query(User)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                User.username.ilike(pattern),
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )
    if role in ("user", "approver", "admin", "finance"):
        query = query.filter(User.role == role)
    if active is not None:
        query = query.filter(User.is_active == active)
    return query.order_by(User.full_name).all()


def update_user(
    db: Session,
    user_id: int,
    username: str,
    email: str,
    full_name: str,
    role: str,
    is_active: bool,
    division_roles: dict[int, str] | None = None, # {division_id: role}
) -> User | None:
    """Update user profile, access, and division assignments with specific roles."""
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    user.username = username
    user.email = email
    user.full_name = full_name
    user.role = role if role in ("user", "approver", "admin", "finance") else "user"
    user.is_active = is_active

    if division_roles is not None:
        # Clear existing associations
        db.query(UserDivision).filter(UserDivision.user_id == user_id).delete()
        
        # Add new associations
        for div_id, div_role in division_roles.items():
            assoc = UserDivision(user_id=user_id, division_id=div_id, role=div_role)
            db.add(assoc)

    db.commit()
    db.refresh(user)
    return user


def reset_user_password(db: Session, user_id: int, password: str) -> User | None:
    """Reset a user's password."""
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    user.password_hash = hash_password(password)
    db.commit()
    db.refresh(user)
    return user
