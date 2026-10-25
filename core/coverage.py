"""What a patient's applications say about one account, from the records sync loaded.

- covering_approval: an approval from the 12 months before the visit covers it (policy).
- pending_application: an application for this account still waits for a decision.
- screened: the patient has had a decision, so the hospital made its 501(r) effort.

A patient's applications are the ones that give their MRN or list one of their accounts.
"""

from __future__ import annotations

import re
from datetime import date

from .policy import approval_covers
from .store import Store

UNDECIDED = {"RECEIVED", "NEEDS_INFO"}


def account_number(written: str) -> str | None:
    """The agency and applicants write account numbers many ways: 26107411, HB-2610-7411, hb26107411."""
    digits = re.sub(r"\D", "", written or "")
    return f"HB{digits}" if len(digits) == 8 else None


def patient_applications(store: Store, mrn: str) -> list[dict]:
    accounts = {r["account_no"] for r in store.records("account", "json_extract(data, '$.mrn') = ?", mrn)}
    return [app for app in store.records("application")
            if app["mrn_given"].strip() == mrn
            or any(account_number(a) in accounts for a in app["accounts_given"].split(";"))]


def _approvals(store: Store, account_no: str) -> tuple[dict | None, list[dict]]:
    account = store.record("account", account_no)
    if not account:
        return None, []
    return account, [app for app in patient_applications(store, account["mrn"])
                     if app["status"] == "APPROVED" and app["decision"] in ("FREE", "DISCOUNT") and app["decision_date"]]


def _lists(app: dict, account_no: str) -> bool:
    return account_no in {account_number(a) for a in app["accounts_given"].split(";")}


def covering_approval(store: Store, account_no: str) -> dict | None:
    """An approval of another account, from the 12 months before this visit."""
    account, approvals = _approvals(store, account_no)
    if not account:
        return None
    visit = date.fromisoformat(account["service_date"])
    covering = [app for app in approvals if not _lists(app, account_no)
                and approval_covers(date.fromisoformat(app["decision_date"]), visit)]
    return max(covering, key=lambda app: app["decision_date"], default=None)


def approved_directly(store: Store, account_no: str) -> dict | None:
    """An approval that names this account: it is already decided."""
    _, approvals = _approvals(store, account_no)
    return max((app for app in approvals if _lists(app, account_no)), key=lambda app: app["decision_date"], default=None)


def pending_application(store: Store, account_no: str) -> dict | None:
    pending = [app for app in (store.record("application", a) for a in store.applications_for(account_no))
               if app and app["status"] in UNDECIDED]
    return max(pending, key=lambda app: app["received_on"], default=None)


def screened(store: Store, account_no: str) -> bool:
    account = store.record("account", account_no)
    decided = account and any(app["decision"] for app in patient_applications(store, account["mrn"]))
    posted = store.one("SELECT 1 AS yes FROM proposals WHERE account_id = ? AND status = 'POSTED' AND kind IN "
                       "('FREE_CARE', 'DISCOUNT', 'PAYMENT_PLAN')", account_no)
    return bool(decided or posted)
