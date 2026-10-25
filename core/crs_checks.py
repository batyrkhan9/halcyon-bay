"""CRS checks for the core, through Noriaki's client in data/crs/ (see data/FORMAT.md).

Used only to help a patient or to stop a collection, never to deny help:
- bankruptcy: an open case is an automatic stay, so no collection action at all;
- deceased: collections stop and the director handles the estate;
- identity: a FAIL or STEP_UP sends the case to a counselor to verify, before anything posts;
- contact: the address CRS has on file, when mail to ours came back.

Each patient is checked once. The answer is saved as a record (kind "crs", by MRN) and in the
audit log, so a replay never asks twice and "why?" shows what CRS said. The client only ever
sends a sandbox persona's registered request; anyone else comes back sent: false.
"""

from __future__ import annotations

import sys

from .config import ROOT
from .permissions import Actor
from .store import Store

CRS_CLIENT = ROOT / "data" / "crs"


def live_check(person: dict) -> dict:
    if str(CRS_CLIENT) not in sys.path:
        sys.path.insert(0, str(CRS_CLIENT))
    import crs  # data/crs/crs.py, Noriaki's client

    return crs.check_person(person)


def check_patient(store: Store, gateway, actor: Actor, mrn: str, account_id: str, check=live_check) -> dict:
    saved = store.record("crs", mrn)
    if saved is not None:
        return saved
    patient = store.record("patient", mrn) or {}
    if not patient.get("ssn"):
        result = {"sent": False, "reason": "NO_SSN"}
    else:
        result = check({key: patient.get(key) for key in
                        ("ssn", "first_name", "last_name", "dob", "phone", "address_line1", "city", "zip")})
    store.put_record("crs", mrn, store.today().isoformat(), result)
    if result.get("sent"):
        gateway.note(actor, "crs_check", account_id=account_id, target=mrn, reason=summary(result), detail=result)
    return result


def bankruptcy_open(result: dict) -> dict | None:
    bankruptcy = result.get("bankruptcy") or {}
    if not bankruptcy.get("open"):
        return None
    return next((r for r in bankruptcy.get("records", []) if r.get("status") == "OPEN"), {"chapter": "?"})


def deceased(result: dict) -> bool:
    return result.get("deceased") is True


def identity_problem(result: dict) -> str | None:
    identity = result.get("identity") or {}
    if identity.get("result") not in ("FAIL", "STEP_UP"):
        return None
    codes = ", ".join(f"{p['code']} {p['text']}" for p in identity.get("problems", []))
    return f"{identity['result']}: {codes}" if codes else identity["result"]


def current_address(result: dict) -> str | None:
    contact = result.get("contact") or {}
    return contact.get("address") if contact.get("found") else None


def summary(result: dict) -> str:
    parts = [f"identity {(result.get('identity') or {}).get('result', 'NOT_CHECKED')}"]
    if case := bankruptcy_open(result):
        parts.append(f"open chapter {case.get('chapter')} bankruptcy")
    if deceased(result):
        parts.append("deceased")
    if address := current_address(result):
        parts.append(f"current address {address}")
    return f"CRS ({result.get('source') or 'no source'}): " + ", ".join(parts) + "."
