from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# ─── Constants ────────────────────────────────────────────────────────────────

TASK_TYPES = [
    "WASHING",
    "PRESSING",
    "FOLDING",
    "PACKING",
    "DRY_CLEANING",
    "STAIN_TREATMENT",
    "MACHINE_CLEANING",
    "SORTING_TAGGING",
    "DELIVERY_SUPPORT",
    "MAINTENANCE",
    "OTHER",
]

TASK_UNITS = ["PIECES", "KG", "LOADS", "HOURS"]

DEPARTMENTS = [
    "WASHING",
    "PRESSING",
    "FINISHING",
    "PACKING",
    "DRY_CLEANING",
    "DELIVERY",
    "GENERAL",
]

SHIFTS = ["MORNING", "EVENING", "NIGHT", "FULL_DAY"]

ATTENDANCE_STATUSES = ["PRESENT", "HALF_DAY", "ABSENT", "ON_LEAVE"]


# ─── Task entries ─────────────────────────────────────────────────────────────


class TaskEntry(BaseModel):
    task_type: str = Field(..., description="One of TASK_TYPES")
    description: Optional[str] = None
    quantity: float = Field(0, ge=0)
    unit: str = Field("PIECES", description="One of TASK_UNITS")
    hours_spent: Optional[float] = Field(None, ge=0)
    gate_pass_id: Optional[str] = None
    gate_pass_number: Optional[str] = None
    remark: Optional[str] = None


# ─── Workers ──────────────────────────────────────────────────────────────────


class WorkerCreate(BaseModel):
    worker_name: str = Field(..., min_length=1)
    department: str = "GENERAL"
    phone: Optional[str] = None
    is_active: bool = True
    joined_date: Optional[str] = None
    notes: Optional[str] = None


class WorkerUpdate(BaseModel):
    worker_name: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    joined_date: Optional[str] = None
    notes: Optional[str] = None


class WorkerResponse(BaseModel):
    id: str | int
    worker_name: str
    department: str
    phone: Optional[str] = None
    is_active: bool = True
    joined_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ─── Daily task logs ──────────────────────────────────────────────────────────


class DailyLogCreate(BaseModel):
    work_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    worker_name: str
    department: str = "GENERAL"
    shift: str = "FULL_DAY"
    attendance_status: str = "PRESENT"
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    overtime_hours: float = Field(0.0, ge=0)
    washed_count: int = Field(0, ge=0)
    pressed_count: int = Field(0, ge=0)
    folded_count: int = Field(0, ge=0)
    packed_count: int = Field(0, ge=0)
    other_count: int = Field(0, ge=0)
    total_weight_kg: float = 0.0
    tasks: list[TaskEntry] = []
    rewash_count: int = Field(0, ge=0)
    damaged_items: int = Field(0, ge=0)
    complaints: int = Field(0, ge=0)
    quality_notes: Optional[str] = None
    machines_used: Optional[str] = None
    chemicals_used: Optional[str] = None
    notes: Optional[str] = None
    performance_rating: Optional[int] = Field(None, ge=1, le=5)


class DailyLogUpdate(BaseModel):
    work_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    worker_name: Optional[str] = None
    department: Optional[str] = None
    shift: Optional[str] = None
    attendance_status: Optional[str] = None
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    overtime_hours: Optional[float] = Field(None, ge=0)
    washed_count: Optional[int] = Field(None, ge=0)
    pressed_count: Optional[int] = Field(None, ge=0)
    folded_count: Optional[int] = Field(None, ge=0)
    packed_count: Optional[int] = Field(None, ge=0)
    other_count: Optional[int] = Field(None, ge=0)
    total_weight_kg: Optional[float] = None
    tasks: Optional[list[TaskEntry]] = None
    rewash_count: Optional[int] = Field(None, ge=0)
    damaged_items: Optional[int] = Field(None, ge=0)
    complaints: Optional[int] = Field(None, ge=0)
    quality_notes: Optional[str] = None
    machines_used: Optional[str] = None
    chemicals_used: Optional[str] = None
    notes: Optional[str] = None
    performance_rating: Optional[int] = Field(None, ge=1, le=5)


class DailyLogResponse(BaseModel):
    id: str | int
    work_date: str
    worker_name: str
    department: str
    shift: str
    attendance_status: str
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    overtime_hours: float = 0.0
    washed_count: int = 0
    pressed_count: int = 0
    folded_count: int = 0
    packed_count: int = 0
    other_count: int = 0
    total_weight_kg: float = 0.0
    tasks: list[TaskEntry] = []
    rewash_count: int = 0
    damaged_items: int = 0
    complaints: int = 0
    quality_notes: Optional[str] = None
    machines_used: Optional[str] = None
    chemicals_used: Optional[str] = None
    notes: Optional[str] = None
    performance_rating: Optional[int] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DailySummaryResponse(BaseModel):
    date: str
    workers_logged: int
    present: int
    absent: int
    on_leave: int
    half_day: int
    total_washed: int
    total_pressed: int
    total_folded: int
    total_packed: int
    total_other: int
    total_weight_kg: float
    total_overtime_hours: float
    total_rewash: int
    total_damaged: int
    total_complaints: int
