from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "api-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from proofloop import config, db
    config.get_settings.cache_clear()
    db.settings = config.get_settings()
    db._ensure_sqlite_directory(db.settings.database_url)
    db.engine.dispose()
    db.engine = __import__("sqlalchemy").create_engine(db.settings.database_url, connect_args={"check_same_thread": False})
    db.SessionLocal.configure(bind=db.engine)
    from proofloop.main import app
    with TestClient(app) as test_client:
        yield test_client


def payload():
    return {"title": "API case", "answer": "The system uses SQLite.", "sources": [{"name": "Spec", "content": "The system uses SQLite."}]}


def test_api_case_verify_decide_and_export(client):
    created = client.post("/api/cases", json=payload())
    assert created.status_code == 201
    case = created.json()
    assert len(case["claims"]) == 1
    verified = client.post(f"/api/cases/{case['id']}/verify")
    assert verified.status_code == 200
    assert verified.json()["latest_run"]["metrics"]["supported"] == 1
    decision = client.post(f"/api/cases/{case['id']}/decision", json={"decision": "APPROVED", "comment": "Reviewed source."})
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"
    exported = client.get(f"/api/cases/{case['id']}/export")
    assert exported.status_code == 200
    assert exported.json()["history"]


def test_api_validation_and_missing_case(client):
    assert client.post("/api/cases", json={"title": "", "answer": "", "sources": []}).status_code == 422
    assert client.get("/api/cases/does-not-exist").status_code == 404
    assert client.post("/api/cases/does-not-exist/decision", json={"decision": "APPROVED"}).status_code == 404
    assert client.post("/api/cases", json={"title": " ", "answer": "Valid answer.", "sources": [{"name": "Spec", "content": "Evidence."}]}).status_code == 422
    assert client.patch("/api/claims/does-not-exist", json={"text": " "}).status_code == 422


def test_demo_scenarios_have_distinct_real_outcomes(client):
    outcomes = {}
    for scenario in ("supported", "unsupported", "contradicted"):
        created = client.get(f"/api/demo/{scenario}")
        assert created.status_code == 200
        case = client.get(f"/api/cases/{created.json()['case_id']}").json()
        result = case["latest_run"]["results"]["results"][0]
        outcomes[scenario] = result["status"]
    assert outcomes == {"supported": "supported", "unsupported": "unsupported", "contradicted": "contradicted"}


def test_decision_rejected_until_current_revision_is_reverified(client):
    created = client.post("/api/cases", json=payload()).json()
    case_id = created["id"]
    verified = client.post(f"/api/cases/{case_id}/verify").json()
    claim_id = verified["claims"][0]["id"]
    revised = client.post(f"/api/cases/{case_id}/repairs/apply", json=[{"claim_id": claim_id, "action": "REMOVE"}])
    assert revised.status_code == 200
    stale_decision = client.post(f"/api/cases/{case_id}/decision", json={"decision": "APPROVED"})
    assert stale_decision.status_code == 409
    fresh = client.post(f"/api/cases/{case_id}/verify")
    assert fresh.status_code == 200
    assert client.post(f"/api/cases/{case_id}/decision", json={"decision": "REJECTED", "comment": "Fresh run reviewed."}).status_code == 200


def test_noop_or_incomplete_repairs_are_rejected(client):
    created = client.post("/api/cases", json=payload()).json()
    case_id = created["id"]
    claim_id = created["claims"][0]["id"]
    assert client.post(f"/api/cases/{case_id}/repairs/apply", json=[{"claim_id": claim_id, "action": "MANUAL_REVIEW"}]).status_code == 409
    assert client.post(f"/api/cases/{case_id}/repairs/apply", json=[{"claim_id": claim_id, "action": "REWRITE"}]).status_code == 422
