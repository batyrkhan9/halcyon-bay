"""A tiny fake office so the UI has something to show before data/ lands.

Every person and account here is made up. The script plays the agent's part
with plain screening code; the real agent replaces it once data/FORMAT.md exists.

Run from the repo root:  core/.venv/bin/python -m core.dev_seed
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from . import law
from .api import DEFAULT_DB
from .gateway import Denied, Gateway
from .model import (
    AGENT, BLOCK_AGENCY_ACTION, COMPLIANCE, COUNSELOR, DIRECTOR, NEEDS_INFO, PAUSE_COLLECTIONS,
    REVERSAL, SCREENING, SYNC,
)
from .policy import OTHER_PROOF, PAY_STUBS, Applicant, screen
from .store import Store

STAFF = [
    ("S-001", "Dana Okafor", COUNSELOR, []),
    ("S-002", "Luis Ferreira", DIRECTOR, []),
    ("S-003", "Priya Raman", COMPLIANCE, []),
    ("S-004", "Tomas Brandt", COUNSELOR, ["PAT-1006"]),   # a counselor who is also a patient
]

# (account, patient, name, billed cents, applicant)
ACCOUNTS = [
    ("ACC-1001", "PAT-1001", "Mara Ellison", 3_200_00, Applicant(4, 40_000, PAY_STUBS)),
    ("ACC-1002", "PAT-1002", "Owen Achebe", 12_000_00, Applicant(4, 99_000, PAY_STUBS)),
    ("ACC-1003", "PAT-1003", "Lena Vasquez", 2_400_00, Applicant(2, 43_300, OTHER_PROOF)),
    ("ACC-1004", "PAT-1004", "Jun Takeda", 1_800_00, Applicant(1, 90_000, PAY_STUBS)),
    ("ACC-1005", "PAT-1005", "Ruth Calloway", 6_500_00, Applicant(3, None, None)),
    ("ACC-1006", "PAT-1006", "Tomas Brandt", 4_100_00, Applicant(2, 30_000, PAY_STUBS)),
]


def seed(store: Store) -> None:
    gw = Gateway(store)
    sync, agent = store.actor(SYNC), store.actor(AGENT)
    today = date(2026, 7, 1)
    store.set_today(today)
    for staff in STAFF:
        store.add_staff(*staff)

    for account_id, patient_id, name, billed, applicant in ACCOUNTS:
        store.upsert_account(account_id, patient_id=patient_id, patient_name=name, billed_cents=billed,
                             first_bill_on=date(2026, 3, 2), sources={"seed": "core/dev_seed.py"})
        item = gw.open_work_item(sync, account_id, "Self-pay balance with no financial assistance decision")
        gw.move(agent, item, SCREENING, "Checking for financial assistance")
        result = screen(applicant, billed, today)
        if result.outcome == NEEDS_INFO or result.question:
            gw.ask(agent, item, COUNSELOR, result.question)
            continue
        gw.propose(agent, item, result.outcome, amount_cents=result.adjustment_cents, rationale=result.reason,
                   evidence=[{"source": "seed", "household": applicant.household,
                              "income": applicant.annual_income, "proof": applicant.income_proof}])

    # The agency asks to report a balance to credit bureaus; the agent blocks it alone.
    violations = law.check_collection_action(law.CREDIT_REPORT, first_bill=date(2026, 3, 2), on=today,
                                             notice_sent=None, screened_for_assistance=False)
    reasons = "; ".join(f"{v.law}: {v.text}" for v in violations)
    gw.act_safe(agent, "ACC-1005", BLOCK_AGENCY_ACTION, rationale=f"Agency asked to credit report. {reasons}",
                evidence=[{"source": "agency_file", "request": "CREDIT_REPORT"}])
    gw.act_safe(agent, "ACC-1005", PAUSE_COLLECTIONS, rationale="Financial assistance screening is open.")

    # A past denial that broke AB 2297, sent to compliance for a reversal.
    store.upsert_account("ACC-0907", patient_id="PAT-0907", patient_name="Gil Moreno", billed_cents=5_400_00,
                         first_bill_on=date(2025, 2, 3), sources={"seed": "core/dev_seed.py"})
    item = gw.open_work_item(sync, "ACC-0907", "Past denial flagged at onboarding")
    gw.move(agent, item, SCREENING, "Checking the past denial against the law")
    pct = law.percent_of_poverty(31_000, 2, 2025)
    found = law.check_denial(reason=law.DENIED_SAVINGS, decided_on=date(2025, 4, 18), pct_of_poverty=pct)
    gw.propose(agent, item, REVERSAL, amount_cents=5_400_00, legal_question=True, reverses="fa_decision:FA-0907",
               rationale=f"Denied on Apr 18, 2025 for savings at {pct:.0f}% of poverty. "
                         + "; ".join(f"{v.law}: {v.text}" for v in found),
               evidence=[{"source": "fa_system", "decision": "FA-0907", "reason": "SAVINGS_OVER_LIMIT"}])

    # The agent tries to post on its own. The gateway refuses and logs it.
    first = store.one("SELECT id FROM proposals WHERE status = 'PROPOSED' ORDER BY id")
    try:
        gw.post(agent, first["id"])
    except Denied:
        pass


if __name__ == "__main__":
    path = os.environ.get("HALCYON_DB", DEFAULT_DB)
    for suffix in ("", "-wal", "-shm"):
        Path(path + suffix).unlink(missing_ok=True)
    seed(Store(path))
    print(f"Seeded {path}")
