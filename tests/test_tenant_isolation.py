"""Multi-tenant isolation tests for worker-service.

Covers the tenancy contract (fail-closed resolve, LoveLaundry legacy $or
rule, 404 oracle), repository-level scoping against an in-memory MongoDB
(mongomock), and endpoint-level cross-tenant 404s with own-tenant flows
unchanged.
"""
import os

os.environ["MASTER_KEY"] = "test-only-master-key-0123456789abcdef"
os.environ["JWT_SECRET"] = "test-only-jwt-secret-0123456789abcdef"
os.environ["DATABASE_URL"] = "mongodb://127.0.0.1:27017"
os.environ["MONGODB_MAIN_URI"] = "mongodb://127.0.0.1:27017"
os.environ["MONGODB_MAIN_DB"] = "test_worker_db"
os.environ["MONGODB_SECONDARY_URI"] = "mongodb://127.0.0.1:27017"
os.environ["MONGODB_LOCAL_URI"] = "mongodb://127.0.0.1:27017"

from types import SimpleNamespace

import mongomock
import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient

from worker_service.main import app
from worker_service.auth_helper import create_access_token
from worker_service.database import main_db
from worker_service import mongodb_repository, repository_factory
from worker_service.mongodb_repository import MongoDBWorkerRepository
from worker_service.tenancy import (
    LOVE_LAUNDRY_ID,
    assert_same_laundry,
    laundry_match,
    resolve_laundry_id,
    scoped_query,
)


def _token(laundry_id: str, **extra) -> str:
    claims = {
        "role": "ADMIN",
        "username": "tester",
        "sub": "tester",
        "laundry_id": laundry_id,
        "laundries": [{"id": laundry_id, "role": "ADMIN", "status": "ACTIVE"}],
    }
    claims.update(extra)
    return create_access_token(claims)


def _headers(laundry_id: str) -> dict:
    return {"Authorization": f"Bearer {_token(laundry_id)}"}


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def repo(monkeypatch):
    """Direct repository bound to a fresh in-memory MongoDB."""
    mc = mongomock.MongoClient()
    db = mc.get_database("test_worker_db")
    workers = db.get_collection("workers")
    logs = db.get_collection("daily_task_logs")
    monkeypatch.setattr(mongodb_repository, "workers_collection", workers)
    monkeypatch.setattr(mongodb_repository, "daily_logs_collection", logs)
    return MongoDBWorkerRepository()


@pytest.fixture
def mongo_env(monkeypatch):
    """TestClient + the mongomock collections backing the app repository."""
    mc = mongomock.MongoClient()
    db = mc.get_database("test_worker_db")
    workers = db.get_collection("workers")
    logs = db.get_collection("daily_task_logs")
    monkeypatch.setattr(main_db, "workers_collection", workers)
    monkeypatch.setattr(main_db, "daily_logs_collection", logs)
    monkeypatch.setattr(mongodb_repository, "workers_collection", workers)
    monkeypatch.setattr(mongodb_repository, "daily_logs_collection", logs)
    # The factory caches a repo singleton bound to the module-level
    # collections — reset so every test gets a repo on THIS mongomock DB.
    monkeypatch.setattr(repository_factory, "_mongodb_repo", None)
    return SimpleNamespace(client=TestClient(app), workers=workers, logs=logs)


def _worker_payload(name: str = "Alice", **overrides) -> dict:
    base = {
        "worker_name": name,
        "department": "GENERAL",
        "phone": "0771234567",
        "is_active": True,
        "joined_date": "2026-01-01",
        "notes": None,
    }
    base.update(overrides)
    return base


def _log_payload(name: str = "Alice", **overrides) -> dict:
    base = {
        "work_date": "2026-10-12",
        "worker_name": name,
        "department": "GENERAL",
        "shift": "FULL_DAY",
        "attendance_status": "PRESENT",
        "tasks": [],
        "is_group_work": False,
        "team_members": [],
    }
    base.update(overrides)
    return base


# ─── Tenancy helpers ─────────────────────────────────────────────────────────


def test_resolve_requires_session():
    with pytest.raises(HTTPException) as exc:
        resolve_laundry_id(None)
    assert exc.value.status_code == 401


def test_resolve_requires_laundry_claim():
    with pytest.raises(HTTPException) as exc:
        resolve_laundry_id({"role": "ADMIN", "username": "tester"})
    assert exc.value.status_code == 400


def test_resolve_rejects_non_member():
    user = {
        "role": "ADMIN",
        "laundry_id": "tenant-a",
        "laundries": [{"id": "other", "status": "ACTIVE"}],
    }
    with pytest.raises(HTTPException) as exc:
        resolve_laundry_id(user)
    assert exc.value.status_code == 403


def test_resolve_rejects_inactive_membership():
    user = {
        "role": "ADMIN",
        "laundry_id": "tenant-a",
        "laundries": [{"id": "tenant-a", "status": "SUSPENDED"}],
    }
    with pytest.raises(HTTPException) as exc:
        resolve_laundry_id(user)
    assert exc.value.status_code == 403


def test_resolve_returns_active_membership_lowercased():
    user = {
        "role": "ADMIN",
        "laundry_id": " Tenant-A ",
        "laundries": [{"id": "tenant-a", "role": "ADMIN", "status": "ACTIVE"}],
    }
    assert resolve_laundry_id(user) == "tenant-a"


def test_resolve_platform_context_bypasses_membership():
    user = {"role": "PLATFORM_ADMIN", "platform_admin": True, "laundry_id": "tenant-a"}
    assert resolve_laundry_id(user) == "tenant-a"
    user = {"support_entry": True, "laundry_id": "tenant-b"}
    assert resolve_laundry_id(user) == "tenant-b"


def test_lovelaundry_match_includes_legacy_unstamped_docs():
    assert laundry_match(LOVE_LAUNDRY_ID) == {
        "$or": [
            {"laundry_id": LOVE_LAUNDRY_ID},
            {"laundry_id": {"$exists": False}},
            {"laundry_id": None},
        ]
    }


def test_other_laundry_match_is_strict():
    assert laundry_match("tenant-a") == {"laundry_id": "tenant-a"}


def test_scoped_query_ands_business_filter_with_legacy_or():
    scoped = scoped_query({"work_date": "2026-10-12"}, LOVE_LAUNDRY_ID)
    assert scoped["$and"][0] == {"work_date": "2026-10-12"}
    assert scoped["$and"][1] == laundry_match(LOVE_LAUNDRY_ID)


def test_assert_same_laundry_404_oracle():
    with pytest.raises(HTTPException) as exc:
        assert_same_laundry({"laundry_id": "tenant-b"}, "tenant-a", "Worker")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Worker not found"


def test_assert_same_laundry_missing_doc_is_404():
    with pytest.raises(HTTPException) as exc:
        assert_same_laundry(None, "tenant-a", "Worker")
    assert exc.value.status_code == 404


def test_assert_same_laundry_legacy_doc_is_lovelaundry():
    assert_same_laundry({"worker_name": "Legacy"}, LOVE_LAUNDRY_ID, "Worker")
    with pytest.raises(HTTPException):
        assert_same_laundry({"worker_name": "Legacy"}, "tenant-a", "Worker")
    assert_same_laundry({"laundry_id": "tenant-a"}, "tenant-a", "Worker")


# ─── Repository scoping (mongomock) ─────────────────────────────────────────


def test_create_stamps_laundry_id(repo):
    created = repo.create_worker(_worker_payload(), laundry_id="tenant-a")
    assert created["laundry_id"] == "tenant-a"
    raw = repo.workers.find_one({"_id": ObjectId(created["id"])})
    assert raw["laundry_id"] == "tenant-a"


def test_create_without_laundry_id_stays_unstamped(repo):
    created = repo.create_worker(_worker_payload("Legacy"))
    raw = repo.workers.find_one({"_id": ObjectId(created["id"])})
    assert "laundry_id" not in raw


def test_list_is_scoped_per_tenant(repo):
    repo.create_worker(_worker_payload("Alice"), laundry_id="tenant-a")
    repo.create_worker(_worker_payload("Bob"), laundry_id="tenant-b")
    names_a = [w["worker_name"] for w in repo.get_all_workers(laundry_id="tenant-a")]
    names_b = [w["worker_name"] for w in repo.get_all_workers(laundry_id="tenant-b")]
    assert names_a == ["Alice"]
    assert names_b == ["Bob"]
    # laundry_id=None is the unscoped system view.
    assert len(repo.get_all_workers()) == 2


def test_cross_tenant_get_returns_none(repo):
    bob = repo.create_worker(_worker_payload("Bob"), laundry_id="tenant-b")
    assert repo.get_worker_by_id(bob["id"], laundry_id="tenant-a") is None
    assert repo.get_worker_by_id(bob["id"], laundry_id="tenant-b") is not None


def test_cross_tenant_update_and_delete_blocked(repo):
    bob = repo.create_worker(_worker_payload("Bob"), laundry_id="tenant-b")
    assert repo.update_worker(bob["id"], {"notes": "hax"}, laundry_id="tenant-a") is None
    assert repo.delete_worker(bob["id"], laundry_id="tenant-a") is False
    still = repo.get_worker_by_id(bob["id"], laundry_id="tenant-b")
    assert still is not None
    assert still["notes"] is None

    # Own tenant keeps working, and the tenant stamp survives the update.
    original_id = ObjectId(bob["id"])
    updated = repo.update_worker(bob["id"], {"notes": "mine"}, laundry_id="tenant-b")
    assert updated["notes"] == "mine"
    assert updated["laundry_id"] == "tenant-b"
    raw = repo.workers.find_one({"_id": original_id})
    assert raw is not None
    assert raw["_id"] == original_id
    assert repo.delete_worker(bob["id"], laundry_id="tenant-b") is True
    assert repo.get_worker_by_id(bob["id"], laundry_id="tenant-b") is None


def test_legacy_unstamped_doc_reads_as_lovelaundry(repo):
    legacy = repo.create_worker(_worker_payload("Legacy"))
    assert repo.get_worker_by_id(legacy["id"], laundry_id=LOVE_LAUNDRY_ID) is not None
    assert repo.get_worker_by_id(legacy["id"], laundry_id="tenant-a") is None
    names = [w["worker_name"] for w in repo.get_all_workers(laundry_id=LOVE_LAUNDRY_ID)]
    assert names == ["Legacy"]
    updated = repo.update_worker(legacy["id"], {"notes": "still mine"}, laundry_id=LOVE_LAUNDRY_ID)
    assert updated["notes"] == "still mine"


def test_log_create_stamps_and_list_is_scoped(repo):
    repo.create_log(_log_payload("Alice"), laundry_id="tenant-a")
    repo.create_log(_log_payload("Bob"), laundry_id="tenant-b")
    assert [l["worker_name"] for l in repo.get_all_logs(laundry_id="tenant-a")] == ["Alice"]
    assert [l["worker_name"] for l in repo.get_all_logs(laundry_id="tenant-b")] == ["Bob"]
    assert len(repo.get_all_logs()) == 2


def test_log_cross_tenant_crud_blocked(repo):
    log_b = repo.create_log(_log_payload("Bob"), laundry_id="tenant-b")
    assert repo.get_log_by_id(log_b["id"], laundry_id="tenant-a") is None
    assert repo.update_log(log_b["id"], {"notes": "hax"}, laundry_id="tenant-a") is None
    assert repo.delete_log(log_b["id"], laundry_id="tenant-a") is False
    assert repo.get_log_by_id(log_b["id"], laundry_id="tenant-b") is not None

    original_id = ObjectId(log_b["id"])
    updated = repo.update_log(log_b["id"], {"notes": "mine"}, laundry_id="tenant-b")
    assert updated["notes"] == "mine"
    assert updated["laundry_id"] == "tenant-b"
    raw = repo.logs.find_one({"_id": original_id})
    assert raw is not None
    assert raw["_id"] == original_id


def test_log_date_filter_combined_with_tenant_scope(repo):
    repo.create_log(_log_payload("Alice"), laundry_id="tenant-a")
    repo.create_log(_log_payload("Bob"), laundry_id="tenant-b")
    scoped = repo.get_all_logs(work_date="2026-10-12", laundry_id="tenant-a")
    assert [l["worker_name"] for l in scoped] == ["Alice"]


# ─── Endpoint-level isolation ────────────────────────────────────────────────


def test_endpoint_cross_tenant_worker_get_put_delete_are_404(mongo_env):
    client = mongo_env.client
    r = client.post(
        "/workers", json={"worker_name": "Alice", "notes": None}, headers=_headers("tenant-a")
    )
    assert r.status_code == 201, r.text
    worker_id = r.json()["id"]
    # Stamped at the source; response shape unchanged (laundry_id filtered out).
    raw = mongo_env.workers.find_one({"_id": ObjectId(worker_id)})
    assert raw["laundry_id"] == "tenant-a"
    assert "laundry_id" not in r.json()

    # Own tenant still works.
    r = client.get(f"/workers/{worker_id}", headers=_headers("tenant-a"))
    assert r.status_code == 200, r.text
    assert r.json()["worker_name"] == "Alice"

    # Cross-tenant read / update / delete all hit the same 404 oracle.
    r = client.get(f"/workers/{worker_id}", headers=_headers("tenant-b"))
    assert r.status_code == 404
    r = client.put(f"/workers/{worker_id}", json={"notes": "hax"}, headers=_headers("tenant-b"))
    assert r.status_code == 404
    r = client.delete(f"/workers/{worker_id}", headers=_headers("tenant-b"))
    assert r.status_code == 404

    # Untouched by the foreign requests; own-tenant mutation works.
    r = client.get(f"/workers/{worker_id}", headers=_headers("tenant-a"))
    assert r.status_code == 200
    assert r.json()["notes"] is None
    r = client.put(f"/workers/{worker_id}", json={"notes": "ok"}, headers=_headers("tenant-a"))
    assert r.status_code == 200
    assert r.json()["notes"] == "ok"
    r = client.delete(f"/workers/{worker_id}", headers=_headers("tenant-a"))
    assert r.status_code == 200


def test_endpoint_lists_are_scoped(mongo_env):
    client = mongo_env.client
    assert (
        client.post("/workers", json={"worker_name": "Alice"}, headers=_headers("tenant-a")).status_code
        == 201
    )
    assert (
        client.post("/workers", json={"worker_name": "Bob"}, headers=_headers("tenant-b")).status_code
        == 201
    )
    r = client.get("/workers", headers=_headers("tenant-a"))
    assert [w["worker_name"] for w in r.json()] == ["Alice"]
    r = client.get("/workers", headers=_headers("tenant-b"))
    assert [w["worker_name"] for w in r.json()] == ["Bob"]


def test_endpoint_cross_tenant_log_is_404_while_own_works(mongo_env):
    client = mongo_env.client
    r = client.post("/daily-logs", json=_log_payload("Alice"), headers=_headers("tenant-a"))
    assert r.status_code == 201, r.text
    log_id = r.json()["id"]
    raw = mongo_env.logs.find_one({"_id": ObjectId(log_id)})
    assert raw["laundry_id"] == "tenant-a"

    assert client.get(f"/daily-logs/{log_id}", headers=_headers("tenant-a")).status_code == 200
    assert client.get(f"/daily-logs/{log_id}", headers=_headers("tenant-b")).status_code == 404
    r = client.put(
        f"/daily-logs/{log_id}", json={"notes": "hax"}, headers=_headers("tenant-b")
    )
    assert r.status_code == 404
    assert client.delete(f"/daily-logs/{log_id}", headers=_headers("tenant-b")).status_code == 404
    assert client.delete(f"/daily-logs/{log_id}", headers=_headers("tenant-a")).status_code == 200
