from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, Table, Column, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.utils.time_utils import get_now_naive


class UserDivision(Base):
    __tablename__ = "user_divisions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    division_id: Mapped[int] = mapped_column(ForeignKey("divisions.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")

    user = relationship("User", back_populates="division_associations")
    division = relationship("Division", back_populates="user_associations")


class Division(Base):
    __tablename__ = "divisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=get_now_naive, onupdate=get_now_naive
    )

    # Many-to-many relationship
    users = relationship("User", secondary="user_divisions", back_populates="divisions", viewonly=True)
    user_associations = relationship("UserDivision", back_populates="division")

    def __repr__(self):
        return f"<Division {self.name}>"
