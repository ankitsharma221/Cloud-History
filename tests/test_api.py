"""Integration tests for all FastAPI REST API endpoints."""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_readiness_endpoint():
    res = client.get("/readiness")
    assert res.status_code == 200
    data = res.json()
    assert "coverage_score" in data
    assert data["coverage_score"] > 0.0


def test_list_and_get_resources():
    res = client.get("/resources")
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 5

    res_single = client.get(f"/resources/{items[0]['id']}")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == items[0]["id"]


def test_provenance_timeline():
    res = client.get("/resources/i-0a1b2c3d4e5f67890/provenance")
    assert res.status_code == 200
    data = res.json()
    assert "timeline" in data
    assert "story" in data
    assert len(data["story"]) >= 1


def test_owner_and_ground_truth_confirmation():
    # 1. Fetch initial owner
    res = client.get("/resources/i-0a1b2c3d4e5f67890/owner")
    assert res.status_code == 200
    data = res.json()
    assert data["confidence"] in ["HIGH", "MEDIUM", "LOW"]

    # 2. Confirm owner
    confirm_res = client.post(
        "/resources/i-0a1b2c3d4e5f67890/owner/confirm",
        json={"confirmed": True, "corrected_owner": "Payments Platform Core"}
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "success"

    # 3. Verify ground truth was updated
    res_after = client.get("/resources/i-0a1b2c3d4e5f67890/owner")
    assert res_after.status_code == 200
    assert res_after.json()["name"] == "Payments Platform Core"


def test_risk_verdict():
    res = client.get("/resources/vol-04d5e6f7a8b9c0d1e/verdict")
    assert res.status_code == 200
    data = res.json()
    assert data["risk_level"] == "LOW_RISK"
    assert data["monthly_savings"] == 20.00


def test_quarantine_and_rollback_workflow():
    target_id = "vol-04d5e6f7a8b9c0d1e"

    # 1. Start quarantine
    q_res = client.post(
        f"/resources/{target_id}/quarantine",
        json={"approved_by": "qa-sre@company.com", "watch_period_days": 7}
    )
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["status"] == "watching"
    assert "snapshot_id" in q_data

    # 2. Trigger rollback
    rb_res = client.post(
        f"/resources/{target_id}/rollback",
        json={"reason": "Test rollback trigger"}
    )
    assert rb_res.status_code == 200
    assert rb_res.json()["status"] == "rolled_back"

    # 3. Check audit trail
    audit_res = client.get(f"/resources/{target_id}/audit")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert len(audit_data["quarantine_workflows"]) >= 1
