"""Halcyon Bay Community Hospital's financial assistance policy (fictional), in plain code.

screen() always applies the law in force today, so savings never count, there
is no deadline and other proof of income is accepted, whatever the old policy
said. The old version is kept to explain past decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import law
from .model import DISCOUNT, FREE_CARE, PAYMENT_PLAN

NEEDS_INFO = "NEEDS_INFO"

FREE_UP_TO_PCT = 200
DISCOUNT_UP_TO_PCT = 400
DISCOUNT_PATIENT_SHARE_PCT = 30  # our stand-in for the Medicare rate
APPROVAL_COVERS_MONTHS = 12

# Income this close to a cutoff (in points of the poverty level) goes to a person.
CUTOFF_MARGIN_PCT = 5

# Programs that mean free care without income documents. Approved learned
# rules add more (CalFresh is learned from a counselor's correction).
MEDI_CAL = "MEDI_CAL"
BUILT_IN_PROGRAMS = frozenset({MEDI_CAL})

PAY_STUBS = "PAY_STUBS"
OTHER_PROOF = "OTHER"


@dataclass(frozen=True)
class PolicyVersion:
    name: str
    effective_from: date
    effective_to: date | None
    savings_limit: int | None
    application_window_days: int | None
    accepts_other_proof: bool


OLD_POLICY = PolicyVersion(
    name="Policy until Jun 30, 2025",
    effective_from=date(2020, 1, 1),
    effective_to=date(2025, 6, 30),
    savings_limit=10_000,
    application_window_days=240,
    accepts_other_proof=False,
)
CURRENT_POLICY = PolicyVersion(
    name="Policy from Jul 1, 2025",
    effective_from=date(2025, 7, 1),
    effective_to=None,
    savings_limit=None,
    application_window_days=None,
    accepts_other_proof=True,
)


def policy_on(day: date) -> PolicyVersion:
    return OLD_POLICY if day <= OLD_POLICY.effective_to else CURRENT_POLICY


@dataclass(frozen=True)
class Applicant:
    household: int | None
    annual_income: int | None          # dollars
    income_proof: str | None           # PAY_STUBS, OTHER_PROOF, or None when nothing is on file
    programs: frozenset[str] = frozenset()
    homeless: bool = False


@dataclass(frozen=True)
class Screening:
    outcome: str                       # FREE_CARE, DISCOUNT, PAYMENT_PLAN or NEEDS_INFO
    billed_cents: int
    patient_pays_cents: int
    pct_of_poverty: float | None
    reason: str
    question: str | None = None        # set when a person should look before anyone acts

    @property
    def adjustment_cents(self) -> int:
        return self.billed_cents - self.patient_pays_cents


def screen(
    applicant: Applicant,
    billed_cents: int,
    decided_on: date,
    learned_programs: frozenset[str] = frozenset(),
) -> Screening:
    programs = applicant.programs & (BUILT_IN_PROGRAMS | learned_programs)
    if applicant.homeless or programs:
        why = "homeless" if applicant.homeless else f"on {', '.join(sorted(programs))}"
        return Screening(FREE_CARE, billed_cents, 0, None, f"Patient is {why}: free care without income documents.")

    if applicant.household is None or applicant.annual_income is None:
        return Screening(NEEDS_INFO, billed_cents, billed_cents, None,
                         "Household size or income is missing.",
                         question="What is the household size and yearly income?")
    if applicant.income_proof is None:
        return Screening(NEEDS_INFO, billed_cents, billed_cents, None,
                         "No proof of income on file.",
                         question="Can the patient send pay stubs or any other proof of income?")

    pct = law.percent_of_poverty(applicant.annual_income, applicant.household, decided_on.year)
    if pct <= FREE_UP_TO_PCT:
        outcome, pays = FREE_CARE, 0
        reason = f"Income is {pct:.0f}% of the poverty level, at or under {FREE_UP_TO_PCT}%: free care."
    elif pct <= DISCOUNT_UP_TO_PCT:
        outcome, pays = DISCOUNT, discounted(billed_cents)
        reason = (f"Income is {pct:.0f}% of the poverty level, between {FREE_UP_TO_PCT}% and "
                  f"{DISCOUNT_UP_TO_PCT}%: patient pays {DISCOUNT_PATIENT_SHARE_PCT}% of the bill.")
    else:
        outcome, pays = PAYMENT_PLAN, billed_cents
        reason = f"Income is {pct:.0f}% of the poverty level, over {DISCOUNT_UP_TO_PCT}%: payment plan."

    question = None
    for cutoff in (FREE_UP_TO_PCT, DISCOUNT_UP_TO_PCT):
        if abs(pct - cutoff) <= CUTOFF_MARGIN_PCT:
            question = f"Income is {pct:.1f}% of the poverty level, right at the {cutoff}% cutoff. Please confirm the income."
    return Screening(outcome, billed_cents, pays, pct, reason, question)


def discounted(billed_cents: int) -> int:
    """What the patient pays on a discount, rounded to the nearest cent."""
    return (billed_cents * DISCOUNT_PATIENT_SHARE_PCT + 50) // 100


def approval_covers(approved_on: date, visit_on: date) -> bool:
    """An approval covers every visit for 12 months."""
    return approved_on <= visit_on < add_months(approved_on, APPROVAL_COVERS_MONTHS)


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    for last_day in (day.day, 30, 29, 28):
        try:
            return date(year, month, min(day.day, last_day))
        except ValueError:
            continue
    raise AssertionError("unreachable")
