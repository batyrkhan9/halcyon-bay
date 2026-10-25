"""HTTP API for the UI. The contract is core/INTERFACE.md.

Run from the repo root:  core/.venv/bin/uvicorn core.api:main --factory --port 8000
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .gateway import Denied, Gateway
from .model import PROPOSED, STAFF_ROLES, WORK_ITEM_STATES
from .permissions import APPROVE, can
from .store import Store

DEFAULT_DB = "core/state/halcyon.db"


class DecisionIn(BaseModel):
    actor_id: str
    approve: bool
    note: str = ""


class AnswerIn(BaseModel):
    actor_id: str
    answer: str


def create_app(store: Store) -> FastAPI:
    gateway = Gateway(store)
    app = FastAPI(title="Halcyon Bay core")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(Denied)
    def denied(_, exc: Denied):
        return JSONResponse(status_code=403, content={"denied": True, "reason": exc.reason})

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
        return gateway.decide(actor_or_404(body.actor_id), proposal_id, body.approve, body.note)

    @app.post("/questions/{question_id}/answer")
    def answer(question_id: str, body: AnswerIn):
        gateway.answer(actor_or_404(body.actor_id), question_id, body.answer)
        return store.question(question_id)

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
