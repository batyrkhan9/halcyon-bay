"""SQLite storage. The audit log and the ledger are append-only, enforced by the database itself."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from .model import AGENT, GATEWAY, SYNC
from .permissions import Actor

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staff (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    patient_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    patient_id TEXT,
    patient_name TEXT,
    billed_cents INTEGER NOT NULL DEFAULT 0,
    first_bill_on TEXT,
    collections_paused INTEGER NOT NULL DEFAULT 0,
    sources TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    state TEXT NOT NULL,
    reason TEXT NOT NULL,
    opened_on TEXT NOT NULL,
    updated_on TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS work_items_by_state ON work_items(state);
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    work_item_id TEXT,
    account_id TEXT,
    kind TEXT NOT NULL,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    rationale TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '[]',
    pattern TEXT,
    legal_question INTEGER NOT NULL DEFAULT 0,
    reverses TEXT,
    subject TEXT,
    status TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    proposed_on TEXT NOT NULL,
    decided_by TEXT,
    decided_on TEXT,
    decision_note TEXT
);
CREATE INDEX IF NOT EXISTS proposals_by_status ON proposals(status);
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    to_role TEXT NOT NULL,
    question TEXT NOT NULL,
    asked_by TEXT NOT NULL,
    asked_on TEXT NOT NULL,
    answer TEXT,
    answered_by TEXT,
    answered_on TEXT
);
CREATE TABLE IF NOT EXISTS records (
    kind TEXT NOT NULL,
    id TEXT NOT NULL,
    recorded_on TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (kind, id)
);
CREATE INDEX IF NOT EXISTS records_by_mrn ON records(kind, json_extract(data, '$.mrn'));
CREATE INDEX IF NOT EXISTS records_by_account ON records(kind, json_extract(data, '$.account_no'));
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    application_id TEXT,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    dated TEXT,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS documents_by_account ON documents(account_id);
CREATE INDEX IF NOT EXISTS documents_by_application ON documents(application_id);
CREATE TABLE IF NOT EXISTS application_accounts (
    application_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    PRIMARY KEY (application_id, account_id)
);
CREATE TABLE IF NOT EXISTS agency_requests (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    action TEXT NOT NULL,
    requested_on TEXT NOT NULL,
    notice_sent_on TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN'
);
CREATE TABLE IF NOT EXISTS claude_replies (
    key TEXT PRIMARY KEY,
    reply TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rejected_patterns (
    pattern TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    rejected_by TEXT NOT NULL,
    rejected_on TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT NOT NULL,
    account_id TEXT,
    kind TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    reverses TEXT,
    posted_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at TEXT NOT NULL,
    sim_day TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    account_id TEXT,
    allowed INTEGER NOT NULL,
    reason TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS audit_by_account ON audit_log(account_id, seq);

-- History is never edited or deleted. Mistakes are fixed with a reversal.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'the ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'the ledger is append-only'); END;
"""

SYSTEM_ACTORS = {
    SYNC: Actor(SYNC, SYNC, "Sync job"),
    AGENT: Actor(AGENT, AGENT, "AI agent"),
    GATEWAY: Actor(GATEWAY, GATEWAY, "Gateway"),
}

JSON_COLUMNS = ("sources", "evidence", "detail", "patient_ids", "reply", "data")
FIRST_SIM_DAY = date(2026, 7, 1)


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.lock = threading.RLock()
        self.db.executescript(SCHEMA)

    @contextmanager
    def tx(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.db.execute("COMMIT")

    def all(self, sql: str, *args) -> list[dict]:
        with self.lock:
            return [_row(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql: str, *args) -> dict | None:
        rows = self.all(sql, *args)
        return rows[0] if rows else None

    def run(self, sql: str, *args) -> None:
        with self.lock:
            self.db.execute(sql, args)

    # Simulated clock.

    def today(self) -> date:
        row = self.one("SELECT value FROM settings WHERE key = 'today'")
        return date.fromisoformat(row["value"]) if row else FIRST_SIM_DAY

    def set_today(self, day: date) -> None:
        self.run("INSERT INTO settings (key, value) VALUES ('today', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", day.isoformat())

    def next_id(self, prefix: str) -> str:
        key = f"seq:{prefix}"
        with self.lock:
            row = self.one("SELECT value FROM settings WHERE key = ?", key)
            n = int(row["value"]) + 1 if row else 1
            self.run("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", key, str(n))
        return f"{prefix}-{n:04d}"

    # People.

    def add_staff(self, id: str, name: str, role: str, patient_ids: list[str] = ()) -> None:
        self.run("INSERT OR REPLACE INTO staff (id, name, role, patient_ids) VALUES (?, ?, ?, ?)",
                 id, name, role, json.dumps(list(patient_ids)))

    def actor(self, actor_id: str) -> Actor | None:
        if actor_id in SYSTEM_ACTORS:
            return SYSTEM_ACTORS[actor_id]
        row = self.one("SELECT * FROM staff WHERE id = ?", actor_id)
        if row is None:
            return None
        return Actor(row["id"], row["role"], row["name"], frozenset(row["patient_ids"]))

    def staff_for_patient(self, patient_id: str | None) -> dict | None:
        """The staff member whose own patient record this is, if any."""
        if not patient_id:
            return None
        for row in self.all("SELECT id, name, role, patient_ids FROM staff"):
            if patient_id in row["patient_ids"]:
                return row
        return None

    # Accounts.

    def upsert_account(self, id: str, *, patient_id: str | None, patient_name: str | None,
                       billed_cents: int, first_bill_on: date | None, sources: dict) -> None:
        self.run(
            "INSERT INTO accounts (id, patient_id, patient_name, billed_cents, first_bill_on, sources) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET patient_id = excluded.patient_id, "
            "patient_name = excluded.patient_name, billed_cents = excluded.billed_cents, "
            "first_bill_on = excluded.first_bill_on, sources = excluded.sources",
            id, patient_id, patient_name, billed_cents,
            first_bill_on.isoformat() if first_bill_on else None, json.dumps(sources),
        )

    def account(self, account_id: str) -> dict | None:
        return self.one("SELECT * FROM accounts WHERE id = ?", account_id)

    def work_item(self, item_id: str) -> dict | None:
        return self.one("SELECT * FROM work_items WHERE id = ?", item_id)

    def proposal(self, proposal_id: str) -> dict | None:
        return self.one("SELECT * FROM proposals WHERE id = ?", proposal_id)

    def question(self, question_id: str) -> dict | None:
        return self.one("SELECT * FROM questions WHERE id = ?", question_id)

    def rejected_pattern(self, pattern: str) -> dict | None:
        return self.one("SELECT * FROM rejected_patterns WHERE pattern = ?", pattern)

    # Documents, agency requests and Claude's replies.

    def add_document(self, id: str, account_id: str | None, kind: str, source: str, dated: date | str | None,
                     text: str, application_id: str | None = None) -> None:
        self.run("INSERT OR REPLACE INTO documents (id, account_id, application_id, kind, source, dated, text) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)", id, account_id, application_id, kind, source,
                 dated.isoformat() if isinstance(dated, date) else dated, text)

    def documents(self, account_id: str) -> list[dict]:
        """Documents filed under the account, or under any application that covers it."""
        return self.all("SELECT * FROM documents WHERE account_id = ? OR application_id IN "
                        "(SELECT application_id FROM application_accounts WHERE account_id = ?) ORDER BY id",
                        account_id, account_id)

    # Source records, exactly as each system exported them. Latest wins per (kind, id).

    def put_record(self, kind: str, id: str, recorded_on: str, data: dict) -> None:
        self.run("INSERT INTO records (kind, id, recorded_on, data) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(kind, id) DO UPDATE SET recorded_on = excluded.recorded_on, data = excluded.data "
                 "WHERE excluded.recorded_on >= records.recorded_on", kind, id, recorded_on, json.dumps(data))

    def record(self, kind: str, id: str) -> dict | None:
        row = self.one("SELECT data FROM records WHERE kind = ? AND id = ?", kind, id)
        return row["data"] if row else None

    def records(self, kind: str, where: str = "", *args) -> list[dict]:
        sql = "SELECT data FROM records WHERE kind = ?" + (f" AND {where}" if where else "") + " ORDER BY id"
        return [r["data"] for r in self.all(sql, kind, *args)]

    def link_application(self, application_id: str, account_id: str) -> None:
        self.run("INSERT OR IGNORE INTO application_accounts (application_id, account_id) VALUES (?, ?)",
                 application_id, account_id)

    def applications_for(self, account_id: str) -> list[str]:
        return [r["application_id"] for r in self.all(
            "SELECT application_id FROM application_accounts WHERE account_id = ? ORDER BY application_id", account_id)]

    def accounts_for(self, application_id: str) -> list[str]:
        return [r["account_id"] for r in self.all(
            "SELECT account_id FROM application_accounts WHERE application_id = ? ORDER BY account_id", application_id)]

    def add_agency_request(self, id: str, account_id: str, action: str, requested_on: date,
                           notice_sent_on: date | None = None) -> None:
        self.run("INSERT OR REPLACE INTO agency_requests (id, account_id, action, requested_on, notice_sent_on) "
                 "VALUES (?, ?, ?, ?, ?)", id, account_id, action, requested_on.isoformat(),
                 notice_sent_on.isoformat() if notice_sent_on else None)

    def open_agency_requests(self, account_id: str) -> list[dict]:
        return self.all("SELECT * FROM agency_requests WHERE account_id = ? AND status = 'OPEN' ORDER BY id",
                        account_id)

    def cached_reply(self, key: str) -> dict | None:
        row = self.one("SELECT reply FROM claude_replies WHERE key = ?", key)
        return row["reply"] if row else None

    def save_reply(self, key: str, reply: dict) -> None:
        self.run("INSERT OR REPLACE INTO claude_replies (key, reply) VALUES (?, ?)", key, json.dumps(reply))

    def replies(self) -> dict:
        return {r["key"]: r["reply"] for r in self.all("SELECT key, reply FROM claude_replies ORDER BY key")}

    # Audit log.

    def log(self, actor: Actor, action: str, *, target: str | None, account_id: str | None,
            allowed: bool, reason: str, detail: dict | None = None) -> None:
        self.run(
            "INSERT INTO audit_log (logged_at, sim_day, actor_id, actor_role, action, target, account_id, "
            "allowed, reason, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            datetime.now(timezone.utc).isoformat(timespec="seconds"), self.today().isoformat(),
            actor.id, actor.role, action, target, account_id, int(allowed), reason,
            json.dumps(detail or {}, default=str),
        )

    def why(self, account_id: str) -> dict | None:
        """An account's whole story in one query per table: sources, work, decisions and the audit trail."""
        account = self.account(account_id)
        if account is None:
            return None
        return {
            "account": account,
            "documents": self.documents(account_id),
            "agency_requests": self.all("SELECT * FROM agency_requests WHERE account_id = ? ORDER BY id", account_id),
            "work_items": self.all("SELECT * FROM work_items WHERE account_id = ? ORDER BY id", account_id),
            "proposals": self.all("SELECT * FROM proposals WHERE account_id = ? ORDER BY id", account_id),
            "questions": self.all("SELECT * FROM questions WHERE account_id = ? ORDER BY id", account_id),
            "ledger": self.all("SELECT * FROM ledger WHERE account_id = ? ORDER BY seq", account_id),
            "audit": self.all("SELECT * FROM audit_log WHERE account_id = ? ORDER BY seq", account_id),
        }


def _row(row: sqlite3.Row) -> dict:
    out = dict(row)
    for key in JSON_COLUMNS:
        if key in out and isinstance(out[key], str):
            out[key] = json.loads(out[key])
    for key in ("allowed", "legal_question", "collections_paused"):
        if key in out and out[key] is not None:
            out[key] = bool(out[key])
    return out
