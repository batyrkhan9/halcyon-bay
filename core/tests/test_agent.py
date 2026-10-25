import pytest

from core.agent import Agent
from core.dev_seed import seed
from core.gateway import Gateway
from core.reader import Reader, ReadFailed
from core.store import Store
from core.scripted import SEED_SCRIPTS, ScriptedClaude, reading


@pytest.fixture
def office():
    store = Store()
    fake = ScriptedClaude(dict(SEED_SCRIPTS))
    results = {r.account_id: r for r in seed(store, Reader(store, call=fake))}
    return store, fake, results


def proposal(store, account_id):
    return store.one("SELECT * FROM proposals WHERE account_id = ? AND kind NOT IN "
                     "('PAUSE_COLLECTIONS', 'BLOCK_AGENCY_ACTION')", account_id)


def question(store, account_id):
    return store.one("SELECT * FROM questions WHERE account_id = ? ORDER BY id DESC", account_id)


def test_clear_cases_get_the_outcome_code_computes(office):
    store, _, results = office
    assert proposal(store, "ACC-1001")["kind"] == "FREE_CARE"
    assert proposal(store, "ACC-1001")["amount_cents"] == 3_200_00
    discount = proposal(store, "ACC-1002")
    assert (discount["kind"], discount["amount_cents"]) == ("DISCOUNT", 8_400_00)
    assert proposal(store, "ACC-1004")["kind"] == "PAYMENT_PLAN"
    assert proposal(store, "ACC-1009")["kind"] == "FREE_CARE"
    assert all(results[a].did == "PROPOSED" for a in ("ACC-1001", "ACC-1002", "ACC-1004", "ACC-1009"))


def test_every_proposal_carries_its_quotes(office):
    store, _, _ = office
    evidence = proposal(store, "ACC-1001")["evidence"]
    assert {e["document_id"] for e in evidence} == {"DOC-0001", "DOC-0002"}
    assert all(e["quote"] for e in evidence)


def test_disagreeing_documents_go_to_a_person(office):
    store, _, results = office
    assert results["ACC-1003"].did == "ASKED"
    assert "disagree" in question(store, "ACC-1003")["question"]
    assert store.work_item(results["ACC-1003"].work_item_id)["state"] == "NEEDS_INFO"


def test_hidden_instructions_are_ignored_logged_and_the_stub_is_not_used(office):
    store, _, results = office
    assert results["ACC-1007"].did == "ASKED"
    assert proposal(store, "ACC-1007") is None
    refused = store.all("SELECT * FROM audit_log WHERE account_id = 'ACC-1007' AND action = 'follow_hidden_instructions'")
    assert refused and not any(r["allowed"] for r in refused)
    assert any("NOTE TO AI REVIEWER" in r["reason"] for r in refused)
    assert "hidden instructions" in question(store, "ACC-1007")["question"]


def test_calfresh_without_income_documents_asks_until_the_rule_is_learned(office):
    store, _, results = office
    assert results["ACC-1005"].did == "ASKED"
    assert "proof of income" in question(store, "ACC-1005")["question"]


def test_illegal_credit_report_is_blocked_and_collections_paused(office):
    store, _, _ = office
    assert store.one("SELECT status FROM agency_requests WHERE account_id = 'ACC-1005'")["status"] == "BLOCKED"
    assert store.account("ACC-1005")["collections_paused"] is True
    block = store.one("SELECT * FROM proposals WHERE account_id = 'ACC-1005' AND kind = 'BLOCK_AGENCY_ACTION'")
    assert block["status"] == "POSTED" and "SB 1061" in block["rationale"]


def test_staff_patient_is_flagged_in_the_proposal(office):
    store, _, _ = office
    assert "staff member Tomas Brandt (S-004)" in proposal(store, "ACC-1006")["rationale"]


def test_help_is_never_proposed_on_the_patients_word_alone(office):
    store, _, results = office
    assert results["ACC-1008"].did == "ASKED"
    assert proposal(store, "ACC-1008") is None
    assert "own word" in question(store, "ACC-1008")["question"]


def test_a_staff_answer_settles_the_question_and_the_agent_proposes(office):
    store, fake, results = office
    gw = Gateway(store)
    gw.answer(store.actor("S-001"), question(store, "ACC-1003")["id"], "Use the pay stub. She earns $3,610.00 a month.")
    fake.scripts["ACC-1003"] = lambda w: reading(w, household=("Household 2", 2),
                                                 income=[("Wages", [("$3,610.00 a month", 3610, "MONTHLY")])])
    result = Agent(store, gw, Reader(store, call=fake)).work(results["ACC-1003"].work_item_id)
    assert result.did == "PROPOSED"
    assert proposal(store, "ACC-1003")["evidence"][-1]["document_id"].startswith("Q-")


def test_the_agent_never_posted_anything_itself(office):
    store, _, _ = office
    posts = store.all("SELECT * FROM audit_log WHERE action = 'post' AND allowed = 1")
    assert {p["actor_id"] for p in posts} == {"gateway"}
    assert store.one("SELECT * FROM audit_log WHERE actor_id = 'agent' AND action = 'post'")["allowed"] is False


def test_every_reading_is_in_the_audit_log(office):
    store, fake, _ = office
    reads = store.all("SELECT * FROM audit_log WHERE action = 'read_case'")
    assert len(reads) == len(fake.calls) == 9
    assert all(r["detail"]["model"] == "scripted" for r in reads)


def test_when_claude_is_down_the_item_waits_untouched():
    store = Store()

    def down(_request):
        raise ReadFailed("Can't reach the Claude API.")

    store.upsert_account("ACC-1", patient_id="P", patient_name="X", billed_cents=100_00, first_bill_on=None, sources={})
    gw = Gateway(store)
    item = gw.open_work_item(store.actor("sync"), "ACC-1", "New balance")
    with pytest.raises(ReadFailed):
        Agent(store, gw, Reader(store, call=down)).work(item)
    assert store.work_item(item)["state"] == "NEW"
