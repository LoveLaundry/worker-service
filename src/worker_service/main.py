from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime

from .config import DB_TYPE, DatabaseType
from .repository import WorkerRepository
from .repository_factory import get_repository, close_connections
from .schemas import (
    TASK_TYPES,
    TASK_UNITS,
    DEPARTMENTS,
    SHIFTS,
    ATTENDANCE_STATUSES,
    WorkerCreate,
    WorkerUpdate,
    WorkerResponse,
    DailyLogCreate,
    DailyLogUpdate,
    DailyLogResponse,
    DailySummaryResponse,
)
from .auth_helper import get_current_user, require_role
from .database.main_db import ensure_indexes
from .database.connection_manager import close_all

import logging
import os
import sentry_sdk

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Known production frontend origins. Used as a safe default so the API is never
# wide-open ("*") yet never fully locked down (which would break the live app if
# the ALLOWED_ORIGINS env var is not injected by the platform).
DEFAULT_ALLOWED_ORIGINS = [
    "https://lovelaundry-manager.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
]

# CORS configuration - prefer the platform-provided allowlist; otherwise use the
# known-good production origins. Never fall back to "*".
try:
    ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "")
    # Always keep the known-good production origins in the allowlist, and never
    # accept a literal "*" (Starlette refuses "*" when credentials are enabled).
    # This way a missing or misconfigured ALLOWED_ORIGINS env can never lock out
    # the live frontend.
    configured = [
        o.strip()
        for o in ALLOWED_ORIGINS_ENV.split(",")
        if o.strip() and o.strip() != "*"
    ]
    ALLOWED_ORIGINS = list(dict.fromkeys(configured + list(DEFAULT_ALLOWED_ORIGINS)))
    ALLOW_CREDENTIALS = True

    logger.info(f"CORS configured with origins: {ALLOWED_ORIGINS}, credentials: {ALLOW_CREDENTIALS}")
except Exception as e:
    logger.warning(f"CORS configuration failed, using safe default: {e}")
    ALLOWED_ORIGINS = list(DEFAULT_ALLOWED_ORIGINS)
    ALLOW_CREDENTIALS = True

SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
    )

app = FastAPI(title="Worker Daily Task Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
def startup_event():
    """Initialize database schema on startup"""
    try:
        if DB_TYPE in (DatabaseType.POSTGRESQL, DatabaseType.SQLITE):
            from .database import Base, engine

            if engine:
                Base.metadata.create_all(bind=engine)
        else:
            ensure_indexes()
    except Exception:
        logger.exception("Failed to initialize database schema on startup")


@app.on_event("shutdown")
def shutdown_event():
    """Close database connections on shutdown"""
    try:
        close_connections()
    except Exception:
        pass
    try:
        close_all()
    except Exception:
        pass


@app.get("/")
def root():
    return {
        "message": "Worker Daily Task Service API",
        "version": "1.0.0",
        "database": DB_TYPE.value,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/meta")
def meta():
    """Return valid enum values for form dropdowns."""
    return {
        "task_types": TASK_TYPES,
        "task_units": TASK_UNITS,
        "departments": DEPARTMENTS,
        "shifts": SHIFTS,
        "attendance_statuses": ATTENDANCE_STATUSES,
    }


# ─── Workers (staff registry) ─────────────────────────────────────────────────


@app.get(
    "/workers",
    response_model=list[WorkerResponse],
    dependencies=[Depends(require_role(["ADMIN", "MANAGER", "STAFF"]))],
)
def get_all_workers(
    active_only: bool = False,
    repo: WorkerRepository = Depends(get_repository),
):
    """Get all laundry staff workers"""
    return repo.get_all_workers(active_only=active_only)


@app.get(
    "/workers/{worker_id}",
    response_model=WorkerResponse,
    dependencies=[Depends(require_role(["ADMIN", "MANAGER", "STAFF"]))],
)
def get_worker(
    worker_id: str,
    repo: WorkerRepository = Depends(get_repository),
):
    worker = repo.get_worker_by_id(_coerce_db_id(worker_id))

    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


@app.post(
    "/workers",
    response_model=WorkerResponse,
    status_code=201,
    dependencies=[Depends(require_role(["ADMIN", "MANAGER"]))],
)
def create_worker(
    payload: WorkerCreate,
    repo: WorkerRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
):
    if payload.department.upper() not in DEPARTMENTS:
        raise HTTPException(status_code=422, detail=f"Department must be one of {DEPARTMENTS}")

    worker_data = {
        "worker_name": payload.worker_name.strip(),
        "department": payload.department.upper(),
        "phone": payload.phone,
        "is_active": payload.is_active,
        "joined_date": payload.joined_date,
        "notes": payload.notes,
    }
    return repo.create_worker(worker_data)


@app.put(
    "/workers/{worker_id}",
    response_model=WorkerResponse,
    dependencies=[Depends(require_role(["ADMIN", "MANAGER"]))],
)
def update_worker(
    worker_id: str,
    payload: WorkerUpdate,
    repo: WorkerRepository = Depends(get_repository),
):
    if DB_TYPE == DatabaseType.MONGODB:
        worker_id = str(worker_id)
    else:
        worker_id = _coerce_db_id(worker_id)

    update_data = payload.model_dump(exclude_unset=True)
    if "department" in update_data and update_data["department"]:
        if update_data["department"].upper() not in DEPARTMENTS:
            raise HTTPException(status_code=422, detail=f"Department must be one of {DEPARTMENTS}")
        update_data["department"] = update_data["department"].upper()

    updated_worker = repo.update_worker(worker_id, update_data)
    if not updated_worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return updated_worker


@app.delete(
    "/workers/{worker_id}",
    dependencies=[Depends(require_role(["ADMIN", "MANAGER"]))],
)
def delete_worker(
    worker_id: str,
    repo: WorkerRepository = Depends(get_repository),
):
    if DB_TYPE == DatabaseType.MONGODB:
        worker_id = str(worker_id)
    else:
        worker_id = _coerce_db_id(worker_id)

    success = repo.delete_worker(worker_id)
    if not success:
        raise HTTPException(status_code=404, detail="Worker not found")
    return {"message": "Worker deleted successfully"}


# ─── Daily task logs ──────────────────────────────────────────────────────────


@app.get(
    "/daily-logs",
    response_model=list[DailyLogResponse],
    dependencies=[Depends(require_role(["ADMIN", "MANAGER", "STAFF"]))],
)
def get_all_daily_logs(
    work_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    worker_name: Optional[str] = None,
    date_from: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    repo: WorkerRepository = Depends(get_repository),
):
    """Get daily task logs with optional date / worker / range filtering"""
    return repo.get_all_logs(
        work_date=work_date,
        worker_name=worker_name,
        date_from=date_from,
        date_to=date_to,
    )


@app.get(
    "/daily-logs/{log_id}",
    response_model=DailyLogResponse,
    dependencies=[Depends(require_role(["ADMIN", "MANAGER", "STAFF"]))],
)
def get_daily_log(
    log_id: str,
    repo: WorkerRepository = Depends(get_repository),
):
    if DB_TYPE == DatabaseType.MONGODB:
        log = repo.get_log_by_id(str(log_id))
    else:
        log = repo.get_log_by_id(_coerce_db_id(log_id))

    if not log:
        raise HTTPException(status_code=404, detail="Daily log not found")
    return log


@app.post(
    "/daily-logs",
    response_model=DailyLogResponse,
    status_code=201,
    dependencies=[Depends(require_role(["ADMIN", "MANAGER", "STAFF"]))],
)
def create_daily_log(
    payload: DailyLogCreate,
    repo: WorkerRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
):
    _validate_log_payload(payload.shift, payload.attendance_status, payload.tasks)

    log_data = {
        **payload.model_dump(),
        "tasks": [t.model_dump() for t in payload.tasks],
        "shift": payload.shift.upper(),
        "attendance_status": payload.attendance_status.upper(),
        "created_by": current_user.get("username") or current_user.get("sub"),
    }

    # Auto-fill quick counts from task entries when they are zero
    _sync_task_counts(log_data)

    return repo.create_log(log_data)


@app.put(
    "/daily-logs/{log_id}",
    response_model=DailyLogResponse,
    dependencies=[Depends(require_role(["ADMIN", "MANAGER", "STAFF"]))],
)
def update_daily_log(
    log_id: str,
    payload: DailyLogUpdate,
    repo: WorkerRepository = Depends(get_repository),
):
    if DB_TYPE == DatabaseType.MONGODB:
        log_id = str(log_id)
    else:
        log_id = _coerce_db_id(log_id)

    update_data = payload.model_dump(exclude_unset=True)

    if "shift" in update_data and update_data["shift"]:
        if update_data["shift"].upper() not in SHIFTS:
            raise HTTPException(status_code=422, detail=f"Shift must be one of {SHIFTS}")
        update_data["shift"] = update_data["shift"].upper()

    if "attendance_status" in update_data and update_data["attendance_status"]:
        if update_data["attendance_status"].upper() not in ATTENDANCE_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Attendance status must be one of {ATTENDANCE_STATUSES}",
            )
        update_data["attendance_status"] = update_data["attendance_status"].upper()

    if "tasks" in update_data and update_data["tasks"] is not None:
        for t in update_data["tasks"]:
            ttype = t.get("task_type") if isinstance(t, dict) else getattr(t, "task_type", None)
            tunit = t.get("unit") if isinstance(t, dict) else getattr(t, "unit", None)
            if ttype is None or str(ttype).upper() not in TASK_TYPES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Task type must be one of {TASK_TYPES}",
                )
            if tunit is None or str(tunit).upper() not in TASK_UNITS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Task unit must be one of {TASK_UNITS}",
                )
        update_data["tasks"] = [
            t.model_dump() if hasattr(t, "model_dump") else t for t in update_data["tasks"]
        ]

    updated_log = repo.update_log(log_id, update_data)
    if not updated_log:
        raise HTTPException(status_code=404, detail="Daily log not found")
    return updated_log


@app.delete(
    "/daily-logs/{log_id}",
    dependencies=[Depends(require_role(["ADMIN", "MANAGER"]))],
)
def delete_daily_log(
    log_id: str,
    repo: WorkerRepository = Depends(get_repository),
):
    if DB_TYPE == DatabaseType.MONGODB:
        log_id = str(log_id)
    else:
        log_id = _coerce_db_id(log_id)

    success = repo.delete_log(log_id)
    if not success:
        raise HTTPException(status_code=404, detail="Daily log not found")
    return {"message": "Daily log deleted successfully"}


# ─── Summaries ────────────────────────────────────────────────────────────────


def _empty_summary(date_value: str) -> dict:
    return {
        "date": date_value,
        "workers_logged": 0,
        "present": 0,
        "absent": 0,
        "on_leave": 0,
        "half_day": 0,
        "total_washed": 0,
        "total_pressed": 0,
        "total_folded": 0,
        "total_packed": 0,
        "total_other": 0,
        "total_weight_kg": 0.0,
        "total_overtime_hours": 0.0,
        "total_rewash": 0,
        "total_damaged": 0,
        "total_complaints": 0,
    }


@app.get(
    "/summary/daily",
    response_model=DailySummaryResponse,
    dependencies=[Depends(require_role(["ADMIN", "MANAGER", "STAFF"]))],
)
def daily_summary(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    repo: WorkerRepository = Depends(get_repository),
):
    """Aggregated productivity summary for a single work date."""
    logs = repo.get_all_logs(work_date=date)
    s = _empty_summary(date)

    for log in logs:
        s["workers_logged"] += 1
        attendance = str(log.get("attendance_status", "")).upper()
        if attendance == "PRESENT":
            s["present"] += 1
        elif attendance == "ABSENT":
            s["absent"] += 1
        elif attendance == "ON_LEAVE":
            s["on_leave"] += 1
        elif attendance == "HALF_DAY":
            s["half_day"] += 1
            s["present"] += 1
        s["total_washed"] += int(log.get("washed_count") or 0)
        s["total_pressed"] += int(log.get("pressed_count") or 0)
        s["total_folded"] += int(log.get("folded_count") or 0)
        s["total_packed"] += int(log.get("packed_count") or 0)
        s["total_other"] += int(log.get("other_count") or 0)
        s["total_weight_kg"] += float(log.get("total_weight_kg") or 0)
        s["total_overtime_hours"] += float(log.get("overtime_hours") or 0)
        s["total_rewash"] += int(log.get("rewash_count") or 0)
        s["total_damaged"] += int(log.get("damaged_items") or 0)
        s["total_complaints"] += int(log.get("complaints") or 0)

    s["total_weight_kg"] = round(s["total_weight_kg"], 2)
    s["total_overtime_hours"] = round(s["total_overtime_hours"], 2)
    return s


@app.get(
    "/summary/range",
    dependencies=[Depends(require_role(["ADMIN", "MANAGER", "STAFF"]))],
)
def range_summary(
    date_from: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    repo: WorkerRepository = Depends(get_repository),
):
    """Per-worker aggregated totals over a date range — useful for payroll/reviews."""
    logs = repo.get_all_logs(date_from=date_from, date_to=date_to)

    per_worker: dict = {}
    for log in logs:
        name = log.get("worker_name", "Unknown")
        entry = per_worker.setdefault(
            name,
            {
                "worker_name": name,
                "days_logged": 0,
                "present_days": 0,
                "total_washed": 0,
                "total_pressed": 0,
                "total_folded": 0,
                "total_packed": 0,
                "total_other": 0,
                "total_pieces": 0,
                "total_weight_kg": 0.0,
                "total_overtime_hours": 0.0,
                "total_rewash": 0,
                "total_damaged": 0,
                "avg_performance_rating": [],
            },
        )
        entry["days_logged"] += 1
        attendance = str(log.get("attendance_status", "")).upper()
        if attendance in ("PRESENT", "HALF_DAY"):
            entry["present_days"] += 1
        washed = int(log.get("washed_count") or 0)
        pressed = int(log.get("pressed_count") or 0)
        folded = int(log.get("folded_count") or 0)
        packed = int(log.get("packed_count") or 0)
        other = int(log.get("other_count") or 0)
        entry["total_washed"] += washed
        entry["total_pressed"] += pressed
        entry["total_folded"] += folded
        entry["total_packed"] += packed
        entry["total_other"] += other
        entry["total_pieces"] += washed + pressed + folded + packed + other
        entry["total_weight_kg"] += float(log.get("total_weight_kg") or 0)
        entry["total_overtime_hours"] += float(log.get("overtime_hours") or 0)
        entry["total_rewash"] += int(log.get("rewash_count") or 0)
        entry["total_damaged"] += int(log.get("damaged_items") or 0)
        rating = log.get("performance_rating")
        if rating:
            entry["avg_performance_rating"].append(float(rating))

    results = []
    for entry in per_worker.values():
        ratings = entry.pop("avg_performance_rating")
        entry["total_weight_kg"] = round(entry["total_weight_kg"], 2)
        entry["total_overtime_hours"] = round(entry["total_overtime_hours"], 2)
        entry["avg_performance_rating"] = round(sum(ratings) / len(ratings), 2) if ratings else None
        results.append(entry)

    results.sort(key=lambda e: e["total_pieces"], reverse=True)
    return {
        "date_from": date_from,
        "date_to": date_to,
        "generated_at": datetime.utcnow().isoformat(),
        "workers": results,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _coerce_db_id(raw_id: str):
    """Coerce a path id to the repository's expected type, returning a clean 404 on invalid ids."""
    if DB_TYPE == DatabaseType.MONGODB:
        return str(raw_id)
    try:
        return int(raw_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Resource not found")


def _validate_log_payload(shift: str, attendance_status: str, tasks: list):
    if shift.upper() not in SHIFTS:
        raise HTTPException(status_code=422, detail=f"Shift must be one of {SHIFTS}")
    if attendance_status.upper() not in ATTENDANCE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Attendance status must be one of {ATTENDANCE_STATUSES}",
        )
    for t in tasks:
        if t.task_type.upper() not in TASK_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Task type '{t.task_type}' must be one of {TASK_TYPES}",
            )
        if t.unit.upper() not in TASK_UNITS:
            raise HTTPException(
                status_code=422,
                detail=f"Task unit '{t.unit}' must be one of {TASK_UNITS}",
            )


def _sync_task_counts(log_data: dict):
    """Populate quick counts from detailed task entries when not manually set."""
    counts_by_type = {
        "WASHING": 0,
        "PRESSING": 0,
        "FOLDING": 0,
        "PACKING": 0,
        "OTHER": 0,
    }
    for t in log_data.get("tasks", []):
        t_type = str(t.get("task_type", "")).upper()
        qty = float(t.get("quantity") or 0)
        if t_type in ("DRY_CLEANING", "STAIN_TREATMENT"):
            counts_by_type["WASHING"] += qty
        elif t_type == "SORTING_TAGGING":
            counts_by_type["OTHER"] += qty
        elif t_type in counts_by_type:
            counts_by_type[t_type] += qty
        else:
            counts_by_type["OTHER"] += qty

    count_fields = {
        "WASHING": "washed_count",
        "PRESSING": "pressed_count",
        "FOLDING": "folded_count",
        "PACKING": "packed_count",
        "OTHER": "other_count",
    }
    for ttype, field in count_fields.items():
        if not log_data.get(field):
            log_data[field] = int(counts_by_type[ttype])
