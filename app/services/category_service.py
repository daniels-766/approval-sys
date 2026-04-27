from sqlalchemy.orm import Session
from app.models.category import Category


def get_all_categories(db: Session, active_only: bool = False):
    """Get all categories, optionally filtered by active status."""
    query = db.query(Category)
    if active_only:
        query = query.filter(Category.is_active == True)
    return query.order_by(Category.name).all()


def get_category_by_id(db: Session, category_id: int) -> Category | None:
    """Get category by ID."""
    return db.query(Category).filter(Category.id == category_id).first()


def create_category(db: Session, name: str, description: str | None = None) -> Category:
    """Create a new category."""
    category = Category(name=name, description=description)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def update_category(
    db: Session,
    category_id: int,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> Category | None:
    """Update an existing category."""
    category = get_category_by_id(db, category_id)
    if not category:
        return None
    if name is not None:
        category.name = name
    if description is not None:
        category.description = description
    if is_active is not None:
        category.is_active = is_active
    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: int) -> bool:
    """Soft-delete a category by setting is_active to False."""
    category = get_category_by_id(db, category_id)
    if not category:
        return False
    category.is_active = False
    db.commit()
    return True
