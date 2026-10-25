"""The answer key's rules, in plain code. Standard library only.

This mirrors core/law.py and core/policy.py on purpose (same tables, same
cutoffs, same rounding) so the answer key agrees with the core. validate.py
cross-checks the two when core/ can be imported.
"""

from __future__ import annotations

from datetime import date, timedelta

POVERTY_GUIDELINES = {
    2025: (15_650, 5_500),
    2026: (15_960, 5_680),
}

FREE_UP_TO_PCT = 200
DISCOUNT_UP_TO_PCT = 400
DISCOUNT_PATIENT_SHARE_PCT = 30
CUTOFF_MARGIN_PCT = 5
APPROVAL_COVERS_MONTHS = 12
COUNSELOR_LIMIT_CENTS = 5_000_00

ECA_WAIT_DAYS = 120
ECA_NOTICE_DAYS = 30
APPLICATION_WINDOW_DAYS = 240
CA_SUIT_OR_SALE_WAIT_DAYS = 180
AB_2297_EFFECTIVE = date(2025, 1, 1)
SB_1061_EFFECTIVE = date(2025, 1, 1)
OLD_POLICY_END = date(2025, 6, 30)

ECA_ACTIONS = ("CREDIT_REPORT", "LAWSUIT", "SELL_DEBT", "LIEN")


def poverty_line(year: int, household: int) -> int:
    first, extra = POVERTY_GUIDELINES[year]
    return first + extra * (household - 1)


def pct_of_poverty(annual_income: float, household: int, year: int) -> float:
    return 100 * annual_income / poverty_line(year, household)


def band(pct: float) -> str:
    if pct <= FREE_UP_TO_PCT:
        return "FREE"
    if pct <= DISCOUNT_UP_TO_PCT:
        return "DISCOUNT"
    return "PAYMENT_PLAN"


def near_cutoff(pct: float) -> bool:
    return any(abs(pct - c) <= CUTOFF_MARGIN_PCT for c in (FREE_UP_TO_PCT, DISCOUNT_UP_TO_PCT))


def discounted_cents(billed_cents: int) -> int:
    """What the patient pays on a discount (30%), rounded to the cent like core/policy.py."""
    return (billed_cents * DISCOUNT_PATIENT_SHARE_PCT + 50) // 100


def plan_monthly_dollars(balance_cents: int) -> int:
    """12 equal monthly payments rounded up to the dollar, at least $25."""
    if balance_cents <= 0:
        return 0
    return max(25, -(-balance_cents // 1200))


def plan_months(balance_cents: int, monthly_dollars: int) -> int:
    if monthly_dollars <= 0:
        return 0
    return min(12, -(-balance_cents // (monthly_dollars * 100)))


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    for last_day in (day.day, 30, 29, 28):
        try:
            return date(year, month, min(day.day, last_day))
        except ValueError:
            continue
    raise AssertionError("unreachable")


def approval_covers(approved_on: date, visit_on: date) -> bool:
    return approved_on <= visit_on < add_months(approved_on, APPROVAL_COVERS_MONTHS)


def adjustment_cents(outcome: str, billed_cents: int) -> int:
    if outcome == "FREE":
        return billed_cents
    if outcome == "DISCOUNT":
        return billed_cents - discounted_cents(billed_cents)
    return 0


def patient_share_cents(outcome: str, billed_cents: int) -> int:
    if outcome == "FREE":
        return 0
    if outcome == "DISCOUNT":
        return discounted_cents(billed_cents)
    return billed_cents


def approver_for_adjustment(adjust_cents: int) -> str:
    return "DIRECTOR" if adjust_cents > COUNSELOR_LIMIT_CENTS else "COUNSELOR"


def eca_violations(action: str, *, first_bill: date, on: date, notice_sent: date | None,
                   screened: bool) -> list[tuple[str, str]]:
    """Same checks as core/law.py check_collection_action. Empty means allowed."""
    if action not in ECA_ACTIONS:
        return []
    found = []
    if action == "CREDIT_REPORT" and on >= SB_1061_EFFECTIVE:
        found.append(("SB 1061", "medical debt can't be reported to credit bureaus"))
    if on < first_bill + timedelta(days=ECA_WAIT_DAYS):
        found.append(("IRS 501(r)", f"under {ECA_WAIT_DAYS} days since the first bill"))
    if action in ("LAWSUIT", "SELL_DEBT") and on < first_bill + timedelta(days=CA_SUIT_OR_SALE_WAIT_DAYS):
        found.append(("AB 1020", f"lawsuit or debt sale under {CA_SUIT_OR_SALE_WAIT_DAYS} days since the first bill"))
    if notice_sent is None or on < notice_sent + timedelta(days=ECA_NOTICE_DAYS):
        found.append(("IRS 501(r)", f"no written notice at least {ECA_NOTICE_DAYS} days before"))
    if not screened:
        found.append(("IRS 501(r)", "patient not screened for financial assistance first"))
    return found


def money(cents: int | None) -> str:
    """Dollars with two decimals, signed when negative."""
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c // 100}.{c % 100:02d}"


def pct_str(pct: float | None) -> str:
    return "" if pct is None else f"{pct:.1f}"
