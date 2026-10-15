from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class WorkerRepository(ABC):
    """Abstract repository interface for workers and daily task logs.

    Every tenant-shaped method accepts ``laundry_id``: the tenant scope from
    the signed JWT (see ``tenancy.resolve_laundry_id``). ``None`` means
    unscoped — reserved for system/platform callers running outside a
    request (sync jobs, migrations, maintenance).
    """

    # ─── Workers ──────────────────────────────────────────────────────────

    @abstractmethod
    def get_all_workers(
        self, active_only: bool = False, laundry_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def get_worker_by_id(
        self, worker_id, laundry_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def create_worker(
        self, worker_data: Dict[str, Any], laundry_id: Optional[str] = None
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    def update_worker(
        self, worker_id, update_data: Dict[str, Any], laundry_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def delete_worker(self, worker_id, laundry_id: Optional[str] = None) -> bool:
        ...

    # ─── Daily task logs ─────────────────────────────────────────────────

    @abstractmethod
    def get_all_logs(
        self,
        work_date: Optional[str] = None,
        worker_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        laundry_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def get_log_by_id(
        self, log_id, laundry_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def create_log(
        self, log_data: Dict[str, Any], laundry_id: Optional[str] = None
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    def update_log(
        self, log_id, update_data: Dict[str, Any], laundry_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def delete_log(self, log_id, laundry_id: Optional[str] = None) -> bool:
        ...
