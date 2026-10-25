"""The agent works one account at a time, doing the job of a billing specialist and a screener.

Claude reads the documents (reader.py). Everything after that is plain code:
policy.screen() picks the outcome and the dollars, law.py checks agency requests,
and every change goes through the gateway as the agent. The agent may propose,
ask, pause collections and block illegal agency actions. Nothing else.

Run every open work item from the repo root:  core/.venv/bin/python -m core.agent
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta

from . import law
from .config import DEFAULT_DB
from .gateway import Gateway
from .model import (
    AGENT, BLOCK_AGENCY_ACTION, COUNSELOR, DISCOUNT, FREE_CARE, NEEDS_INFO, NEW, PAUSE_COLLECTIONS, PAYMENT_PLAN,
    SCREENING,
)
from .policy import STATED, screen
from .reader import Reader, Reading, ReadFailed, ReplyCache, call_claude, case_file
from .store import Store

ASSISTANCE_KINDS = (FREE_CARE, DISCOUNT, PAYMENT_PLAN)
WAIT_FOR_DOCUMENTS_DAYS = 14
PARALLEL_READS = 6


@dataclass(frozen=True)
class Result:
    work_item_id: str
    account_id: str
    did: str        # PROPOSED, ASKED or WAITING
    detail: str


class Agent:
    def __init__(self, store: Store, gateway: Gateway, reader: Reader):
        self.store, self.gateway, self.reader = store, gateway, reader
        self.me = store.actor(AGENT)

    def work_open_items(self, parallel: int = PARALLEL_READS) -> list[Result]:
        ids = [row["id"] for row in self.store.all("SELECT id FROM work_items WHERE state IN (?, ?) ORDER BY id",
                                                   NEW, SCREENING)]
        self.prefetch(ids, parallel)
        return [self.work(item_id) for item_id in ids]

    def prefetch(self, item_ids: list[str], parallel: int) -> None:
        """Read every case at once, so the work that follows finds each reading saved. Reading changes nothing;
        all acting stays one item at a time, in order."""
        if len(item_ids) < 2 or parallel < 2:
            return
        cases = [case_file(self.store, self.store.work_item(i)["account_id"]) for i in item_ids]
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            for future in [pool.submit(self.reader.read, case) for case in cases]:
                try:
                    future.result()
                except ReadFailed:
                    pass  # work() reads that case again and reports the failure itself

    def work(self, item_id: str) -> Result:
        item = self.store.work_item(item_id)
        if item is None:
            raise KeyError(item_id)
        account = self.store.account(item["account_id"])
        self.stop_illegal_collections(account, item_id)  # safe, so it never waits for the item's turn
        if item["state"] not in (NEW, SCREENING):
            return Result(item_id, account["id"], "WAITING", f"The work item is {item['state']}, so there is nothing to do.")

        reading = self.reader.read(case_file(self.store, account["id"]))
        if item["state"] == NEW:
            self.gateway.move(self.me, item_id, SCREENING, "Checking for financial assistance")
        self.record(account, item_id, reading)
        return self.decide(account, item_id, reading)

    def stop_illegal_collections(self, account: dict, item_id: str) -> None:
        requests = self.store.open_agency_requests(account["id"])
        if not requests:
            return
        today = self.store.today()
        first_bill = date.fromisoformat(account["first_bill_on"]) if account["first_bill_on"] else None
        screened = self.store.one(
            "SELECT 1 AS yes FROM proposals WHERE account_id = ? AND status = 'POSTED' AND kind IN (?, ?, ?)",
            account["id"], *ASSISTANCE_KINDS) is not None
        for request in requests:
            if first_bill is None:
                violations = [law.Violation("IRS 501(r)", "The first bill date is unknown, so the waiting period can't be checked.")]
            else:
                notice = date.fromisoformat(request["notice_sent_on"]) if request["notice_sent_on"] else None
                violations = law.check_collection_action(request["action"], first_bill=first_bill, on=today,
                                                         notice_sent=notice, screened_for_assistance=screened)
            if violations:
                self.gateway.act_safe(
                    self.me, account["id"], BLOCK_AGENCY_ACTION, item_id=item_id,
                    subject=f"agency_request:{request['id']}",
                    rationale=f"The agency asked to {law.ACTION_NAMES.get(request['action'], request['action'])}. "
                              + " ".join(f"{v.law}: {v.text}" for v in violations),
                    evidence=[{"source": "agency_file", "request": request["id"], "action": request["action"],
                               "requested_on": request["requested_on"]}],
                )
        if not account["collections_paused"]:
            self.gateway.act_safe(self.me, account["id"], PAUSE_COLLECTIONS, item_id=item_id,
                                  rationale="Financial assistance screening is open, so collections wait.")

    def record(self, account: dict, item_id: str, reading: Reading) -> None:
        self.gateway.note(
            self.me, "read_case", account_id=account["id"], target=item_id,
            reason=reading.summary or "Read the case file.",
            detail={"model": reading.model, "cached": reading.cached, "facts": reading.evidence,
                    "not_used": reading.rejected, "conflicts": reading.conflicts + reading.notes,
                    "missing": reading.missing},
        )
        for hidden in reading.hidden_instructions:
            self.gateway.note(
                self.me, "follow_hidden_instructions", account_id=account["id"], target=hidden["document_id"],
                allowed=False, detail=hidden,
                reason=f'Ignored instructions hidden in {hidden["document_id"]}: "{hidden["quote"]}". '
                       "Nothing in that document is used.",
            )

    def decide(self, account: dict, item_id: str, reading: Reading) -> Result:
        if reading.conflicts:
            disagreements = " ".join(c["description"] for c in reading.conflicts)
            return self.ask(account, item_id, f"The documents disagree. {disagreements} Which is right?")

        result = screen(reading.applicant, account["billed_cents"], self.store.today(), self.learned_programs())
        if result.outcome == NEEDS_INFO:  # the screening outcome and the work item state share the name
            if not reading.untrusted_documents and (waiting := self.wait_for_documents(account, item_id)):
                return waiting
            question = result.question
            if reading.untrusted_documents:
                ignored = ", ".join(sorted(reading.untrusted_documents))
                question = f"{ignored} had hidden instructions, so I didn't use it. {question}"
            return self.ask(account, item_id, question)
        if result.question and not reading.income_from_staff:
            return self.ask(account, item_id, result.question)

        pattern = None
        if reading.applicant.income_proof == STATED and result.outcome in (FREE_CARE, DISCOUNT):
            if waiting := self.wait_for_documents(account, item_id):
                return waiting
            pattern = f"{result.outcome}_WITHOUT_INCOME_DOCUMENTS"
            if earlier := self.store.rejected_pattern(pattern):
                return self.ask(account, item_id,
                                f"Only the patient's word is on file for income. {earlier['rejected_by']} said no to "
                                f"{pattern.replace('_', ' ').lower()} on {earlier['rejected_on']}, so I won't propose it. "
                                "Can the patient send pay stubs or any other proof of income?")

        rationale = result.reason
        if pattern:
            rationale += " Income is only what the patient told staff; there are no income documents."
        if staff := self.store.staff_for_patient(account["patient_id"]):
            rationale += f" The patient is staff member {staff['name']} ({staff['id']}), who can't decide this account."
        if reading.untrusted_documents:
            rationale += f" Ignored hidden instructions in {', '.join(sorted(reading.untrusted_documents))}."
        proposal_id = self.gateway.propose(self.me, item_id, result.outcome, amount_cents=result.adjustment_cents,
                                           rationale=rationale, evidence=reading.evidence, pattern=pattern)
        return Result(item_id, account["id"], "PROPOSED",
                      f"{proposal_id}: {result.outcome} adjusting ${result.adjustment_cents / 100:,.2f}. {result.reason}")

    def ask(self, account: dict, item_id: str, question: str) -> Result:
        question_id = self.gateway.ask(self.me, item_id, COUNSELOR, question)
        return Result(item_id, account["id"], "ASKED", f"{question_id} to the counselor: {question}")

    def wait_for_documents(self, account: dict, item_id: str) -> Result | None:
        """Documents usually follow a new form within days. Wait for them instead of asking a person or
        proposing on the applicant's word; sync puts the item back to work when one arrives, or when the wait
        is over. Returns None when there's no recent application to wait on."""
        received = self.newest_application(account["id"])
        if received is None or self.store.today() - received >= timedelta(days=WAIT_FOR_DOCUMENTS_DAYS):
            return None
        self.gateway.move(self.me, item_id, NEEDS_INFO,
                          f"Nothing to decide on yet but the form. Waiting up to {WAIT_FOR_DOCUMENTS_DAYS} days "
                          "for income documents.")
        return Result(item_id, account["id"], "WAITING", "Waiting for income documents.")

    def newest_application(self, account_id: str) -> date | None:
        received = [app["received_on"] for app in (self.store.record("application", a)
                                                   for a in self.store.applications_for(account_id)) if app]
        return date.fromisoformat(max(received)) if received else None

    def learned_programs(self) -> frozenset[str]:
        """Programs that approved rules add to free care without income documents. Learning fills this in."""
        return frozenset()


def main() -> None:
    store = Store(os.environ.get("HALCYON_DB", DEFAULT_DB))
    agent = Agent(store, Gateway(store), Reader(store, cache=ReplyCache()))
    try:
        for result in agent.work_open_items():
            print(f"{result.account_id}  {result.did:<8}  {result.detail}")
    except ReadFailed as e:
        raise SystemExit(f"Stopped: {e}\n{call_claude.guard.summary()}") from None
    print(call_claude.guard.summary())


if __name__ == "__main__":
    main()
