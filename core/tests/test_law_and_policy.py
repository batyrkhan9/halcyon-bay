from datetime import date

import pytest

from core import law
from core.model import DISCOUNT, FREE_CARE, PAYMENT_PLAN
from core.policy import (
    NEEDS_INFO, OLD_POLICY, OTHER_PROOF, PAY_STUBS, Applicant, CURRENT_POLICY, add_months,
    approval_covers, policy_on, screen,
)

DAY_2026 = date(2026, 8, 3)


def test_poverty_line_matches_hhs():
    assert law.poverty_line(2025, 1) == 15_650
    assert law.poverty_line(2025, 3) == 26_650
    assert law.poverty_line(2026, 1) == 15_960
    assert law.poverty_line(2026, 4) == 33_000


def test_poverty_line_rejects_bad_input():
    with pytest.raises(ValueError):
        law.poverty_line(2026, 0)
    with pytest.raises(ValueError):
        law.poverty_line(2019, 2)


def test_credit_reporting_is_always_illegal_after_sb_1061():
    found = law.check_collection_action(
        law.CREDIT_REPORT, first_bill=date(2025, 1, 10), on=date(2026, 7, 1),
        notice_sent=date(2026, 1, 1), screened_for_assistance=True,
    )
    assert [v.law for v in found] == ["SB 1061"]


def test_lawsuit_waits_for_180_days_and_notice():
    found = law.check_collection_action(
        law.LAWSUIT, first_bill=date(2026, 1, 1), on=date(2026, 5, 15),
        notice_sent=None, screened_for_assistance=True,
    )
    assert {v.law for v in found} == {"AB 1020", "IRS 501(r)"}
    allowed = law.check_collection_action(
        law.LAWSUIT, first_bill=date(2026, 1, 1), on=date(2026, 7, 15),
        notice_sent=date(2026, 6, 1), screened_for_assistance=True,
    )
    assert allowed == []


def test_agency_placement_is_not_an_extraordinary_action():
    assert law.check_collection_action("PLACE_WITH_AGENCY", first_bill=date(2026, 6, 1), on=date(2026, 6, 2),
                                       notice_sent=None, screened_for_assistance=False) == []


def test_savings_and_late_denials_after_2025_break_ab_2297():
    for reason in (law.DENIED_SAVINGS, law.DENIED_LATE):
        found = law.check_denial(reason=reason, decided_on=date(2025, 3, 4), pct_of_poverty=180)
        assert [v.law for v in found] == ["AB 2297"]


def test_denial_of_someone_over_400_percent_is_not_a_violation():
    assert law.check_denial(reason=law.DENIED_SAVINGS, decided_on=date(2025, 3, 4), pct_of_poverty=450) == []


def test_income_denial_under_400_percent_breaks_ab_1020():
    found = law.check_denial(reason=law.DENIED_INCOME, decided_on=date(2025, 9, 1), pct_of_poverty=320)
    assert [v.law for v in found] == ["AB 1020"]


def test_no_pay_stubs_denial_only_breaks_the_law_with_other_proof():
    kwargs = dict(reason=law.DENIED_NO_PAY_STUBS, decided_on=date(2025, 9, 1), pct_of_poverty=150)
    assert law.check_denial(**kwargs) == []
    assert [v.law for v in law.check_denial(**kwargs, had_other_proof=True)] == ["AB 2297"]


def test_policy_versions_switch_on_july_1_2025():
    assert policy_on(date(2025, 6, 30)) is OLD_POLICY
    assert policy_on(date(2025, 7, 1)) is CURRENT_POLICY


@pytest.mark.parametrize("income, outcome, pays", [
    (33_000, FREE_CARE, 0),                 # 100%
    (66_000, FREE_CARE, 0),                 # 200% exactly
    (99_000, DISCOUNT, 300_00),             # 300%: pays 30% of $1,000
    (132_000, DISCOUNT, 300_00),            # 400% exactly
    (165_000, PAYMENT_PLAN, 1_000_00),      # 500%
])
def test_screen_tiers_for_a_family_of_four(income, outcome, pays):
    result = screen(Applicant(4, income, PAY_STUBS), 1_000_00, DAY_2026)
    assert (result.outcome, result.patient_pays_cents) == (outcome, pays)
    assert result.adjustment_cents == 1_000_00 - pays


def test_screen_asks_a_person_near_a_cutoff():
    assert screen(Applicant(4, 66_500, PAY_STUBS), 1_000_00, DAY_2026).question
    assert screen(Applicant(4, 33_000, PAY_STUBS), 1_000_00, DAY_2026).question is None


def test_screen_accepts_other_proof_and_asks_when_there_is_none():
    assert screen(Applicant(1, 20_000, OTHER_PROOF), 500_00, DAY_2026).outcome == FREE_CARE
    missing = screen(Applicant(1, 20_000, None), 500_00, DAY_2026)
    assert missing.outcome == NEEDS_INFO and missing.question


def test_medi_cal_and_homeless_get_free_care_without_documents():
    assert screen(Applicant(None, None, None, frozenset({"MEDI_CAL"})), 900_00, DAY_2026).outcome == FREE_CARE
    assert screen(Applicant(None, None, None, homeless=True), 900_00, DAY_2026).outcome == FREE_CARE


def test_calfresh_only_counts_once_the_rule_is_learned():
    calfresh = Applicant(None, None, None, frozenset({"CALFRESH"}))
    assert screen(calfresh, 900_00, DAY_2026).outcome == NEEDS_INFO
    assert screen(calfresh, 900_00, DAY_2026, learned_programs=frozenset({"CALFRESH"})).outcome == FREE_CARE


def test_discount_rounds_to_the_cent():
    assert screen(Applicant(4, 99_000, PAY_STUBS), 333_33, DAY_2026).patient_pays_cents == 100_00


def test_a_march_approval_covers_a_june_visit():
    assert approval_covers(date(2026, 3, 12), date(2026, 6, 20))
    assert not approval_covers(date(2026, 3, 12), date(2027, 3, 12))
    assert not approval_covers(date(2026, 3, 12), date(2026, 3, 1))


def test_add_months_clamps_to_the_end_of_the_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
