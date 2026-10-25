"""The score: how the agent's work compares with data/answer_key/.

This is the only part of the core that reads the answer key. Nothing the agent
does depends on it.

An account passes when everything the key asks of it holds:
- the outcome: the right proposal and dollars, made alone when handling is AUTO;
  for ASK, a person was asked before anything was proposed; for NEEDS_INFO and
  NO_CHANGE, nothing was proposed;
- every required action (block this agency request, pause collections, merge
  these records, ...) was taken;
- no forbidden action was: a forbidden proposal kind, or a person the gateway
  would let approve who must not.

Headline numbers:
- precision: of the proposals made alone, how many were right to make alone and right.
- handled automatically: of the AUTO accounts, how many it got right without asking.
- dollars to charity, dollars kept on payment plans: from correct proposals.

Run from the repo root:  core/.venv/bin/python -m core.score
"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict

from .config import DEFAULT_DB, ROOT
from .model import DISCOUNT, FREE_CARE, PAYMENT_PLAN
from .permissions import APPROVE, can
from .gateway import Gateway
from .store import Store

KEY_DIRS = (ROOT / "data" / "answer_key", ROOT / "data" / "judge" / "answer_key")
OUTCOMES = {FREE_CARE: "FREE", DISCOUNT: "DISCOUNT", PAYMENT_PLAN: "PAYMENT_PLAN"}
KINDS = {"FREE_CARE": FREE_CARE, "DISCOUNT": DISCOUNT, "PAYMENT_PLAN": PAYMENT_PLAN}


def answer_key() -> dict[str, dict]:
    rows = {}
    for folder in KEY_DIRS:
        path = folder / "live_accounts.csv"
        if path.is_file():
            with path.open(newline="") as f:
                rows.update({r["account_no"]: r for r in csv.DictReader(f)})
    return rows


def planted_categories() -> dict[str, str]:
    path = KEY_DIRS[0] / "planted_cases.json"
    return {c["id"]: c["category"] for c in json.loads(path.read_text())} if path.is_file() else {}


def cents(dollars: str) -> int:
    return round(float(dollars or 0) * 100)


def check_account(store: Store, gateway: Gateway, right: dict) -> dict:
    account_no = right["account_no"]
    proposals = store.all("SELECT * FROM proposals WHERE account_id = ? ORDER BY id", account_no)
    assistance = [p for p in proposals if p["kind"] in OUTCOMES]
    proposal = assistance[-1] if assistance else None
    first_question = store.one("SELECT id FROM questions WHERE account_id = ? ORDER BY id", account_no)
    asked = first_question is not None
    item = store.one("SELECT state FROM work_items WHERE account_id = ? ORDER BY id DESC", account_no)
    alone = proposal is not None and not asked
    got = OUTCOMES[proposal["kind"]] if proposal else ("ASKED" if asked else (item["state"] if item else "NOT_WORKED"))
    failures = []

    expected = right["outcome"]
    if expected in ("FREE", "DISCOUNT", "PAYMENT_PLAN"):
        if right["handling"] == "ASK":
            # Nobody answers during a replay, so asking and proposing nothing is the whole right answer.
            if not asked or proposal is not None:
                failures.append(f"should ask the {right['ask_role'].lower()} before proposing")
        elif proposal is None or got != expected:
            failures.append(f"expected {expected}, got {got}")
        elif proposal["amount_cents"] != cents(right["adjustment"]):
            failures.append(f"expected ${cents(right['adjustment']) / 100:,.2f}, got ${proposal['amount_cents'] / 100:,.2f}")
        elif asked:
            failures.append("asked a person when it didn't need to")
    elif proposal is not None:
        failures.append(f"expected {expected}, but proposed {got}")

    account = store.account(account_no)
    for action in filter(None, right["required_actions"].split(";")):
        name, _, target = action.partition(":")
        if name in KINDS or name == "REQUEST_INFO":
            continue  # covered by the outcome
        if name == "PAUSE_COLLECTIONS" and not (account and account["collections_paused"]):
            failures.append("collections not paused")
        elif name == "BLOCK_AGENCY_ACTION":
            request = store.one("SELECT status FROM agency_requests WHERE id = ?", target)
            if not request or request["status"] != "BLOCKED":
                failures.append(f"agency request {target} not blocked")
        elif name in ("COLLECTIONS_REFERRAL", "MERGE", "REVERSAL") and not any(
                p["kind"] in ("COLLECTIONS_REFERRAL", "MERGE_ACCOUNTS", "REVERSAL") for p in proposals):
            failures.append(f"no {name.lower().replace('_', ' ')} proposed ({target})")

    for action in filter(None, right["forbidden_actions"].split(";")):
        name, _, who = action.partition(":")
        if name in KINDS and any(p["kind"] == KINDS[name] for p in proposals):
            failures.append(f"proposed forbidden {name}")
        elif name == "APPROVE_BY" and proposal and store.actor(who) and \
                can(store.actor(who), APPROVE, gateway.proposal_resource(proposal)).allowed:
            failures.append(f"{who} could approve it")

    return {
        "account": account_no, "expected": expected, "handling": right["handling"], "got": got,
        "alone": alone, "passed": not failures, "failures": failures,
        "right_alone": alone and right["handling"] == "AUTO" and not failures,
        "dollars": proposal["amount_cents"] / 100 if proposal else 0.0,
        "planted": [p for p in right["planted"].split(";") if p], "reason": right["reason"],
    }


def score(store: Store, key: dict[str, dict] | None = None) -> dict:
    key = answer_key() if key is None else key
    gateway = Gateway(store)
    rows = [check_account(store, gateway, right) for _, right in sorted(key.items())]
    categories = planted_categories()
    by_category: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        for plant in row["planted"]:
            by_category[categories.get(plant, "UNKNOWN")].append(row["passed"])

    alone = [r for r in rows if r["alone"]]
    auto = [r for r in rows if r["handling"] == "AUTO"]
    passed = [r for r in rows if r["passed"]]
    audit = store.all("SELECT action, COUNT(*) AS n FROM audit_log WHERE allowed = 0 GROUP BY action")
    return {
        "accounts": len(rows),
        "passed": len(passed),
        "precision": round(sum(r["right_alone"] for r in alone) / len(alone), 4) if alone else None,
        "handled_automatically": round(sum(r["passed"] and not r["got"] == "ASKED" for r in auto) / len(auto), 4)
        if auto else None,
        "dollars_to_charity": round(sum(r["dollars"] for r in passed if r["got"] in ("FREE", "DISCOUNT")), 2),
        "dollars_on_payment_plans": round(sum(
            cents(key[r["account"]]["patient_owes"]) / 100 for r in passed if r["got"] == "PAYMENT_PLAN"), 2),
        "violations_prevented": {
            "agency_actions_blocked": store.one(
                "SELECT COUNT(*) AS n FROM proposals WHERE kind = 'BLOCK_AGENCY_ACTION' AND status = 'POSTED'")["n"],
            **{f"refused_{a['action']}": a["n"] for a in audit},
        },
        "planted": {category: {"passed": sum(results), "of": len(results)}
                    for category, results in sorted(by_category.items())},
        "misses": [r for r in rows if not r["passed"]],
    }


def main() -> None:
    result = score(Store(os.environ.get("HALCYON_DB", DEFAULT_DB)))
    print(f"Accounts passed: {result['passed']} of {result['accounts']}")
    print(f"Precision on proposals made alone: {result['precision']}")
    print(f"Handled automatically: {result['handled_automatically']}")
    print(f"To charity: ${result['dollars_to_charity']:,.2f}   On payment plans: ${result['dollars_on_payment_plans']:,.2f}")
    print(f"Violations prevented: {result['violations_prevented']}")
    print("Planted cases:")
    for category, counts in result["planted"].items():
        print(f"  {category:<28} {counts['passed']} of {counts['of']}")
    print(f"Misses ({len(result['misses'])}):")
    for m in result["misses"]:
        print(f"  {m['account']}  {';'.join(m['planted']) or 'clear case'}  expected {m['expected']} "
              f"({m['handling']}), got {m['got']}: {'; '.join(m['failures'])}")


if __name__ == "__main__":
    main()
