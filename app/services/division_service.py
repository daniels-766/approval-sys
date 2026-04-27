from sqlalchemy.orm import Session
from app.models.division import Division
from app.models.user import User


def get_all_divisions(db: Session, active_only: bool = False):
    """Get all divisions, optionally filtered by active status."""
    query = db.query(Division)
    if active_only:
        query = query.filter(Division.is_active == True)
    return query.order_by(Division.name).all()


def get_division_by_id(db: Session, division_id: int) -> Division | None:
    """Get division by ID."""
    return db.query(Division).filter(Division.id == division_id).first()


def create_division(db: Session, name: str, description: str | None = None) -> Division:
    """Create a new division."""
    division = Division(name=name, description=description)
    db.add(division)
    db.commit()
    db.refresh(division)
    return division


def update_division(
    db: Session,
    division_id: int,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> Division | None:
    """Update an existing division."""
    division = get_division_by_id(db, division_id)
    if not division:
        return None
    if name is not None:
        division.name = name
    if description is not None:
        division.description = description
    if is_active is not None:
        division.is_active = is_active
    db.commit()
    db.refresh(division)
    return division


def assign_users_to_division(
    db: Session, division_id: int, user_ids: list[int]
) -> Division | None:
    """Replace the users assigned to a division."""
    division = get_division_by_id(db, division_id)
    if not division:
        return None

    users = db.query(User).filter(User.id.in_(user_ids)).order_by(User.username).all()
    division.users = users
    db.commit()
    db.refresh(division)
    return division


def delete_division(db: Session, division_id: int) -> bool:
    """Soft-delete a division by setting is_active to False."""
    division = get_division_by_id(db, division_id)
    if not division:
        return False
    division.is_active = False
    db.commit()
    return True
