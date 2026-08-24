from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from .repository import WorkerRepository
from .models import Worker, DailyTaskLog


class PostgreSQLWorkerRepository(WorkerRepository):
    """PostgreSQL/SQLite implementation of WorkerRepository using SQLAlchemy"""

    def __init__(self, db: Session):
        self.db = db

    # ─── Workers ──────────────────────────────────────────────────────────

    def _worker_to_dict(self, worker: Worker) -> Dict[str, Any]:
        return {
            "id": worker.id,
            "worker_name": worker.worker_name,
            "department": worker.department,
            "phone": worker.phone,
            "is_active": worker.is_active,
            "joined_date": worker.joined_date,
            "notes": worker.notes,
            "created_at": worker.created_at,
            "updated_at": worker.updated_at,
        }

    def get_all_workers(self, active_only: bool = False) -> List[Dict[str, Any]]:
        query = self.db.query(Worker)
        if active_only:
            query = query.filter(Worker.is_active.is_(True))
        workers = query.order_by(Worker.worker_name.asc()).all()
        return [self._worker_to_dict(w) for w in workers]

    def get_worker_by_id(self, worker_id: int) -> Optional[Dict[str, Any]]:
        worker = self.db.query(Worker).filter(Worker.id == worker_id).first()
        return self._worker_to_dict(worker) if worker else None

    def create_worker(self, worker_data: Dict[str, Any]) -> Dict[str, Any]:
        new_worker = Worker(**worker_data)
        self.db.add(new_worker)
        self.db.commit()
        self.db.refresh(new_worker)
        return self._worker_to_dict(new_worker)

    def update_worker(self, worker_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        worker = self.db.query(Worker).filter(Worker.id == worker_id).first()
        if not worker:
            return None

        for key, value in update_data.items():
            if hasattr(worker, key):
                setattr(worker, key, value)

        self.db.commit()
        self.db.refresh(worker)
        return self._worker_to_dict(worker)

    def delete_worker(self, worker_id: int) -> bool:
        worker = self.db.query(Worker).filter(Worker.id == worker_id).first()
        if not worker:
            return False

        self.db.delete(worker)
        self.db.commit()
        return True

    # ─── Daily task logs ─────────────────────────────────────────────────

    def _log_to_dict(self, log: DailyTaskLog) -> Dict[str, Any]:
        tasks = log.tasks or []
        if isinstance(tasks, str):
            import json

            try:
                tasks = json.loads(tasks)
            except Exception:
                tasks = []
        for t in tasks:
            if isinstance(t, dict):
                t.setdefault("unit", "PIECES")
        return {
            "id": log.id,
            "work_date": log.work_date,
            "worker_name": log.worker_name,
            "department": log.department,
            "shift": log.shift,
            "attendance_status": log.attendance_status,
            "check_in_time": log.check_in_time,
            "check_out_time": log.check_out_time,
            "overtime_hours": log.overtime_hours,
            "washed_count": log.washed_count,
            "pressed_count": log.pressed_count,
            "folded_count": log.folded_count,
            "packed_count": log.packed_count,
            "other_count": log.other_count,
            "total_weight_kg": log.total_weight_kg,
            "tasks": tasks,
            "rewash_count": log.rewash_count,
            "damaged_items": log.damaged_items,
            "complaints": log.complaints,
            "quality_notes": log.quality_notes,
            "machines_used": log.machines_used,
            "chemicals_used": log.chemicals_used,
            "notes": log.notes,
            "performance_rating": log.performance_rating,
            "created_by": log.created_by,
            "created_at": log.created_at,
            "updated_at": log.updated_at,
        }

    def get_all_logs(
        self,
        work_date: Optional[str] = None,
        worker_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = self.db.query(DailyTaskLog)
        if work_date:
            query = query.filter(DailyTaskLog.work_date == work_date)
        else:
            if date_from:
                query = query.filter(DailyTaskLog.work_date >= date_from)
            if date_to:
                query = query.filter(DailyTaskLog.work_date <= date_to)
        if worker_name:
            query = query.filter(DailyTaskLog.worker_name.ilike(f"%{worker_name}%"))
        logs = query.order_by(
            DailyTaskLog.work_date.desc(), DailyTaskLog.worker_name.asc()
        ).all()
        return [self._log_to_dict(l) for l in logs]

    def get_log_by_id(self, log_id: int) -> Optional[Dict[str, Any]]:
        log = self.db.query(DailyTaskLog).filter(DailyTaskLog.id == log_id).first()
        return self._log_to_dict(log) if log else None

    def create_log(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        new_log = DailyTaskLog(**log_data)
        self.db.add(new_log)
        self.db.commit()
        self.db.refresh(new_log)
        return self._log_to_dict(new_log)

    def update_log(self, log_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        log = self.db.query(DailyTaskLog).filter(DailyTaskLog.id == log_id).first()
        if not log:
            return None

        for key, value in update_data.items():
            if hasattr(log, key):
                setattr(log, key, value)

        self.db.commit()
        self.db.refresh(log)
        return self._log_to_dict(log)

    def delete_log(self, log_id: int) -> bool:
        log = self.db.query(DailyTaskLog).filter(DailyTaskLog.id == log_id).first()
        if not log:
            return False

        self.db.delete(log)
        self.db.commit()
        return True
