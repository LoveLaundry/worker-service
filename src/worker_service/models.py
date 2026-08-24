from sqlalchemy import String, Integer, Float, JSON, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    worker_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    department: Mapped[str] = mapped_column(String, nullable=False, default="GENERAL")
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    joined_date: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    updated_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


class DailyTaskLog(Base):
    __tablename__ = "daily_task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    worker_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    department: Mapped[str] = mapped_column(String, nullable=False, default="GENERAL")
    shift: Mapped[str] = mapped_column(String, nullable=False, default="FULL_DAY")
    attendance_status: Mapped[str] = mapped_column(String, nullable=False, default="PRESENT")
    check_in_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    check_out_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    overtime_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Work breakdown
    washed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pressed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    packed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_weight_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Detailed task entries [{task_type, description, quantity, unit}]
    tasks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Quality tracking
    rewash_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    damaged_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    complaints: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_notes: Mapped[str | None] = mapped_column(String, nullable=True)

    # Equipment / consumables / misc
    machines_used: Mapped[str | None] = mapped_column(String, nullable=True)
    chemicals_used: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    performance_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    updated_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
