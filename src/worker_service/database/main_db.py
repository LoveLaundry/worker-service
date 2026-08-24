"""
MAIN database — production source of truth.

All normal application reads and writes MUST go through these
collections. Never read or write the Secondary/Local databases
from business logic.
"""
from pymongo.collection import Collection

from .connection_manager import ROLE_MAIN, get_database

_db = get_database(ROLE_MAIN)

workers_collection: Collection = _db.get_collection("workers")
daily_logs_collection: Collection = _db.get_collection("daily_task_logs")


def ensure_indexes():
    """Create all required indexes on the MAIN database."""
    # Worker registry indexes
    workers_collection.create_index("worker_name_search")
    workers_collection.create_index("is_active")
    workers_collection.create_index("created_at")

    # Daily task log indexes
    daily_logs_collection.create_index("work_date")
    daily_logs_collection.create_index("worker_name_search")
    daily_logs_collection.create_index([("work_date", 1), ("worker_name_search", 1)])
    daily_logs_collection.create_index("created_at")
