from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.utils.time_utils import get_now_naive


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    nominal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False, index=True)
    document_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        server_default="pending",
        index=True,
    )
    current_step: Mapped[int] = mapped_column(
        default=1,
        server_default="1",
        index=True,
    )
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    paid_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    payment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now_naive, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=get_now_naive, onupdate=get_now_naive
    )

    # Relationships
    user = relationship("User", back_populates="submissions", foreign_keys=[user_id])
    reviewer = relationship(
        "User", back_populates="reviewed_submissions", foreign_keys=[reviewed_by]
    )
    payer = relationship("User", foreign_keys=[paid_by])
    category = relationship("Category", back_populates="submissions")
    attachments = relationship(
        "SubmissionAttachment",
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="SubmissionAttachment.id",
    )
    audit_entries = relationship(
        "SubmissionAudit",
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="SubmissionAudit.created_at",
    )

    def __repr__(self):
        return f"<Submission {self.submission_code} - {self.status}>"


class SubmissionAttachment(Base):
    __tablename__ = "submission_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "submission" (request attachments) or "payment" (finance proof).
    kind: Mapped[str] = mapped_column(
        String(20),
        default="submission",
        server_default="submission",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now_naive)

    submission = relationship("Submission", back_populates="attachments")


class SubmissionAudit(Base):
    __tablename__ = "submission_audits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    step_no: Mapped[int | None] = mapped_column(nullable=True, index=True)
    status_from: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status_to: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now_naive)

    submission = relationship("Submission", back_populates="audit_entries")
    actor = relationship("User")
