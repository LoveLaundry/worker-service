from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class WorkerRepository(ABC):
    """Abstract repository interface for workers and daily task logs."""

    # ─── Workers ──────────────────────────────────────────────────────────

    @abstractmethod
    def get_all_workers(self, active_only: bool = False) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def get_worker_by_id(self, worker_id) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def create_worker(self, worker_data: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def update_worker(self, worker_id, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def delete_worker(self, worker_id) -> bool:
        ...

    # ─── Daily task logs ─────────────────────────────────────────────────

    @abstractmethod
    def get_all_logs(
        self,
        work_date: Optional[str] = None,
        worker_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def get_log_by_id(self, log_id) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def create_log(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def update_log(self, log_id, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def delete_log(self, log_id) -> bool:
        ...
