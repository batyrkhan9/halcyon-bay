"""The gateway: the only path that changes state.

Every call runs can() first and writes to the audit log whether it is allowed
or not. Only the gateway itself posts, and only approved proposals.
"""

from __future__ import annotations

import json

from .model import (
    APPROVED, NEEDS_INFO, NEXT_STATES, PAUSE_COLLECTIONS, POSTED, PROPOSAL_KINDS, PROPOSED,
    REJECTED, SAFE_KINDS, SCREENING,
)
from .permissions import (
    ACT_SAFE, ANSWER, APPROVE, ASK, MOVE_WORK_ITEM, OPEN_WORK_ITEM, POST, PROPOSE, REJECT,
    Actor, Resource, can,
)
from .store import SYSTEM_ACTORS, Store

GATEWAY_ACTOR = SYSTEM_ACTORS["gateway"]


class Denied(Exception):
    """An action was refused. It is already in the audit log."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Gateway:
    def __init__(self, store: Store):
        self.store = store

    def _refuse(self, actor: Actor, action: str, target: str, account_id: str | None,
                reason: str, detail: dict | None = None):
        self.store.log(actor, action, target=target, account_id=account_id, allowed=False,
                       reason=reason, detail=detail)
        raise Denied(reason)

    def _check(self, actor: Actor, action: str, resource: Resource, target: str,
               detail: dict | None = None) -> str:
        decision = can(actor, action, resource)
        if not decision:
            self._refuse(actor, action, target, resource.account_id, decision.reason, detail)
        return decision.reason

    def _set_state(self, item_id: str, state: str) -> None:
        self.store.run("UPDATE work_items SET state = ?, updated_on = ? WHERE id = ?",
                       state, self.store.today().isoformat(), item_id)

    def proposal_resource(self, p: dict) -> Resource:
        account = self.store.account(p["account_id"]) if p["account_id"] else None
        return Resource(
            kind=p["kind"], account_id=p["account_id"],
            patient_id=account["patient_id"] if account else None,
            amount_cents=p["amount_cents"], proposed_by=p["proposed_by"],
            legal_question=p["legal_question"], status=p["status"],
        )

    # Work items.

    def open_work_item(self, actor: Actor, account_id: str, reason: str) -> str:
        target = f"account:{account_id}"
        self._check(actor, OPEN_WORK_ITEM, Resource(account_id=account_id), target)
        today = self.store.today().isoformat()
        with self.store.tx():
            item_id = self.store.next_id("WI")
            self.store.run("INSERT INTO work_items (id, account_id, state, reason, opened_on, updated_on) "
                           "VALUES (?, ?, 'NEW', ?, ?, ?)", item_id, account_id, reason, today, today)
            self.store.log(actor, OPEN_WORK_ITEM, target=item_id, account_id=account_id, allowed=True,
                           reason=reason)
        return item_id

    def move(self, actor: Actor, item_id: str, state: str, why: str) -> None:
        item = self.store.work_item(item_id)
        if item is None:
            raise KeyError(item_id)
        resource = Resource(account_id=item["account_id"], status=item["state"])
        self._check(actor, MOVE_WORK_ITEM, resource, item_id)
        if state not in (SCREENING, NEEDS_INFO) or state not in NEXT_STATES[item["state"]]:
            self._refuse(actor, MOVE_WORK_ITEM, item_id, item["account_id"],
                         f"Can't move a work item from {item['state']} to {state} directly.")
        with self.store.tx():
            self._set_state(item_id, state)
            self.store.log(actor, MOVE_WORK_ITEM, target=item_id, account_id=item["account_id"],
                           allowed=True, reason=why, detail={"from": item["state"], "to": state})

    # Proposals.

    def propose(self, actor: Actor, item_id: str, kind: str, *, amount_cents: int, rationale: str,
                evidence: list | None = None, pattern: str | None = None,
                legal_question: bool = False, reverses: str | None = None) -> str:
        if kind not in PROPOSAL_KINDS or kind in SAFE_KINDS:
            raise ValueError(f"{kind} can't be proposed; safe actions go through act_safe()")
        item = self.store.work_item(item_id)
        if item is None:
            raise KeyError(item_id)
        account_id = item["account_id"]
        detail = {"kind": kind, "amount_cents": amount_cents, "rationale": rationale, "pattern": pattern}
        self._check(actor, PROPOSE, Resource(kind=kind, account_id=account_id), item_id, detail)
        if item["state"] != SCREENING:
            self._refuse(actor, PROPOSE, item_id, account_id,
                         f"Proposals come from SCREENING; this work item is {item['state']}.", detail)
        if pattern and (earlier := self.store.rejected_pattern(pattern)):
            self._refuse(actor, PROPOSE, item_id, account_id,
                         f"Not proposed again: {earlier['rejected_by']} rejected '{pattern}' "
                         f"on {earlier['rejected_on']} ({earlier['note'] or 'no note'}).", detail)
        with self.store.tx():
            proposal_id = self.store.next_id("P")
            self.store.run(
                "INSERT INTO proposals (id, work_item_id, account_id, kind, amount_cents, rationale, evidence, "
                "pattern, legal_question, reverses, status, proposed_by, proposed_on) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPOSED', ?, ?)",
                proposal_id, item_id, account_id, kind, amount_cents, rationale, _json(evidence or []),
                pattern, int(legal_question), reverses, actor.id, self.store.today().isoformat(),
            )
            self._set_state(item_id, PROPOSED)
            self.store.log(actor, PROPOSE, target=proposal_id, account_id=account_id, allowed=True,
                           reason=rationale, detail={**detail, "evidence": evidence or []})
        return proposal_id

    def decide(self, actor: Actor, proposal_id: str, approve: bool, note: str = "") -> dict:
        """Approve or reject. An approval is posted by the gateway right away."""
        p = self.store.proposal(proposal_id)
        if p is None:
            raise KeyError(proposal_id)
        action = APPROVE if approve else REJECT
        reason = self._check(actor, action, self.proposal_resource(p), proposal_id, {"note": note})
        if p["status"] != PROPOSED:
            self._refuse(actor, action, proposal_id, p["account_id"], f"This proposal is already {p['status']}.")
        status = APPROVED if approve else REJECTED
        today = self.store.today().isoformat()
        with self.store.tx():
            self.store.run("UPDATE proposals SET status = ?, decided_by = ?, decided_on = ?, decision_note = ? "
                           "WHERE id = ?", status, actor.id, today, note, proposal_id)
            if p["work_item_id"]:
                self._set_state(p["work_item_id"], status)
            if not approve and p["pattern"]:
                self.store.run("INSERT OR IGNORE INTO rejected_patterns (pattern, proposal_id, rejected_by, "
                               "rejected_on, note) VALUES (?, ?, ?, ?, ?)",
                               p["pattern"], proposal_id, actor.id, today, note)
            self.store.log(actor, action, target=proposal_id, account_id=p["account_id"], allowed=True,
                           reason=reason, detail={"note": note})
        if approve:
            self.post(GATEWAY_ACTOR, proposal_id)
        return self.store.proposal(proposal_id)

    def post(self, actor: Actor, proposal_id: str) -> None:
        p = self.store.proposal(proposal_id)
        if p is None:
            raise KeyError(proposal_id)
        reason = self._check(actor, POST, self.proposal_resource(p), proposal_id)
        today = self.store.today().isoformat()
        with self.store.tx():
            self.store.run("INSERT INTO ledger (proposal_id, account_id, kind, amount_cents, reverses, posted_on) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           proposal_id, p["account_id"], p["kind"], p["amount_cents"], p["reverses"], today)
            self.store.run("UPDATE proposals SET status = 'POSTED' WHERE id = ?", proposal_id)
            if p["work_item_id"] and p["kind"] not in SAFE_KINDS:
                self._set_state(p["work_item_id"], POSTED)
            if p["kind"] == PAUSE_COLLECTIONS and p["account_id"]:
                self.store.run("UPDATE accounts SET collections_paused = 1 WHERE id = ?", p["account_id"])
            self.store.log(actor, POST, target=proposal_id, account_id=p["account_id"], allowed=True,
                           reason=reason, detail={"kind": p["kind"], "amount_cents": p["amount_cents"]})

    def act_safe(self, actor: Actor, account_id: str, kind: str, *, rationale: str,
                 evidence: list | None = None, item_id: str | None = None) -> str:
        """Pause collections or block an agency action. Safe, so no approval is needed."""
        detail = {"kind": kind, "rationale": rationale}
        reason = self._check(actor, ACT_SAFE, Resource(kind=kind, account_id=account_id),
                             f"account:{account_id}", detail)
        today = self.store.today().isoformat()
        with self.store.tx():
            proposal_id = self.store.next_id("P")
            self.store.run(
                "INSERT INTO proposals (id, work_item_id, account_id, kind, amount_cents, rationale, evidence, "
                "status, proposed_by, proposed_on, decided_by, decided_on, decision_note) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, 'APPROVED', ?, ?, ?, ?, ?)",
                proposal_id, item_id, account_id, kind, rationale, _json(evidence or []),
                actor.id, today, actor.id, today, reason,
            )
            self.store.log(actor, ACT_SAFE, target=proposal_id, account_id=account_id, allowed=True,
                           reason=rationale, detail={**detail, "evidence": evidence or []})
        self.post(GATEWAY_ACTOR, proposal_id)
        return proposal_id

    # Questions.

    def ask(self, actor: Actor, item_id: str, to_role: str, question: str) -> str:
        item = self.store.work_item(item_id)
        if item is None:
            raise KeyError(item_id)
        self._check(actor, ASK, Resource(account_id=item["account_id"]), item_id, {"question": question})
        with self.store.tx():
            question_id = self.store.next_id("Q")
            self.store.run("INSERT INTO questions (id, work_item_id, account_id, to_role, question, asked_by, "
                           "asked_on) VALUES (?, ?, ?, ?, ?, ?, ?)", question_id, item_id, item["account_id"],
                           to_role, question, actor.id, self.store.today().isoformat())
            if item["state"] == SCREENING:
                self._set_state(item_id, NEEDS_INFO)
            self.store.log(actor, ASK, target=question_id, account_id=item["account_id"], allowed=True,
                           reason=question, detail={"to_role": to_role})
        return question_id

    def answer(self, actor: Actor, question_id: str, answer: str) -> None:
        q = self.store.question(question_id)
        if q is None:
            raise KeyError(question_id)
        self._check(actor, ANSWER, Resource(account_id=q["account_id"]), question_id, {"answer": answer})
        if actor.role != q["to_role"]:
            self._refuse(actor, ANSWER, question_id, q["account_id"],
                         f"This question is for the {q['to_role']}, not the {actor.role}.")
        if q["answer"] is not None:
            self._refuse(actor, ANSWER, question_id, q["account_id"], "This question is already answered.")
        item = self.store.work_item(q["work_item_id"])
        with self.store.tx():
            self.store.run("UPDATE questions SET answer = ?, answered_by = ?, answered_on = ? WHERE id = ?",
                           answer, actor.id, self.store.today().isoformat(), question_id)
            if item and item["state"] == NEEDS_INFO:
                self._set_state(item["id"], SCREENING)
            self.store.log(actor, ANSWER, target=question_id, account_id=q["account_id"], allowed=True,
                           reason=answer)


def _json(value) -> str:
    return json.dumps(value, default=str)
