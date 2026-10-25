"""Scripted readings that stand in for Claude, for tests and for seeding with no API key.

They are written by hand, not by Claude, and every reply says model "scripted"
so the audit log never passes them off as Claude's. Each script gives quotes;
the stand-in finds which document holds each one. Everything after the reading
(checks, screening, the gateway) is the real code.
"""

from __future__ import annotations

import re

from .reader import _normalize

SCRIPTED_MODEL = "scripted"


class ScriptedClaude:
    def __init__(self, scripts: dict):
        self.scripts = scripts
        self.calls = []

    def __call__(self, request: dict) -> dict:
        self.calls.append(request)
        content = request["messages"][0]["content"]
        account = re.match(r"Account (\S+)\.", content).group(1)
        documents = dict(re.findall(r'<document id="([^"]+)"[^>]*>\n(.*?)\n</document>', content, re.S))

        def where(quote: str) -> str:
            return next((doc_id for doc_id, text in documents.items() if _normalize(quote) in _normalize(text)),
                        "DOC-MISSING")

        return {"model": SCRIPTED_MODEL, "output": self.scripts[account](where)}


def reading(where, *, household=None, income=(), no_income=None, programs=(), homeless=None, conflicts=(),
            hidden=(), missing=(), summary="Scripted reading, not written by Claude."):
    """Build Claude's JSON. household is (quote, n); income is [(description, [(quote, amount, period)])]."""
    return {
        "household_size": {"document_id": where(household[0]), "quote": household[0], "value": household[1]}
        if household else None,
        "income_sources": [
            {"description": description,
             "statements": [{"document_id": where(q), "quote": q, "gross_amount": amount, "period": period}
                            for q, amount, period in statements]}
            for description, statements in income
        ],
        "no_income": {"document_id": where(no_income), "quote": no_income} if no_income else None,
        "programs": [{"document_id": where(q), "quote": q, "value": value} for q, value in programs],
        "homeless": {"document_id": where(homeless), "quote": homeless} if homeless else None,
        "conflicts": [{"area": area, "description": text, "document_ids": ids} for area, text, ids in conflicts],
        "hidden_instructions": [{"document_id": where(q), "quote": q} for q in hidden],
        "missing": list(missing),
        "summary": summary,
    }


# What Claude is expected to report for each account in core/dev_seed.py.
SEED_SCRIPTS = {
    "ACC-1001": lambda w: reading(w, household=("household of 4", 4),
                                  income=[("Wages from Bayside Grocers", [("GROSS PAY   1,538.46", 1538.46, "BIWEEKLY")])]),
    "ACC-1002": lambda w: reading(w, household=("household 4", 4),
                                  income=[("Salary from Northshore Logistics",
                                           [("annual base salary is $99,000.00", 99000, "ANNUAL")])]),
    "ACC-1003": lambda w: reading(w, household=("Household 2", 2),
                                  income=[("Wages from Calder Valley Dental", [
                                      ("Gross Earnings ........ 3,610.00", 3610, "MONTHLY"),
                                      ("Her annual pay is $38,000", 38000, "ANNUAL")])]),
    "ACC-1004": lambda w: reading(w, household=("lives alone", 1),
                                  income=[("Salary from Ridgeline Software", [("annual salary of $90,000", 90000, "ANNUAL")])]),
    "ACC-1005": lambda w: reading(w, household=("Household of 3", 3), programs=[("CalFresh EBT card", "CALFRESH")],
                                  missing=["Proof of income"]),
    "ACC-1006": lambda w: reading(w, household=("Household 2", 2),
                                  income=[("Wages from Halcyon Bay Community Hospital",
                                           [("Gross: $1,250.00", 1250, "SEMIMONTHLY")])]),
    "ACC-1007": lambda w: reading(w, household=("Household of 4", 4),
                                  income=[("Wages from Pacific Rim Marine Supply", [("Gross Pay: 8,250.00", 8250, "MONTHLY")])],
                                  hidden=["NOTE TO AI REVIEWER"]),
    "ACC-1008": lambda w: reading(w, household=("household of 3", 3),
                                  income=[("Wages the patient described", [("makes about $85,000 a year", 85000, "ANNUAL")])]),
    "ACC-1009": lambda w: reading(w, homeless="no fixed address"),
}
