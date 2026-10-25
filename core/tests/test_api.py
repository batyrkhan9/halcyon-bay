import pytest
from fastapi.testclient import TestClient

from core.api import create_app
from core.dev_seed import seed
from core.store import Store


@pytest.fixture
def client():
    store = Store()
    seed(store)
    return TestClient(create_app(store))


def test_state_counts_work_items(client):
    body = client.get("/state").json()
    assert body["today"] == "2026-07-01"
    assert body["work_items_by_state"]["PROPOSED"] == 5
    assert body["work_items_by_state"]["NEEDS_INFO"] == 2


def test_inbox_only_shows_what_each_person_may_decide(client):
    def proposals(actor_id):
        return {p["account_id"] for p in client.get(f"/inbox/{actor_id}").json()["proposals"]}

    assert proposals("S-001") == {"ACC-1001", "ACC-1004", "ACC-1006"}
    assert proposals("S-004") == {"ACC-1001", "ACC-1004"}          # not their own account
    assert proposals("S-002") == {"ACC-1001", "ACC-1002", "ACC-1004", "ACC-1006"}
    assert proposals("S-003") == {"ACC-0907"}
    assert len(client.get("/inbox/S-001").json()["questions"]) == 2


def test_decision_posts_or_returns_403_with_the_reason(client):
    big = next(p for p in client.get("/inbox/S-002").json()["proposals"] if p["account_id"] == "ACC-1002")
    denied = client.post(f"/proposals/{big['id']}/decision", json={"actor_id": "S-001", "approve": True})
    assert denied.status_code == 403
    assert "limit" in denied.json()["reason"]
    ok = client.post(f"/proposals/{big['id']}/decision", json={"actor_id": "S-002", "approve": True})
    assert ok.status_code == 200 and ok.json()["status"] == "POSTED"


def test_unknown_ids_are_404(client):
    assert client.get("/accounts/NOPE").status_code == 404
    assert client.post("/proposals/P-9999/decision", json={"actor_id": "S-002", "approve": True}).status_code == 404
    assert client.get("/inbox/NOPE").status_code == 404


def test_audit_search_finds_blocked_actions(client):
    blocked = client.get("/audit", params={"allowed": False}).json()
    assert [(r["actor_id"], r["action"]) for r in blocked] == [("agent", "post")]
    assert client.get("/audit", params={"q": "SB 1061"}).json()[0]["account_id"] == "ACC-1005"


def test_account_story(client):
    story = client.get("/accounts/ACC-1005").json()
    assert story["account"]["collections_paused"] is True
    assert {p["kind"] for p in story["proposals"]} == {"BLOCK_AGENCY_ACTION", "PAUSE_COLLECTIONS"}
