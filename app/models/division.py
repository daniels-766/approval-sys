from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, Table, Column, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


# Many-to-many association table
user_divisions = Table(
    "user_divisions",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("division_id", Integer, ForeignKey("divisions.id"), primary_key=True),
)


class Division(Base):
    __tablename__ = "divisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Many-to-many relationship
    users = relationship("User", secondary=user_divisions, back_populates="divisions")

    def __repr__(self):
        return f"<Division {self.name}>"
