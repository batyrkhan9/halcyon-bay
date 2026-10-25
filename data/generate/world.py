"""The simulated hospital's records as Python objects, and how they become CSV files.

Records point at each other as objects. IDs are handed out at the end, in the
order the records appeared, so every ID sequence runs forward in time like a
real system's would.
"""

from __future__ import annotations

import csv
import io
import random
from datetime import date, timedelta

from rules import money

HISTORY_START = date(2025, 1, 1)
HISTORY_END = date(2026, 6, 30)
LIVE_START = date(2026, 7, 1)
WORLD_END = date(2026, 9, 30)

COLUMNS = {
    "billing/patients.csv": ["recorded_on", "mrn", "last_name", "first_name", "middle_initial", "dob", "ssn",
                             "address_line1", "city", "state", "zip", "phone", "registered_on"],
    "billing/accounts.csv": ["recorded_on", "account_no", "mrn", "service_date", "discharge_date", "service_type",
                             "payer", "total_charges", "insurance_paid", "insurance_adjustment",
                             "patient_responsibility", "first_statement_date", "status"],
    "billing/transactions.csv": ["recorded_on", "txn_id", "account_no", "posted_on", "txn_type", "amount", "note"],
    "billing/statements.csv": ["recorded_on", "statement_id", "account_no", "sent_on", "kind", "amount_due",
                               "mailed_to", "returned_mail"],
    "billing/payment_plans.csv": ["recorded_on", "plan_id", "mrn", "account_nos", "start_date", "monthly_amount",
                                  "months", "status", "missed_payments", "last_payment_on", "stopped_on",
                                  "stopped_by", "stop_reason"],
    "fa/applications.csv": ["recorded_on", "application_id", "applicant_id", "mrn_given", "accounts_given",
                            "first_name", "last_name", "dob", "ssn", "phone", "address_line1", "city", "state",
                            "zip", "household_size", "income_stated", "income_verified", "income_proof",
                            "monetary_assets", "medi_cal", "homeless", "received_on", "form_version", "status",
                            "decision", "decision_date", "decided_by", "reason"],
    "fa/notes.csv": ["recorded_on", "note_id", "application_id", "account_no", "author", "written_on", "text"],
    "agency/placements.csv": ["recorded_on", "agency_ref", "client_account", "debtor_name", "debtor_dob",
                              "debtor_address", "debtor_phone", "placed_date", "placed_balance", "current_balance",
                              "status", "last_activity"],
    "agency/requests.csv": ["recorded_on", "request_id", "agency_ref", "client_account", "requested_action",
                            "requested_date", "agency_note"],
    "documents/index.csv": ["recorded_on", "doc_id", "application_id", "name_on_document", "doc_type",
                            "received_on", "file"],
    "staff/staff.csv": ["recorded_on", "staff_id", "first_name", "last_name", "role", "approval_limit", "email",
                        "dob", "address_line1", "city", "state", "zip", "phone", "active"],
    "policy/index.csv": ["recorded_on", "version", "effective_from", "effective_to", "file"],
}

ANSWER_COLUMNS = {
    "live_accounts.csv": ["account_no", "person", "outcome", "fpl_pct", "adjustment", "patient_owes", "refund",
                          "monthly_payment", "handling", "ask_role", "approver_role", "required_actions",
                          "forbidden_actions", "planted", "reason"],
    "history_findings.csv": ["finding", "application_id", "person", "accounts", "decision_date", "decided_by",
                             "stated_reason", "fpl_pct", "correct_outcome", "adjustment", "refund", "law", "reason"],
    "calfresh_backtest.csv": ["application_id", "person", "accounts", "original_status", "original_decision",
                              "with_rule", "changes", "dollars", "reason"],
    "patterns.csv": ["pattern", "evidence_count", "legal", "note"],
}


def clamp(day: date) -> date:
    """Records that existed before the export starts show up on its first day."""
    return HISTORY_START if day < HISTORY_START else day


def iso(d: date | None) -> str:
    return "" if d is None else d.isoformat()


def mdy(d: date | None) -> str:
    return "" if d is None else d.strftime("%m/%d/%Y")


class Rec:
    """One record. Keyed records keep every version; event records have one."""

    def __init__(self, world: "World", rkind: str, first_day: date, **fields):
        self.world = world
        self.rkind = rkind
        self.seq = world.next_seq()
        self.first_day = first_day
        self.id: str | None = None
        self.f = dict(fields)                       # current state
        self.versions: list[tuple[date, dict]] = []

    def snap(self, day: date, **changes) -> "Rec":
        self.f.update(changes)
        self.versions.append((day, dict(self.f)))
        return self

    def __repr__(self):
        return f"<{self.rkind} {self.id or self.seq}>"


class Person:
    """The truth about one human. Only the answer key knows it."""

    def __init__(self, seq: int, **kw):
        self.seq = seq
        self.pid: str | None = None
        self.persona: str | None = kw.pop("persona", None)
        self.__dict__.update(kw)


class World:
    def __init__(self, id_rng: random.Random):
        self.id_rng = id_rng
        self._seq = 0
        self.people: list[Person] = []
        self.patients: list[Rec] = []
        self.accounts: list[Rec] = []
        self.txns: list[Rec] = []
        self.statements: list[Rec] = []
        self.plans: list[Rec] = []
        self.apps: list[Rec] = []
        self.applicants: list[Rec] = []
        self.notes: list[Rec] = []
        self.placements: list[Rec] = []
        self.requests: list[Rec] = []
        self.docs: list[Rec] = []
        self.answers: list[dict] = []
        self.findings: list[dict] = []
        self.backtest: list[dict] = []
        self.planted: list[dict] = []
        self.patterns: list[dict] = []

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # ---------- creation helpers ----------

    def person(self, **kw) -> Person:
        p = Person(self.next_seq(), **kw)
        self.people.append(p)
        return p

    def patient(self, person: Person, registered_on: date, **fields) -> Rec:
        r = Rec(self, "patient", registered_on, person=person, registered_on=registered_on, **fields)
        r.snap(clamp(registered_on))
        self.patients.append(r)
        return r

    def account(self, patient: Rec, recorded: date, **fields) -> Rec:
        r = Rec(self, "account", recorded, patient=patient, **fields)
        r.txn_list = []
        r.final_notices = []
        r.statement_stop = None
        r.returned_mail = False
        r.mail_to = None
        r.no_monthly = False
        self.accounts.append(r)
        return r

    def txn(self, account: Rec, posted_on: date, txn_type: str, amount_cents: int, note: str = "",
            recorded: date | None = None) -> Rec:
        rec_day = recorded or posted_on
        r = Rec(self, "txn", rec_day, account=account, posted_on=posted_on, txn_type=txn_type,
                amount=amount_cents, note=note, recorded=rec_day)
        account.txn_list.append(r)
        self.txns.append(r)
        return r

    def balance(self, account: Rec, on: date) -> int:
        return sum(t.f["amount"] for t in account.txn_list if t.f["recorded"] <= on)

    def paid_by_patient(self, account: Rec, on: date) -> int:
        """Patient money in (payments and agency collections) net of refunds, as of `on`."""
        total = 0
        for t in account.txn_list:
            if t.f["recorded"] > on:
                continue
            if t.f["txn_type"] in ("PATIENT_PAYMENT", "AGENCY_PAYMENT"):
                total -= t.f["amount"]
            elif t.f["txn_type"] == "REFUND":
                total -= t.f["amount"]
        return total

    def statement(self, account: Rec, sent_on: date, kind: str, amount_cents: int, mailed_to: str,
                  returned: bool = False) -> Rec:
        r = Rec(self, "statement", sent_on, account=account, sent_on=sent_on, kind=kind, amount_due=amount_cents,
                mailed_to=mailed_to, returned_mail="Y" if returned else "")
        self.statements.append(r)
        return r

    def plan(self, patient: Rec, accounts: list[Rec], created: date, **fields) -> Rec:
        r = Rec(self, "plan", created, patient=patient, accounts=accounts, **fields)
        self.plans.append(r)
        return r

    def applicant(self, person: Person, first_day: date) -> Rec:
        r = Rec(self, "applicant", first_day, person=person)
        self.applicants.append(r)
        return r

    def app(self, applicant: Rec, received_on: date, **fields) -> Rec:
        r = Rec(self, "app", received_on, applicant=applicant, received_on=received_on, **fields)
        self.apps.append(r)
        return r

    def note(self, written_on: date, author: str, text: str, app: Rec | None = None,
             account: Rec | None = None) -> Rec:
        r = Rec(self, "note", written_on, app=app, account=account, author=author, written_on=written_on,
                text=text)
        self.notes.append(r)
        return r

    def placement(self, account: Rec, placed: date, **fields) -> Rec:
        r = Rec(self, "placement", placed, account=account, placed_date=placed, **fields)
        self.placements.append(r)
        return r

    def request(self, placement: Rec, on: date, action: str, note: str) -> Rec:
        r = Rec(self, "request", on, placement=placement, requested_action=action, requested_date=on,
                agency_note=note)
        self.requests.append(r)
        return r

    def doc(self, app: Rec | None, received: date, doc_type: str, name: str, text: str) -> Rec:
        r = Rec(self, "doc", received, app=app, received_on=received, doc_type=doc_type,
                name_on_document=name, text=text)
        self.docs.append(r)
        return r

    # ---------- ids ----------

    def assign_ids(self) -> None:
        rng = self.id_rng

        def seq_ids(recs, key, fmt, start, gap=(1, 3)):
            n = start
            for r in sorted(recs, key=key):
                n += rng.randint(*gap)
                r.id = fmt(n)

        seq_ids(self.patients, lambda r: (r.f["registered_on"], r.seq), lambda n: f"M{n:07d}", 1_204_000, (1, 9))
        by_year: dict[int, list[Rec]] = {}
        for a in self.accounts:
            by_year.setdefault(a.f["service_date"].year, []).append(a)
        for year in sorted(by_year):
            seq_ids(by_year[year], lambda r: (r.first_day, r.seq), lambda n, y=year: f"HB{y % 100:02d}{n:06d}",
                    310_000 if year == 2024 else 100_000, (2, 40))
        seq_ids(self.txns, lambda r: (clamp(r.f["recorded"]), r.f["posted_on"], r.seq), lambda n: f"T{n:08d}",
                40_100_000, (1, 6))
        seq_ids(self.statements, lambda r: (r.f["sent_on"], r.seq), lambda n: f"ST{n:07d}", 5_010_000, (1, 5))
        seq_ids(self.plans, lambda r: (r.first_day, r.seq), lambda n: f"PP{n:05d}", 20_400, (1, 3))
        seq_ids(self.applicants, lambda r: (r.first_day, r.seq), lambda n: f"APL-{n:06d}", 300_000, (1, 4))
        apps_by_year: dict[int, list[Rec]] = {}
        for a in self.apps:
            apps_by_year.setdefault(a.f["received_on"].year, []).append(a)
        for year in sorted(apps_by_year):
            seq_ids(apps_by_year[year], lambda r: (r.f["received_on"], r.seq),
                    lambda n, y=year: f"FA-{y % 100:02d}-{n:05d}", 0 if year >= 2025 else 4_100, (1, 2))
        seq_ids(self.notes, lambda r: (r.f["written_on"], r.seq), lambda n: f"N{n:07d}", 7_000_000, (1, 4))
        seq_ids(self.placements, lambda r: (r.first_day, r.seq), lambda n: f"GCR-{n:06d}", 610_000, (3, 25))
        seq_ids(self.requests, lambda r: (r.first_day, r.seq), lambda n: f"GCR-R-{n:05d}", 40_000, (2, 11))
        seq_ids(self.docs, lambda r: (r.f["received_on"], r.seq), lambda n: f"DOC-{n:06d}", 100_000, (1, 3))
        for i, p in enumerate(sorted(self.people, key=lambda p: p.seq), start=1):
            p.pid = f"PER-{i:05d}"


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Rec):
        return v.id
    if hasattr(v, "lazy_id"):
        return v.lazy_id()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return ";".join(_cell(x) for x in v)
    return str(v)


def csv_text(columns: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns)
    for row in rows:
        w.writerow([_cell(v) for v in row])
    return buf.getvalue()


def versions_rows(rec: Rec, make_row) -> list[tuple[date, int, list]]:
    """One row per version; versions recorded the same day collapse to the last one."""
    by_day: dict[date, dict] = {}
    for day, state in rec.versions:
        by_day[clamp(day)] = state
    out = []
    for day in sorted(by_day):
        if day > WORLD_END:
            continue
        out.append((day, rec.seq, make_row(day, by_day[day])))
    return out
