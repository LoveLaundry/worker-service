import logging
from .app_time import UTC
from datetime import datetime
from typing import List, Optional, Dict, Any
from bson import ObjectId

from .repository import WorkerRepository
from .crypto_helper import encrypt_dict, decrypt_dict, get_search_token
from .database.main_db import workers_collection, daily_logs_collection
from .tenancy import LOVE_LAUNDRY_ID

logger = logging.getLogger(__name__)

WORKER_SENSITIVE_FIELDS = ["worker_name", "phone", "notes"]
LOG_SENSITIVE_FIELDS = [
    "worker_name",
    "tasks",
    "machines_used",
    "chemicals_used",
    "quality_notes",
    "notes",
]


class MongoDBWorkerRepository(WorkerRepository):
    """MongoDB implementation of WorkerRepository with envelope encryption"""

    def __init__(self):
        self.workers = workers_collection
        self.logs = daily_logs_collection

        # Create indexes
        self.workers.create_index("worker_name_search")
        self.workers.create_index("is_active")
        self.logs.create_index("work_date")
        self.logs.create_index("worker_name_search")
        self.logs.create_index([("work_date", 1), ("worker_name_search", 1)])

    # ─── Tenant scoping ──────────────────────────────────────────────────────

    @staticmethod
    def _scope(query: Optional[Dict[str, Any]], laundry_id: Optional[str]) -> Dict[str, Any]:
        """Merge a business filter with the tenant scope.

        ``laundry_id=None`` means unscoped (system/platform callers only —
        never a request path). Pre-tenancy documents without ``laundry_id``
        belong to LoveLaundry, the sole historical tenant, so for
        ``lovelaundry`` the scope also matches missing/null values; every
        other laundry matches strictly its own stamped documents.
        """
        business = dict(query or {})
        if laundry_id is None:
            return business
        if laundry_id == LOVE_LAUNDRY_ID:
            tenant: Dict[str, Any] = {
                "$or": [
                    {"laundry_id": laundry_id},
                    {"laundry_id": {"$exists": False}},
                    {"laundry_id": None},
                ]
            }
        else:
            tenant = {"laundry_id": laundry_id}
        if business:
            return {"$and": [business, tenant]}
        return tenant

    # ─── Serialization helpers ────────────────────────────────────────────

    def _serialize_worker(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None
        try:
            doc = decrypt_dict(doc, WORKER_SENSITIVE_FIELDS)
        except Exception as e:
            raise ValueError(f"Failed to decrypt worker: {str(e)}")

        if "_id" in doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
        return doc

    def _serialize_log(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None
        try:
            doc = decrypt_dict(doc, LOG_SENSITIVE_FIELDS)
        except Exception as e:
            raise ValueError(f"Failed to decrypt daily log: {str(e)}")

        if "_id" in doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]

        # Normalize task entries (ensure unit defaults)
        for t in doc.get("tasks", []):
            t.setdefault("unit", "PIECES")
        return doc

    # ─── Workers ──────────────────────────────────────────────────────────

    def get_all_workers(
        self, active_only: bool = False, laundry_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = {"is_active": True} if active_only else {}
        documents = self.workers.find(self._scope(query, laundry_id)).sort("worker_name", 1)
        results = []
        for doc in documents:
            try:
                results.append(self._serialize_worker(doc))
            except ValueError as e:
                logger.error(f"Skipping undecryptable worker document {doc.get('_id')}: {e}")
        return results

    def get_worker_by_id(
        self, worker_id: str, laundry_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            doc = self.workers.find_one(self._scope({"_id": ObjectId(worker_id)}, laundry_id))
            if not doc:
                return None
            return self._serialize_worker(doc)
        except Exception:
            return None

    def create_worker(
        self, worker_data: Dict[str, Any], laundry_id: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.now(UTC)
        document = {
            **worker_data,
            "created_at": now,
            "updated_at": now,
        }
        if laundry_id is not None:
            document["laundry_id"] = laundry_id
        encrypted_document = encrypt_dict(document, WORKER_SENSITIVE_FIELDS)
        result = self.workers.insert_one(encrypted_document)
        encrypted_document["_id"] = result.inserted_id
        return self._serialize_worker(encrypted_document)

    def update_worker(
        self,
        worker_id: str,
        update_data: Dict[str, Any],
        laundry_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            original = self.workers.find_one(
                self._scope({"_id": ObjectId(worker_id)}, laundry_id)
            )
            if not original:
                return None

            try:
                decrypted_original = decrypt_dict(original, WORKER_SENSITIVE_FIELDS)
            except Exception:
                return None

            decrypted_original.update(update_data)
            decrypted_original.pop("created_at", None)
            decrypted_original["updated_at"] = datetime.now(UTC)

            encrypted_new = encrypt_dict(decrypted_original, WORKER_SENSITIVE_FIELDS)

            result = self.workers.find_one_and_update(
                self._scope({"_id": ObjectId(worker_id)}, laundry_id),
                {"$set": encrypted_new},
                return_document=True,
            )
            if not result:
                return None
            return self._serialize_worker(result)
        except Exception:
            return None

    def delete_worker(
        self, worker_id: str, laundry_id: Optional[str] = None
    ) -> bool:
        try:
            result = self.workers.delete_one(
                self._scope({"_id": ObjectId(worker_id)}, laundry_id)
            )
            return result.deleted_count > 0
        except Exception:
            return False

    # ─── Daily task logs ─────────────────────────────────────────────────

    def get_all_logs(
        self,
        work_date: Optional[str] = None,
        worker_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        laundry_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if work_date:
            query["work_date"] = work_date
        else:
            date_query: Dict[str, Any] = {}
            if date_from:
                date_query["$gte"] = date_from
            if date_to:
                date_query["$lte"] = date_to
            if date_query:
                query["work_date"] = date_query
        if worker_name:
            query["worker_name_search"] = get_search_token(worker_name)

        documents = self.logs.find(self._scope(query, laundry_id)).sort(
            [("work_date", -1), ("worker_name", 1)]
        )
        results = []
        for doc in documents:
            try:
                results.append(self._serialize_log(doc))
            except ValueError as e:
                logger.error(f"Skipping undecryptable daily log document {doc.get('_id')}: {e}")
        return results

    def get_log_by_id(
        self, log_id: str, laundry_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            doc = self.logs.find_one(self._scope({"_id": ObjectId(log_id)}, laundry_id))
            if not doc:
                return None
            return self._serialize_log(doc)
        except Exception:
            return None

    def create_log(
        self, log_data: Dict[str, Any], laundry_id: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.now(UTC)
        document = {
            **log_data,
            "worker_name_search": get_search_token(log_data.get("worker_name", "")),
            "created_at": now,
            "updated_at": now,
        }
        if laundry_id is not None:
            document["laundry_id"] = laundry_id
        encrypted_document = encrypt_dict(document, LOG_SENSITIVE_FIELDS)
        result = self.logs.insert_one(encrypted_document)
        encrypted_document["_id"] = result.inserted_id
        return self._serialize_log(encrypted_document)

    def update_log(
        self,
        log_id: str,
        update_data: Dict[str, Any],
        laundry_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            original = self.logs.find_one(self._scope({"_id": ObjectId(log_id)}, laundry_id))
            if not original:
                return None

            try:
                decrypted_original = decrypt_dict(original, LOG_SENSITIVE_FIELDS)
            except Exception:
                return None

            decrypted_original.update(update_data)
            decrypted_original.pop("created_at", None)

            if "worker_name" in update_data:
                decrypted_original["worker_name_search"] = get_search_token(
                    update_data["worker_name"]
                )

            decrypted_original["updated_at"] = datetime.now(UTC)

            encrypted_new = encrypt_dict(decrypted_original, LOG_SENSITIVE_FIELDS)

            result = self.logs.find_one_and_update(
                self._scope({"_id": ObjectId(log_id)}, laundry_id),
                {"$set": encrypted_new},
                return_document=True,
            )
            if not result:
                return None
            return self._serialize_log(result)
        except Exception:
            return None

    def delete_log(self, log_id: str, laundry_id: Optional[str] = None) -> bool:
        try:
            result = self.logs.delete_one(self._scope({"_id": ObjectId(log_id)}, laundry_id))
            return result.deleted_count > 0
        except Exception:
            return False

    def close(self):
        """Close the MongoDB connection"""
        pass
