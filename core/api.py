"""HTTP API for the UI. The contract is core/INTERFACE.md.

Run from the repo root:  core/.venv/bin/uvicorn core.api:main --factory --port 8000
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import discovery, learning
from .agent import Agent
from .config import DEFAULT_DB
from .gateway import Denied, Gateway
from .judge_box import FIRST_LIVE_DAY, JudgeBoxError, add_account, fields_from_text
from .model import PROPOSED, STAFF_ROLES, WORK_ITEM_STATES
from .permissions import APPROVE, can
from .reader import Reader, ReadFailed, ReplyCache
from .score import score
from .store import Store
from .sync import SOURCES, Sync

LAST_LIVE_DAY = date(2026, 9, 30)


class DecisionIn(BaseModel):
    actor_id: str
    approve: bool
    note: str = ""


class AnswerIn(BaseModel):
    actor_id: str
    answer: str


class AdvanceIn(BaseModel):
    days: int = 1


class JudgeBoxIn(BaseModel):
    text: str


class CorrectionIn(BaseModel):
    actor_id: str
    account_id: str
    correction: str
    note: str = ""


def create_app(store: Store, reader: Reader | None = None, sources=SOURCES, crs_check=None,
               claude_call=None) -> FastAPI:
    """claude_call stands in for Claude in the judge box and corrections, for tests."""
    gateway = Gateway(store)
    agent = Agent(store, gateway, reader or Reader(store, cache=ReplyCache()),
                  **({"crs_check": crs_check} if crs_check else {}))
    sync = Sync(store, sources=sources)
    app = FastAPI(title="Halcyon Bay core")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(Denied)
    def denied(_, exc: Denied):
        return JSONResponse(status_code=403, content={"denied": True, "reason": exc.reason})

    @app.exception_handler(ReadFailed)
    def read_failed(_, exc: ReadFailed):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    def missing(_, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": f"Not found: {exc.args[0]}"})

    def actor_or_404(actor_id: str):
        actor = store.actor(actor_id)
        if actor is None:
            raise HTTPException(404, f"No actor {actor_id}")
        return actor

    @app.get("/state")
    def state():
        counts = {s: 0 for s in WORK_ITEM_STATES}
        for row in store.all("SELECT state, COUNT(*) AS n FROM work_items GROUP BY state"):
            counts[row["state"]] = row["n"]
        return {
            "today": store.today().isoformat(),
            "work_items_by_state": counts,
            "open_proposals": store.one("SELECT COUNT(*) AS n FROM proposals WHERE status = 'PROPOSED'")["n"],
            "open_questions": store.one("SELECT COUNT(*) AS n FROM questions WHERE answer IS NULL")["n"],
        }

    @app.post("/sim/advance")
    def advance(body: AdvanceIn):
        """Run the next simulated day or days: sync each one, then the agent works what it brought."""
        for _ in range(max(1, min(body.days, 7))):
            day = store.today() + timedelta(days=1)
            if day > LAST_LIVE_DAY:
                raise HTTPException(409, f"The simulation already reached its last day, {LAST_LIVE_DAY}.")
            sync.day(day)
            agent.work_open_items()
        return state()

    @app.post("/judge-box")
    def judge_box(body: JudgeBoxIn):
        """A patient in plain English becomes a new account today, and the agent works it right away."""
        if store.today().isoformat() < FIRST_LIVE_DAY:
            raise HTTPException(409, "Advance to the first live day before adding a patient.")
        if not body.text.strip():
            raise HTTPException(400, "Describe the patient first.")
        fields = fields_from_text(body.text, call=claude_call)
        try:
            added = add_account(store.today().isoformat(), fields)
        except JudgeBoxError as e:
            raise HTTPException(400, str(e)) from None
        sync.refresh()
        sync.reload_today()
        item = store.one("SELECT id FROM work_items WHERE account_id = ? ORDER BY id DESC", added["account_no"])
        result = agent.work(item["id"]) if item else None
        return {"account_id": added["account_no"], "work_item_id": item["id"] if item else None,
                "fields": fields, "result": asdict(result) if result else None}

    @app.get("/actors")
    def actors():
        return store.all("SELECT id, name, role FROM staff WHERE role IN (?, ?, ?) ORDER BY role, name",
                         *STAFF_ROLES)

    @app.get("/work-items")
    def work_items(state: str | None = None, limit: int = 200):
        sql = ("SELECT w.*, a.patient_name, a.billed_cents FROM work_items w "
               "LEFT JOIN accounts a ON a.id = w.account_id")
        if state:
            return store.all(f"{sql} WHERE w.state = ? ORDER BY w.updated_on DESC, w.id LIMIT ?", state, limit)
        return store.all(f"{sql} ORDER BY w.updated_on DESC, w.id LIMIT ?", limit)

    @app.get("/accounts/{account_id}")
    def account(account_id: str):
        story = store.why(account_id)
        if story is None:
            raise HTTPException(404, f"No account {account_id}")
        return story

    @app.get("/inbox/{actor_id}")
    def inbox(actor_id: str):
        """What this person can decide or answer right now."""
        actor = actor_or_404(actor_id)
        open_proposals = store.all("SELECT * FROM proposals WHERE status = ? ORDER BY id", PROPOSED)
        decidable = [p for p in open_proposals
                     if can(actor, APPROVE, gateway.proposal_resource(p)).allowed]
        questions = store.all("SELECT * FROM questions WHERE answer IS NULL AND to_role = ? ORDER BY id",
                              actor.role)
        return {"actor": {"id": actor.id, "name": actor.name, "role": actor.role},
                "proposals": decidable, "questions": questions}

    @app.post("/proposals/{proposal_id}/decision")
    def decide(proposal_id: str, body: DecisionIn):
        decided = gateway.decide(actor_or_404(body.actor_id), proposal_id, body.approve, body.note)
        if decided["kind"] == "NEW_RULE" and decided["status"] == "POSTED":
            agent.reconsider()  # the accounts the new rule settles go back to work right away
        return decided

    @app.post("/corrections")
    def correction(body: CorrectionIn):
        """A staff correction becomes a precedent, and a general rule proposed to the director when it implies one."""
        return learning.correct(store, actor_or_404(body.actor_id), body.account_id, body.correction, body.note,
                                call=claude_call)

    @app.post("/questions/{question_id}/answer")
    def answer(question_id: str, body: AnswerIn):
        gateway.answer(actor_or_404(body.actor_id), question_id, body.answer)
        return store.question(question_id)

    @app.post("/work-items/{item_id}/work")
    def work(item_id: str):
        """The agent works one item now: reads it with Claude, then proposes or asks."""
        result = agent.work(item_id)
        return {"result": asdict(result), "work_item": store.work_item(item_id)}

    @app.get("/score")
    def current_score():
        """The live score against the answer key, in the shape the UI reads, plus the detail."""
        s = score(store)
        alone = s["alone"]
        auto = s["auto"]
        violations = s["violations_prevented"]
        return {
            "as_of": store.today().isoformat(),
            "precision": {"value": s["precision"] or 0, "correct": alone["right"], "total": alone["total"]},
            "auto_share": {"value": s["handled_automatically"] or 0, "auto": auto["right"], "total": auto["total"]},
            "charity_cents": round(s["dollars_to_charity"] * 100),
            "payment_plan_collected_cents": round(s["dollars_on_payment_plans"] * 100),
            "violations_prevented": {"count": sum(violations.values()), "by_law": violations},
            "answer_key": {"accounts_scored": s["accounts"], "matched": s["passed"]},
            "discovery": s["discovery"],
            "planted": s["planted"],
            "misses": s["misses"],
        }

    @app.get("/discovery")
    def day_one():
        """What onboarding found in the history, with each reversal's current proposal."""
        found = discovery.saved(store)
        if found is None:
            raise HTTPException(404, "Onboarding hasn't run the day-one discovery yet")
        for finding in found["findings"]:
            finding["proposal"] = store.proposal(finding["proposal_id"]) if finding["proposal_id"] else None
        return found

    @app.get("/learned")
    def learned():
        found = discovery.saved(store) or {"patterns": []}
        return {
            "patterns": found["patterns"],
            "precedents": store.records("precedent"),
            "rules": learning.learned_rules(store),
            "rejected": store.all("SELECT * FROM rejected_patterns ORDER BY rejected_on"),
        }

    @app.get("/audit")
    def audit(account_id: str | None = None, actor_id: str | None = None, allowed: bool | None = None,
              q: str | None = None, limit: int = 200):
        where, args = [], []
        if account_id:
            where.append("account_id = ?")
            args.append(account_id)
        if actor_id:
            where.append("actor_id = ?")
            args.append(actor_id)
        if allowed is not None:
            where.append("allowed = ?")
            args.append(int(allowed))
        if q:
            where.append("(reason LIKE ? OR target LIKE ? OR detail LIKE ? OR account_id LIKE ?)")
            args += [f"%{q}%"] * 4
        sql = "SELECT * FROM audit_log" + (f" WHERE {' AND '.join(where)}" if where else "")
        return store.all(f"{sql} ORDER BY seq DESC LIMIT ?", *args, limit)

    return app


def main() -> FastAPI:
    return create_app(Store(os.environ.get("HALCYON_DB", DEFAULT_DB)))
