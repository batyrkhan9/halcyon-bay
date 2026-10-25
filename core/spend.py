"""A hard cap on what the agent spends on Claude, enforced in code.

Before each call the guard books the most that call could cost: all of its
input plus max_tokens of output, and the same again on a fallback model in case
the request is declined and re-run there. If that would take total spend past
the cap, the call is refused and nothing is sent. After the call, the booking is
replaced with what the call actually cost, from the usage the API reports.

The ledger is its own small database, core/state/claude_spend.db, so the total
keeps adding up across runs, reseeds, restarts and processes. The cap is
HALCYON_CLAUDE_BUDGET_USD in .env (default $20); raising it is the only way past it.

See the totals from the repo root:  core/.venv/bin/python -m core.spend
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

DEFAULT_BUDGET_USD = 20.0
LEDGER = ROOT / "core" / "state" / "claude_spend.db"
CHARS_PER_TOKEN = 3  # deliberately low, so input estimates run high


@dataclass(frozen=True)
class Price:
    """Dollars per million tokens."""
    input: float
    output: float
    cache_write: float
    cache_read: float


PRICES = {
    "claude-opus-5-5": Price(4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": Price(2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5": Price(0.10, 0.50, 0.125, 0.01),
    "claude-opus-5": Price(5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-8": Price(5.00, 25.00, 6.25, 0.50),
    "claude-fable-5-1": Price(10.00, 50.00, 12.50, 0.25),
}
# A model not listed is priced as the most expensive one, never as free.
UNKNOWN = Price(*(max(getattr(p, f) for p in PRICES.values()) for f in ("input", "output", "cache_write", "cache_read")))
# Where a declined Claude Opus 5.5 request is re-run by fallbacks: "default".
FALLBACK = PRICES["claude-opus-4-8"]


class OverBudget(Exception):
    """The call could take spend past the cap, so it wasn't sent."""


def price(model: str | None) -> Price:
    return PRICES.get(model or "", UNKNOWN)


def worst_case_usd(request: dict) -> float:
    """The most one request could cost, with every input token billed at the cache-write rate."""
    text = json.dumps({k: request.get(k) for k in ("system", "messages", "output_config", "tools")})
    input_tokens = len(text) / CHARS_PER_TOKEN
    prices = [price(request["model"])] + ([FALLBACK] if request.get("fallbacks") else [])
    return sum((input_tokens * p.cache_write + request["max_tokens"] * p.output) / 1e6 for p in prices)


def actual_usd(usage, model: str) -> float:
    """What a call cost, from the usage on the response. Each part is priced at the model that ran it."""
    parts = getattr(usage, "iterations", None) or [usage]
    total = 0.0
    for part in parts:
        p = price(getattr(part, "model", None) or model)
        total += (part.input_tokens * p.input
                  + (part.cache_creation_input_tokens or 0) * p.cache_write
                  + (part.cache_read_input_tokens or 0) * p.cache_read
                  + part.output_tokens * p.output) / 1e6
    return total


class SpendGuard:
    def __init__(self, path: Path = LEDGER, cap_usd: float | None = None):
        self.cap = cap_usd if cap_usd is not None else float(
            os.environ.get("HALCYON_CLAUDE_BUDGET_USD", DEFAULT_BUDGET_USD))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=30)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, "
            "model TEXT NOT NULL, status TEXT NOT NULL, usd REAL NOT NULL, input_tokens INTEGER, "
            "output_tokens INTEGER, note TEXT)")
        self.lock = threading.Lock()

    def total(self) -> float:
        with self.lock:
            return self.db.execute("SELECT COALESCE(SUM(usd), 0) FROM calls").fetchone()[0]

    def book(self, request: dict) -> int:
        """Reserve the worst case for this request, or raise OverBudget if it doesn't fit."""
        worst = worst_case_usd(request)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                spent = self.db.execute("SELECT COALESCE(SUM(usd), 0) FROM calls").fetchone()[0]
                if spent + worst > self.cap:
                    raise OverBudget(
                        f"Claude spending cap reached: ${spent:.2f} of ${self.cap:.2f} used, and this call could "
                        f"cost up to ${worst:.2f}. Raise HALCYON_CLAUDE_BUDGET_USD in .env to go on.")
                booking = self.db.execute(
                    "INSERT INTO calls (at, model, status, usd) VALUES (?, ?, 'booked', ?)",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"), request["model"], worst)).lastrowid
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.db.execute("COMMIT")
        return booking

    def settle(self, booking: int, usd: float, *, status: str = "settled", input_tokens: int | None = None,
               output_tokens: int | None = None, note: str = "") -> None:
        with self.lock:
            self.db.execute("UPDATE calls SET status = ?, usd = ?, input_tokens = ?, output_tokens = ?, note = ? "
                            "WHERE id = ?", (status, usd, input_tokens, output_tokens, note, booking))

    def hold(self, booking: int, note: str) -> None:
        """Keep the worst case booked: the call may have been billed, and there is no way to know."""
        with self.lock:
            self.db.execute("UPDATE calls SET status = 'unknown', note = ? WHERE id = ?", (note, booking))

    def summary(self) -> str:
        with self.lock:
            settled, calls = self.db.execute(
                "SELECT COALESCE(SUM(usd), 0), COUNT(usd > 0 OR NULL) FROM calls WHERE status = 'settled'").fetchone()
            held = self.db.execute("SELECT COALESCE(SUM(usd), 0) FROM calls WHERE status != 'settled'").fetchone()[0]
        line = f"Claude spend: ${settled:.2f} over {calls} calls, cap ${self.cap:.2f}"
        if held:
            line += f", plus ${held:.2f} held for calls whose cost is unknown"
        return f"{line}. Left: ${max(self.cap - settled - held, 0):.2f}."


if __name__ == "__main__":
    guard = SpendGuard()
    print(guard.summary())
    for row in guard.db.execute("SELECT at, model, status, usd, input_tokens, output_tokens, note FROM calls "
                                "ORDER BY id DESC LIMIT 10"):
        print("  ", *row)
