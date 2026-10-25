import sqlite3

import pytest

from core.gateway import Denied, Gateway
from core.model import (
    AGENT, COLLECTIONS_REFERRAL, COMPLIANCE, COUNSELOR, DIRECTOR, DISCOUNT, FREE_CARE,
    NEEDS_INFO, PAUSE_COLLECTIONS, POSTED, PROPOSED, REJECTED, REVERSAL, SCREENING, SYNC,
)
from core.permissions import Actor, Resource, can
from core.store import Store


@pytest.fixture
def world():
    store = Store()
    store.add_staff("S-COUNSELOR", "Test Counselor", COUNSELOR)
    store.add_staff("S-DIRECTOR", "Test Director", DIRECTOR)
    store.add_staff("S-COMPLIANCE", "Test Compliance", COMPLIANCE)
    store.add_staff("S-STAFF-PATIENT", "Counselor Who Is A Patient", COUNSELOR, ["PAT-9"])
    store.upsert_account("ACC-1", patient_id="PAT-1", patient_name="Test Patient", billed_cents=2_000_00,
                         first_bill_on=None, sources={})
    store.upsert_account("ACC-9", patient_id="PAT-9", patient_name="Staff Patient", billed_cents=1_000_00,
                         first_bill_on=None, sources={})
    return store, Gateway(store)


def screening_item(store, gw, account_id="ACC-1"):
    item = gw.open_work_item(store.actor(SYNC), account_id, "New self-pay balance")
    gw.move(store.actor(AGENT), item, SCREENING, "Checking for financial assistance")
    return item


def audit(store, **where):
    rows = store.all("SELECT * FROM audit_log ORDER BY seq")
    return [r for r in rows if all(r[k] == v for k, v in where.items())]


def test_approval_is_posted_by_the_gateway(world):
    store, gw = world
    item = screening_item(store, gw)
    p = gw.propose(store.actor(AGENT), item, FREE_CARE, amount_cents=2_000_00, rationale="120% of poverty")
    assert store.work_item(item)["state"] == PROPOSED
    result = gw.decide(store.actor("S-COUNSELOR"), p, approve=True, note="Looks right")
    assert result["status"] == POSTED
    assert store.work_item(item)["state"] == POSTED
    assert store.all("SELECT kind, amount_cents FROM ledger") == [{"kind": FREE_CARE, "amount_cents": 2_000_00}]
    assert audit(store, action="post", actor_id="gateway", allowed=True)


def test_agent_can_never_post_or_approve(world):
    store, gw = world
    item = screening_item(store, gw)
    p = gw.propose(store.actor(AGENT), item, FREE_CARE, amount_cents=2_000_00, rationale="r")
    with pytest.raises(Denied, match="Only the gateway posts"):
        gw.post(store.actor(AGENT), p)
    with pytest.raises(Denied, match="never approves"):
        gw.decide(store.actor(AGENT), p, approve=True)
    denied = audit(store, actor_id=AGENT, allowed=False)
    assert [r["action"] for r in denied] == ["post", "approve"]
    assert store.all("SELECT * FROM ledger") == []


def test_gateway_wont_post_an_unapproved_proposal(world):
    store, gw = world
    item = screening_item(store, gw)
    p = gw.propose(store.actor(AGENT), item, FREE_CARE, amount_cents=100_00, rationale="r")
    with pytest.raises(Denied, match="Only approved"):
        gw.post(store.actor("gateway"), p)


def test_proposer_cannot_approve_their_own_proposal(world):
    store, gw = world
    item = screening_item(store, gw)
    p = gw.propose(store.actor("S-COUNSELOR"), item, DISCOUNT, amount_cents=500_00, rationale="r")
    with pytest.raises(Denied, match="proposes"):
        gw.decide(store.actor("S-COUNSELOR"), p, approve=True)


def test_staff_cannot_approve_their_own_account(world):
    store, gw = world
    item = screening_item(store, gw, "ACC-9")
    p = gw.propose(store.actor(AGENT), item, FREE_CARE, amount_cents=1_000_00, rationale="r")
    with pytest.raises(Denied, match="own account"):
        gw.decide(store.actor("S-STAFF-PATIENT"), p, approve=True)
    assert gw.decide(store.actor("S-COUNSELOR"), p, approve=True)["status"] == POSTED


def test_counselor_limit_sends_large_adjustments_to_the_director(world):
    store, gw = world
    item = screening_item(store, gw)
    p = gw.propose(store.actor(AGENT), item, FREE_CARE, amount_cents=5_000_01, rationale="r")
    with pytest.raises(Denied, match="limit"):
        gw.decide(store.actor("S-COUNSELOR"), p, approve=True)
    assert gw.decide(store.actor("S-DIRECTOR"), p, approve=True)["status"] == POSTED


def test_only_compliance_decides_reversals_and_legal_questions(world):
    store, gw = world
    item = screening_item(store, gw)
    p = gw.propose(store.actor(AGENT), item, REVERSAL, amount_cents=2_000_00, rationale="AB 2297",
                   legal_question=True, reverses="fa_decision:D-1")
    with pytest.raises(Denied, match="compliance"):
        gw.decide(store.actor("S-DIRECTOR"), p, approve=True)
    assert gw.decide(store.actor("S-COMPLIANCE"), p, approve=True)["status"] == POSTED


def test_only_the_director_approves_collections_referrals():
    referral = Resource(kind=COLLECTIONS_REFERRAL, amount_cents=900_00, proposed_by=AGENT)
    assert not can(Actor("c", COUNSELOR), "approve", referral)
    assert can(Actor("d", DIRECTOR), "approve", referral)


def test_a_rejected_pattern_is_never_proposed_again(world):
    store, gw = world
    item = screening_item(store, gw)
    pattern = "DISCOUNT_WITHOUT_INCOME_DOCUMENTS"
    p = gw.propose(store.actor(AGENT), item, DISCOUNT, amount_cents=700_00, rationale="r", pattern=pattern)
    gw.decide(store.actor("S-DIRECTOR"), p, approve=False, note="We need some proof of income")
    assert store.work_item(item)["state"] == REJECTED
    gw.move(store.actor(AGENT), item, SCREENING, "Rework after rejection")
    with pytest.raises(Denied, match="Not proposed again"):
        gw.propose(store.actor(AGENT), item, DISCOUNT, amount_cents=700_00, rationale="r", pattern=pattern)


def test_agent_pauses_collections_alone(world):
    store, gw = world
    gw.act_safe(store.actor(AGENT), "ACC-1", PAUSE_COLLECTIONS, rationale="Screening in progress")
    assert store.account("ACC-1")["collections_paused"] is True
    with pytest.raises(Denied, match="not a safe action"):
        gw.act_safe(store.actor(AGENT), "ACC-1", FREE_CARE, rationale="r")


def test_questions_move_the_item_and_back(world):
    store, gw = world
    item = screening_item(store, gw)
    q = gw.ask(store.actor(AGENT), item, COUNSELOR, "Pay stub and letter disagree. Which income is right?")
    assert store.work_item(item)["state"] == NEEDS_INFO
    with pytest.raises(Denied, match="for the counselor"):
        gw.answer(store.actor("S-DIRECTOR"), q, "x")
    gw.answer(store.actor("S-COUNSELOR"), q, "Use the letter")
    assert store.work_item(item)["state"] == SCREENING


def test_illegal_state_jumps_are_refused(world):
    store, gw = world
    item = gw.open_work_item(store.actor(SYNC), "ACC-1", "r")
    with pytest.raises(Denied):
        gw.move(store.actor(AGENT), item, NEEDS_INFO, "skip screening")
    with pytest.raises(Denied, match="Only the sync job"):
        gw.open_work_item(store.actor(AGENT), "ACC-1", "r")


def test_audit_log_and_ledger_are_append_only(world):
    store, gw = world
    item = screening_item(store, gw)
    p = gw.propose(store.actor(AGENT), item, FREE_CARE, amount_cents=100_00, rationale="r")
    gw.decide(store.actor("S-COUNSELOR"), p, approve=True)
    for sql in ("UPDATE audit_log SET reason = 'x'", "DELETE FROM audit_log",
                "UPDATE ledger SET amount_cents = 0", "DELETE FROM ledger"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.run(sql)


def test_why_tells_the_whole_story(world):
    store, gw = world
    item = screening_item(store, gw)
    p = gw.propose(store.actor(AGENT), item, FREE_CARE, amount_cents=100_00, rationale="120% of poverty")
    with pytest.raises(Denied):
        gw.post(store.actor(AGENT), p)
    gw.decide(store.actor("S-COUNSELOR"), p, approve=True)
    story = store.why("ACC-1")
    actions = [(r["actor_id"], r["action"], r["allowed"]) for r in story["audit"]]
    assert actions == [
        ("sync", "open_work_item", True),
        ("agent", "move_work_item", True),
        ("agent", "propose", True),
        ("agent", "post", False),
        ("S-COUNSELOR", "approve", True),
        ("gateway", "post", True),
    ]
    assert story["proposals"][0]["status"] == POSTED
