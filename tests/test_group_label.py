"""Regression tests for the worker-service daily-log group-label logic.

A group log's `worker_name` label ("A + B") must stay in sync with its
`team_members` whenever the group is edited — including edits that change ONLY
the team (the old code only recomputed the label when `is_group_work` AND
`team_members` changed in the same request).
"""
import os

os.environ["MASTER_KEY"] = "test-only-master-key-0123456789abcdef"
os.environ["JWT_SECRET"] = "test-only-jwt-secret-0123456789abcdef"
os.environ["DATABASE_URL"] = "mongodb://127.0.0.1:27017"
os.environ["MONGODB_MAIN_URI"] = "mongodb://127.0.0.1:27017"
os.environ["MONGODB_MAIN_DB"] = "test_worker_db"
os.environ["MONGODB_SECONDARY_URI"] = "mongodb://127.0.0.1:27017"
os.environ["MONGODB_LOCAL_URI"] = "mongodb://127.0.0.1:27017"

import mongomock
import pytest
from fastapi.testclient import TestClient

from worker_service.main import app
from worker_service.auth_helper import create_access_token
from worker_service.database import main_db
from worker_service import mongodb_repository


@pytest.fixture
def client(monkeypatch):
    mc = mongomock.MongoClient()
    db = mc.get_database("test_worker_db")
    workers = db.get_collection("workers")
    logs = db.get_collection("daily_task_logs")
    # Patch both modules: main_db is the source the repo imports, and
    # mongodb_repository caches its own module-level references at import time.
    monkeypatch.setattr(main_db, "workers_collection", workers)
    monkeypatch.setattr(main_db, "daily_logs_collection", logs)
    monkeypatch.setattr(mongodb_repository, "workers_collection", workers)
    monkeypatch.setattr(mongodb_repository, "daily_logs_collection", logs)
    return TestClient(app)


TOKEN = create_access_token({"role": "ADMIN", "username": "tester", "sub": "tester"})


def _headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def _create_log(client, **overrides):
    base = {
        "work_date": "2026-10-12",
        "worker_name": "Alice",
        "department": "GENERAL",
        "shift": "FULL_DAY",
        "attendance_status": "PRESENT",
    }
    base.update(overrides)
    r = client.post("/daily-logs", json=base, headers=_headers())
    assert r.status_code == 201, r.text
    return r.json()


def test_group_team_edit_refreshes_label(client):
    log = _create_log(client)
    assert log["is_group_work"] is False
    assert log["worker_name"] == "Alice"

    # Promote to a group: label becomes "Alice + Bob".
    r = client.put(
        f"/daily-logs/{log['id']}",
        json={"is_group_work": True, "team_members": ["Alice", "Bob"]},
        headers=_headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["worker_name"] == "Alice + Bob"

    # Edit ONLY the team (is_group_work omitted): label must follow.
    r = client.put(
        f"/daily-logs/{log['id']}",
        json={"team_members": ["Alice", "Bob", "Carol"]},
        headers=_headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["worker_name"] == "Alice + Bob + Carol"


def test_group_off_with_single_name_clears_group_label(client):
    log = _create_log(client)
    r = client.put(
        f"/daily-logs/{log['id']}",
        json={"is_group_work": True, "team_members": ["Alice", "Bob"]},
        headers=_headers(),
    )
    assert r.json()["worker_name"] == "Alice + Bob"

    # Back to an individual log: explicit worker_name wins.
    r = client.put(
        f"/daily-logs/{log['id']}",
        json={"is_group_work": False, "worker_name": "Alice"},
        headers=_headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["worker_name"] == "Alice"
    assert r.json()["team_members"] == []


def test_group_requires_two_members_on_update(client):
    log = _create_log(client)
    r = client.put(
        f"/daily-logs/{log['id']}",
        json={"is_group_work": True, "team_members": ["Alice", "Bob"]},
        headers=_headers(),
    )
    assert r.status_code == 200, r.text
    # Shrinking a group to a single member is rejected.
    r = client.put(
        f"/daily-logs/{log['id']}",
        json={"team_members": ["OnlyOne"]},
        headers=_headers(),
    )
    assert r.status_code == 422, r.text