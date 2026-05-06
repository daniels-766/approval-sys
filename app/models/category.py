from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.utils.time_utils import get_now_naive


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=get_now_naive, onupdate=get_now_naive
    )

    # Relationships
    submissions = relationship("Submission", back_populates="category")

    def __repr__(self):
        return f"<Category {self.name}>"
