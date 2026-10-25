"""Sync: bring each simulated day from data/ into the store, then open work items.

Reads data/world/, and data/judge/ when the judge box has added a patient, as
data/FORMAT.md describes. Onboarding loads every row recorded on or before
2026-06-30; live day D loads the rows recorded on D. Never a row from the future,
and never the answer key.

Every row is kept as its system exported it (latest wins per key), so a screen
can show what each system says. The messy parts become documents for the
agent's reader: each application is rendered as its form, each staff note as a
note, each account's registration as a billing record, and the mailroom's text.

An application reaches the accounts it lists and the open accounts under the MRN
it gives. Matching people across systems (duplicates, typos) comes next.

Run from the repo root:
  core/.venv/bin/python -m core.sync onboard
  core/.venv/bin/python -m core.sync day 2026-07-01 [--through 2026-07-07] [--work]
"""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .agent import WAIT_FOR_DOCUMENTS_DAYS, Agent
from .config import DEFAULT_DB, ROOT
from .coverage import account_number, covering_approval
from .gateway import Gateway
from .model import COMPLIANCE, COUNSELOR, DIRECTOR, NEEDS_INFO, SCREENING, SYNC
from .reader import APPLICATION, BILLING, NOTE
from .store import Store

DATA = ROOT / "data"
SOURCES = (DATA / "world", DATA / "judge")
ONBOARDING_THROUGH = date(2026, 6, 30)

# file: (record kind, key column). Event files have unique IDs, so latest-wins is the same as adding.
FILES = {
    "billing/patients.csv": ("patient", "mrn"),
    "billing/accounts.csv": ("account", "account_no"),
    "billing/transactions.csv": ("transaction", "txn_id"),
    "billing/statements.csv": ("statement", "statement_id"),
    "billing/payment_plans.csv": ("payment_plan", "plan_id"),
    "fa/applications.csv": ("application", "application_id"),
    "fa/notes.csv": ("note", "note_id"),
    "agency/placements.csv": ("placement", "agency_ref"),
    "agency/requests.csv": ("request", "request_id"),
    "documents/index.csv": ("document", "doc_id"),
    "staff/staff.csv": ("staff", "staff_id"),
}
ROLES = {
    "FINANCIAL_COUNSELOR": COUNSELOR,
    "REVENUE_CYCLE_DIRECTOR": DIRECTOR,
    "COMPLIANCE_OFFICER": COMPLIANCE,
    "BILLING_SPECIALIST": "billing_specialist",
    "PATIENT_ACCESS": "patient_access",
}
UNDECIDED = {"RECEIVED", "NEEDS_INFO"}
WORKABLE_ACCOUNTS = {"OPEN", "IN_COLLECTIONS"}
OPEN_ITEM_STATES = ("NEW", "SCREENING", "NEEDS_INFO", "PROPOSED", "APPROVED", "REJECTED")


def cents(dollars: str) -> int:
    return int(Decimal(dollars or "0") * 100)


def us_date(written: str) -> str | None:
    """MM/DD/YYYY to ISO."""
    if not written:
        return None
    month, day, year = written.split("/")
    return f"{year}-{int(month):02d}-{int(day):02d}"


class Sync:
    def __init__(self, store: Store, sources=SOURCES):
        self.store, self.gateway = store, Gateway(store)
        self.me = store.actor(SYNC)
        self.sources = [Path(s) for s in sources if Path(s).is_dir()]
        self._files: dict[str, list[tuple[Path, dict]]] = {}

    def rows(self, file: str) -> list[tuple[Path, dict]]:
        """Every row of a file across the sources, in replay order, read once."""
        if file not in self._files:
            found = []
            for source in self.sources:
                path = source / file
                if path.is_file():
                    with path.open(newline="") as f:
                        found += [(source, row) for row in csv.DictReader(f)]
            self._files[file] = sorted(found, key=lambda pair: pair[1]["recorded_on"])
        return self._files[file]

    def onboard(self) -> dict:
        return self._load(lambda day: day <= ONBOARDING_THROUGH.isoformat(), ONBOARDING_THROUGH)

    def day(self, day: date) -> dict:
        if day <= self.store.today() and self.store.one("SELECT 1 AS loaded FROM records LIMIT 1"):
            raise ValueError(f"{day} is already loaded; the store is at {self.store.today()}")
        return self._load(lambda recorded: recorded == day.isoformat(), day)

    def _load(self, wanted, today: date) -> dict:
        self.store.set_today(today)
        changed: dict[str, set] = defaultdict(set)
        sources: dict[tuple[str, str], Path] = {}
        with self.store.tx():
            for file, (kind, key) in FILES.items():
                for source, row in self.rows(file):
                    if wanted(row["recorded_on"]):
                        self.store.put_record(kind, row[key], row["recorded_on"], row)
                        changed[kind].add(row[key])
                        sources[(kind, row[key])] = source
            self._derive(changed, sources)
        opened, reopened = self._open_work(changed)
        return {"day": today.isoformat(), "rows": {k: len(v) for k, v in sorted(changed.items())},
                "opened": opened, "reopened": reopened}

    # Records into the shapes the core works with.

    def _derive(self, changed: dict[str, set], sources: dict) -> None:
        store = self.store
        for staff in store.records("staff"):
            store.add_staff(staff["staff_id"], f"{staff['first_name']} {staff['last_name']}",
                            ROLES.get(staff["role"], staff["role"].lower()), self._patient_records_of(staff))

        accounts = set(changed["account"])
        for mrn in changed["patient"]:
            accounts |= {r["account_no"] for r in store.records("account", "json_extract(data, '$.mrn') = ?", mrn)}
        for account_no in sorted(accounts):
            row = store.record("account", account_no)
            patient = store.record("patient", row["mrn"]) or {}
            name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip().title() or None
            store.upsert_account(account_no, patient_id=row["mrn"], patient_name=name,
                                 billed_cents=cents(row["patient_responsibility"]),
                                 first_bill_on=date.fromisoformat(row["first_statement_date"])
                                 if row["first_statement_date"] else None,
                                 sources={"billing": row, "patient": patient})
            store.add_document(f"BILL-{account_no}", account_no, BILLING, "billing_system", row["recorded_on"],
                               render_billing(row, patient))

        for application_id in sorted(changed["application"]):
            app = store.record("application", application_id)
            store.add_document(application_id, None, APPLICATION, "fa_system", app["received_on"],
                               render_application(app), application_id=application_id)
            for account_no in self._accounts_of(app):
                store.link_application(application_id, account_no)

        for note_id in sorted(changed["note"]):
            note = store.record("note", note_id)
            store.add_document(note_id, account_number(note["account_no"]), NOTE, "fa_system", note["written_on"],
                               f"{note['written_on']} {note['author']}: {note['text']}",
                               application_id=note["application_id"] or None)

        for doc_id in sorted(changed["document"]):
            doc = store.record("document", doc_id)
            text = (sources[("document", doc_id)] / "documents" / doc["file"]).read_text()
            store.add_document(doc_id, None, doc["doc_type"], "mailroom", doc["received_on"], text,
                               application_id=doc["application_id"] or None)

        for request_id in sorted(changed["request"]):
            request = store.record("request", request_id)
            account_no = account_number(request["client_account"])
            if account_no:
                store.add_agency_request(request_id, account_no, request["requested_action"],
                                         date.fromisoformat(us_date(request["requested_date"])),
                                         self._final_notice(account_no))

    def _patient_records_of(self, staff: dict) -> list[str]:
        """A staff member can also be a patient; HR doesn't say so. Same last name and birth date."""
        return [p["mrn"] for p in self.store.records(
            "patient", "upper(json_extract(data, '$.last_name')) = ? AND json_extract(data, '$.dob') = ?",
            staff["last_name"].upper(), staff["dob"])]

    def _accounts_of(self, app: dict) -> list[str]:
        listed = {a for a in (account_number(x) for x in app["accounts_given"].split(";")) if a}
        listed = {a for a in listed if self.store.record("account", a)}
        if app["mrn_given"]:
            for row in self.store.records("account", "json_extract(data, '$.mrn') = ?", app["mrn_given"].strip()):
                if row["status"] in WORKABLE_ACCOUNTS and cents(row["patient_responsibility"]) > 0:
                    listed.add(row["account_no"])
        return sorted(listed)

    def _final_notice(self, account_no: str) -> date | None:
        sent = [s["sent_on"] for s in self.store.records(
            "statement", "json_extract(data, '$.account_no') = ? AND json_extract(data, '$.kind') = 'FINAL_NOTICE'",
            account_no)]
        return date.fromisoformat(max(sent)) if sent else None

    # Work items.

    def _open_work(self, changed: dict[str, set]) -> tuple[list[str], list[str]]:
        """Open an item for each workable account a new application or agency request reaches, and put
        items waiting on information back to work when something new arrives for them."""
        reasons: dict[str, str] = {}
        news: dict[str, str] = {}
        for application_id in sorted(changed["application"]):
            app = self.store.record("application", application_id)
            for account_no in self.store.accounts_for(application_id):
                if app["status"] in UNDECIDED:
                    reasons.setdefault(account_no, f"Financial assistance application {application_id} received")
                news.setdefault(account_no, f"Application {application_id} was updated")
        for request_id in sorted(changed["request"]):
            request = self.store.one("SELECT account_id FROM agency_requests WHERE id = ?", request_id)
            if request:
                reasons.setdefault(request["account_id"], f"The agency sent request {request_id}")
        for account_no in sorted(changed["account"]):
            row = self.store.record("account", account_no)
            if row["status"] in WORKABLE_ACCOUNTS and cents(row["patient_responsibility"]) > 0 and \
                    not self.store.one("SELECT 1 AS seen FROM work_items WHERE account_id = ?", account_no) and \
                    (approval := covering_approval(self.store, account_no)):
                reasons.setdefault(account_no, f"Visit covered by approval {approval['application_id']}")
        for kind in ("document", "note"):
            for doc_id in sorted(changed[kind]):
                doc = self.store.one("SELECT account_id, application_id FROM documents WHERE id = ?", doc_id)
                accounts = [doc["account_id"]] if doc["account_id"] else self.store.accounts_for(doc["application_id"] or "")
                for account_no in accounts:
                    news.setdefault(account_no, f"New {kind} {doc_id}")

        opened, reopened = [], []
        for account_no, reason in sorted(reasons.items()):
            account = self.store.record("account", account_no)
            if account["status"] not in WORKABLE_ACCOUNTS or cents(account["patient_responsibility"]) <= 0:
                continue
            if not self._open_item(account_no):
                opened.append(self.gateway.open_work_item(self.me, account_no, reason))
        for account_no, why in sorted(news.items()):
            item = self._open_item(account_no)
            if item and item["state"] == NEEDS_INFO:
                self.gateway.move(self.me, item["id"], SCREENING, why)
                reopened.append(item["id"])
        # Items waiting for documents, not for an answer, go back to work when the wait is over.
        waited_since = (self.store.today() - timedelta(days=WAIT_FOR_DOCUMENTS_DAYS)).isoformat()
        for item in self.store.all(
                "SELECT * FROM work_items w WHERE state = ? AND updated_on <= ? AND NOT EXISTS "
                "(SELECT 1 FROM questions q WHERE q.work_item_id = w.id AND q.answer IS NULL) ORDER BY id",
                NEEDS_INFO, waited_since):
            self.gateway.move(self.me, item["id"], SCREENING,
                              f"Waited {WAIT_FOR_DOCUMENTS_DAYS} days for income documents; none came.")
            reopened.append(item["id"])
        return opened, reopened

    def _open_item(self, account_no: str) -> dict | None:
        return self.store.one(f"SELECT * FROM work_items WHERE account_id = ? AND state IN "
                              f"({', '.join('?' * len(OPEN_ITEM_STATES))}) ORDER BY id DESC",
                              account_no, *OPEN_ITEM_STATES)


def render_application(app: dict) -> str:
    def yes_no(flag):
        return {"Y": "Yes", "N": "No"}.get(flag, "not answered")

    return "\n".join([
        f"FINANCIAL ASSISTANCE APPLICATION {app['application_id']} ({app['form_version']} form)",
        f"Applicant: {app['first_name']} {app['last_name']}   Date of birth: {app['dob']}   Phone: {app['phone']}",
        f"Address: {app['address_line1']}, {app['city']}, {app['state']} {app['zip']}",
        f"MRN given: {app['mrn_given'] or 'none'}   Accounts given: {app['accounts_given'] or 'none'}",
        f"Household size: {app['household_size'] or 'not given'}",
        f"Yearly household income written by the applicant: {app['income_stated'] or 'not given'}",
        f"Enrolled in Medi-Cal: {yes_no(app['medi_cal'])}   Homeless: {yes_no(app['homeless'])}",
        f"Received: {app['received_on']}   Status: {app['status']}",
    ])


def render_billing(account: dict, patient: dict) -> str:
    address = ", ".join(x for x in (patient.get("address_line1"), patient.get("city"),
                                    f"{patient.get('state', '')} {patient.get('zip', '')}".strip()) if x)
    return "\n".join([
        f"BILLING SYSTEM REGISTRATION, account {account['account_no']}",
        f"Patient: {patient.get('first_name', '')} {patient.get('last_name', '')}   MRN: {account['mrn']}   "
        f"Date of birth: {patient.get('dob', '')}",
        f"Address: {address or 'unknown'}   Phone: {patient.get('phone', '')}",
        f"Service: {account['service_type']} on {account['service_date']}   Payer: {account['payer']}",
        f"Patient responsibility: {account['patient_responsibility']}   "
        f"First statement: {account['first_statement_date'] or 'not sent'}   Status: {account['status']}",
    ])


def main() -> None:
    args = sys.argv[1:]
    path = os.environ.get("HALCYON_DB", DEFAULT_DB)
    if args[:1] == ["onboard"]:
        for suffix in ("", "-wal", "-shm"):
            Path(path + suffix).unlink(missing_ok=True)
        print(Sync(Store(path)).onboard())
        return
    if args[:1] != ["day"] or len(args) < 2:
        raise SystemExit(__doc__)
    first = date.fromisoformat(args[1])
    last = date.fromisoformat(args[args.index("--through") + 1]) if "--through" in args else first
    store = Store(path)
    sync = Sync(store)
    work = "--work" in args
    if work:
        from .reader import Reader, ReadFailed, ReplyCache, call_claude
        agent = Agent(store, sync.gateway, Reader(store, cache=ReplyCache()))
    day = first
    while day <= last:
        summary = sync.day(day)
        print(f"{summary['day']}: opened {len(summary['opened'])}, back to work {len(summary['reopened'])}")
        if work:
            try:
                for result in agent.work_open_items():
                    print(f"  {result.account_id}  {result.did:<8}  {result.detail[:150]}")
            except ReadFailed as e:
                raise SystemExit(f"Stopped: {e}\n{call_claude.guard.summary()}") from None
        day += timedelta(days=1)
    if work:
        print(call_claude.guard.summary())


if __name__ == "__main__":
    main()
