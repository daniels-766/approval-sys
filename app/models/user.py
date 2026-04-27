from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        SAEnum("user", "admin", name="user_role"), default="user", server_default="user"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    submissions = relationship("Submission", back_populates="user", foreign_keys="Submission.user_id")
    reviewed_submissions = relationship(
        "Submission", back_populates="reviewer", foreign_keys="Submission.reviewed_by"
    )
    divisions = relationship("Division", secondary="user_divisions", back_populates="users")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
