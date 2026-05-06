from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.time_utils import get_now_naive


class ApprovalStep(Base):
    __tablename__ = "approval_steps"
    __table_args__ = (
        UniqueConstraint("category_id", "step_no", name="uq_approval_steps_category_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False, index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    required_role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now_naive)

    category = relationship("Category")

    def __repr__(self) -> str:
        return f"<ApprovalStep category={self.category_id} step={self.step_no} role={self.required_role}>"

