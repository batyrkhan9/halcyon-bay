import pytest
from fastapi.testclient import TestClient

from core.api import create_app
from core.dev_seed import seed
from core.reader import Reader, ReadFailed
from core.store import Store
from core.scripted import SEED_SCRIPTS, ScriptedClaude


@pytest.fixture
def client():
    store = Store()
    reader = Reader(store, call=ScriptedClaude(dict(SEED_SCRIPTS)))
    seed(store, reader)
    return TestClient(create_app(store, reader))


def test_state_counts_work_items(client):
    body = client.get("/state").json()
    assert body["today"] == "2026-07-01"
    assert body["work_items_by_state"]["PROPOSED"] == 6
    assert body["work_items_by_state"]["NEEDS_INFO"] == 4


def test_inbox_only_shows_what_each_person_may_decide(client):
    def proposals(actor_id):
        return {p["account_id"] for p in client.get(f"/inbox/{actor_id}").json()["proposals"]}

    assert proposals("S-001") == {"ACC-1001", "ACC-1004", "ACC-1006", "ACC-1009"}
    assert proposals("S-004") == {"ACC-1001", "ACC-1004", "ACC-1009"}          # not their own account
    assert proposals("S-002") == {"ACC-1001", "ACC-1002", "ACC-1004", "ACC-1006", "ACC-1009"}
    assert proposals("S-003") == {"ACC-0907"}
    assert len(client.get("/inbox/S-001").json()["questions"]) == 4


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
    assert client.post("/work-items/WI-9999/work").status_code == 404


def test_audit_search_finds_blocked_actions(client):
    blocked = client.get("/audit", params={"allowed": False}).json()
    assert {(r["actor_id"], r["action"]) for r in blocked} == {("agent", "post"), ("agent", "follow_hidden_instructions")}
    assert client.get("/audit", params={"q": "SB 1061"}).json()[0]["account_id"] == "ACC-1005"


def test_account_story_includes_documents_and_agency_requests(client):
    story = client.get("/accounts/ACC-1005").json()
    assert story["account"]["collections_paused"] is True
    assert [d["kind"] for d in story["documents"]] == ["NOTE"]
    assert story["agency_requests"][0]["status"] == "BLOCKED"
    assert {p["kind"] for p in story["proposals"]} == {"BLOCK_AGENCY_ACTION", "PAUSE_COLLECTIONS"}


def test_answer_then_work_runs_the_agent_again(client):
    q = next(q for q in client.get("/inbox/S-001").json()["questions"] if q["account_id"] == "ACC-1003")
    assert client.post(f"/questions/{q['id']}/answer", json={"actor_id": "S-001", "answer": "Use the letter."}).status_code == 200
    worked = client.post(f"/work-items/{q['work_item_id']}/work")
    assert worked.status_code == 200
    assert worked.json()["result"]["did"] in ("PROPOSED", "ASKED")


def test_work_returns_503_when_claude_is_down():
    store = Store()

    def down(_request):
        raise ReadFailed("Can't reach the Claude API.")

    reader = Reader(store, call=ScriptedClaude(dict(SEED_SCRIPTS)))
    seed(store, reader)
    store.upsert_account("ACC-1", patient_id="P", patient_name="X", billed_cents=100_00, first_bill_on=None, sources={})
    client = TestClient(create_app(store, Reader(store, call=down)))
    from core.gateway import Gateway
    item = Gateway(store).open_work_item(store.actor("sync"), "ACC-1", "New balance")
    response = client.post(f"/work-items/{item}/work")
    assert response.status_code == 503 and "Claude" in response.json()["detail"]
