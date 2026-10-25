"""Federal 501(r) and California rules, in plain code.

A prompt never decides any of this. The agent may turn a messy note into a
reason code, but whether that reason is legal is decided here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# HHS poverty guidelines for the 48 contiguous states: (first person, each extra person).
# The year of the decision picks the table.
POVERTY_GUIDELINES = {
    2025: (15_650, 5_500),
    2026: (15_960, 5_680),
}

AB_1020_LIMIT_PCT = 400          # up to 400% of poverty qualifies for free or discounted care
AB_1020_EFFECTIVE = date(2024, 1, 1)
AB_2297_EFFECTIVE = date(2025, 1, 1)
SB_1061_EFFECTIVE = date(2025, 1, 1)

ECA_WAIT_DAYS = 120              # 501(r): no extraordinary collection action before this
ECA_NOTICE_DAYS = 30             # 501(r): written notice at least this long before one
APPLICATION_WINDOW_DAYS = 240    # 501(r): applications accepted at least this long
CA_SUIT_OR_SALE_WAIT_DAYS = 180  # AB 1020: no lawsuit or debt sale before this

# Extraordinary collection actions. Placing an account with an agency is not one.
SELL_DEBT = "SELL_DEBT"
CREDIT_REPORT = "CREDIT_REPORT"
LAWSUIT = "LAWSUIT"
LIEN = "LIEN"
EXTRAORDINARY_ACTIONS = frozenset({SELL_DEBT, CREDIT_REPORT, LAWSUIT, LIEN})
ACTION_NAMES = {
    SELL_DEBT: "sell the debt",
    CREDIT_REPORT: "report the debt to credit bureaus",
    LAWSUIT: "sue the patient",
    LIEN: "place a lien",
}

# Reasons a past denial can give.
DENIED_INCOME = "INCOME_OVER_LIMIT"
DENIED_SAVINGS = "SAVINGS_OVER_LIMIT"
DENIED_LATE = "LATE_APPLICATION"
DENIED_NO_PAY_STUBS = "NO_PAY_STUBS"
DENIED_INCOMPLETE = "INCOMPLETE_APPLICATION"


@dataclass(frozen=True)
class Violation:
    law: str
    text: str


def poverty_line(year: int, household: int) -> int:
    if household < 1:
        raise ValueError(f"household must be at least 1, got {household}")
    if year not in POVERTY_GUIDELINES:
        raise ValueError(f"no poverty guideline loaded for {year}")
    first, extra = POVERTY_GUIDELINES[year]
    return first + extra * (household - 1)


def percent_of_poverty(annual_income: float, household: int, year: int) -> float:
    return 100 * annual_income / poverty_line(year, household)


def check_collection_action(
    action: str,
    *,
    first_bill: date,
    on: date,
    notice_sent: date | None,
    screened_for_assistance: bool,
    application_pending: bool = False,
) -> list[Violation]:
    """Every law an agency action on `on` would break. Empty means it is allowed."""
    if action not in EXTRAORDINARY_ACTIONS:
        return []
    found = []
    if application_pending:
        found.append(Violation("IRS 501(r)", "A financial assistance application is pending."))
    if action == CREDIT_REPORT and on >= SB_1061_EFFECTIVE:
        found.append(Violation("SB 1061", "Medical debt can't be reported to credit bureaus."))
    earliest = first_bill + timedelta(days=ECA_WAIT_DAYS)
    if on < earliest:
        found.append(Violation(
            "IRS 501(r)",
            f"No extraordinary collection action until {ECA_WAIT_DAYS} days after the first bill ({earliest}).",
        ))
    if action in (LAWSUIT, SELL_DEBT):
        earliest = first_bill + timedelta(days=CA_SUIT_OR_SALE_WAIT_DAYS)
        if on < earliest:
            found.append(Violation(
                "AB 1020",
                f"No lawsuit or debt sale until {CA_SUIT_OR_SALE_WAIT_DAYS} days after the first bill ({earliest}).",
            ))
    if notice_sent is None or on < notice_sent + timedelta(days=ECA_NOTICE_DAYS):
        found.append(Violation("IRS 501(r)", f"Needs written notice at least {ECA_NOTICE_DAYS} days before."))
    if not screened_for_assistance:
        found.append(Violation("IRS 501(r)", "The patient must be checked for financial assistance first."))
    return found


def check_denial(
    *,
    reason: str,
    decided_on: date,
    pct_of_poverty: float | None,
    applied_on: date | None = None,
    first_bill: date | None = None,
    had_other_proof: bool = False,
) -> list[Violation]:
    """Every law a past financial assistance denial broke.

    Only denials of patients who qualify on income count: if income is over
    the limit, the outcome was right even when the stated reason was not.
    """
    if pct_of_poverty is None or pct_of_poverty > AB_1020_LIMIT_PCT:
        return []
    found = []
    after_ab_2297 = decided_on >= AB_2297_EFFECTIVE
    if reason == DENIED_INCOME and decided_on >= AB_1020_EFFECTIVE:
        found.append(Violation(
            "AB 1020",
            f"Income is {pct_of_poverty:.0f}% of the poverty level; up to {AB_1020_LIMIT_PCT}% qualifies.",
        ))
    if reason == DENIED_SAVINGS and after_ab_2297:
        found.append(Violation("AB 2297", "Savings and other monetary assets can't be counted."))
    if reason == DENIED_LATE:
        if after_ab_2297:
            found.append(Violation("AB 2297", "There can be no application deadline."))
        elif applied_on and first_bill and applied_on <= first_bill + timedelta(days=APPLICATION_WINDOW_DAYS):
            found.append(Violation(
                "IRS 501(r)",
                f"Applications must be accepted for {APPLICATION_WINDOW_DAYS} days after the first bill.",
            ))
    if reason == DENIED_NO_PAY_STUBS and had_other_proof and after_ab_2297:
        found.append(Violation("AB 2297", "Other proof of income must be accepted."))
    return found
