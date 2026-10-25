"""Writes data/world/ and data/answer_key/ from a built world."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pools
import rules as R
from world import (ANSWER_COLUMNS, COLUMNS, HISTORY_END, HISTORY_START, LIVE_START, WORLD_END, Rec, World, clamp,
                   csv_text, mdy, versions_rows)

POLICY_DIR = Path(__file__).resolve().parent / "policy_text"


def client_account(acc_id: str, style: str) -> str:
    if style == "noprefix":
        return acc_id[2:]
    if style == "dashes":
        return f"HB-{acc_id[2:6]}-{acc_id[6:]}"
    return acc_id


def sort_rows(rows):
    return [r for _, _, r in sorted(rows, key=lambda t: (t[0], t[2][1]))]


def event_rows(recs, day_of, make):
    out = []
    for r in recs:
        day = clamp(day_of(r))
        if day > WORLD_END:
            continue
        out.append((day, r.seq, make(day, r)))
    return out


def world_tables(w: World) -> dict[str, list[list]]:
    m = R.money
    t: dict[str, list] = {}
    rows = []
    for p in w.patients:
        rows += versions_rows(p, lambda d, s, p=p: [d, p.id, s["last_name"], s["first_name"], s["middle_initial"],
                                                    s["dob"], s["ssn"], s["address_line1"], s["city"], s["state"],
                                                    s["zip"], s["phone"], s["registered_on"]])
    t["billing/patients.csv"] = sort_rows(rows)
    rows = []
    for a in w.accounts:
        rows += versions_rows(a, lambda d, s, a=a: [d, a.id, s["patient"], s["service_date"], s["discharge_date"],
                                                    s["service_type"], s["payer"], m(s["total_charges"]),
                                                    m(s["insurance_paid"]), m(s["insurance_adjustment"]),
                                                    m(s["patient_responsibility"]), s["first_statement_date"],
                                                    s["status"]])
    t["billing/accounts.csv"] = sort_rows(rows)
    t["billing/transactions.csv"] = sort_rows(event_rows(
        w.txns, lambda r: r.f["recorded"],
        lambda d, r: [d, r.id, r.f["account"], r.f["posted_on"], r.f["txn_type"], m(r.f["amount"]), r.f["note"]]))
    t["billing/statements.csv"] = sort_rows(event_rows(
        w.statements, lambda r: r.f["sent_on"],
        lambda d, r: [d, r.id, r.f["account"], r.f["sent_on"], r.f["kind"], m(r.f["amount_due"]), r.f["mailed_to"],
                      r.f["returned_mail"]]))
    rows = []
    for p in w.plans:
        rows += versions_rows(p, lambda d, s, p=p: [d, p.id, s["patient"], s["accounts"], s["start_date"],
                                                    m(s["monthly_amount"]), s["months"], s["status"],
                                                    s["missed_payments"], s["last_payment_on"], s["stopped_on"],
                                                    s["stopped_by"], s["stop_reason"]])
    t["billing/payment_plans.csv"] = sort_rows(rows)
    rows = []
    for a in w.apps:
        rows += versions_rows(a, lambda d, s, a=a: [d, a.id, s["applicant"], s["mrn_given"], s["accounts_given"],
                                                    s["first_name"], s["last_name"], s["dob"], s["ssn"], s["phone"],
                                                    s["address_line1"], s["city"], s["state"], s["zip"],
                                                    s["household_size"], s["income_stated"], s["income_verified"],
                                                    s["income_proof"], s["monetary_assets"], s["medi_cal"],
                                                    s["homeless"], s["received_on"], s["form_version"], s["status"],
                                                    s["decision"], s["decision_date"], s["decided_by"], s["reason"]])
    t["fa/applications.csv"] = sort_rows(rows)
    t["fa/notes.csv"] = sort_rows(event_rows(
        w.notes, lambda r: r.f["written_on"],
        lambda d, r: [d, r.id, r.f["app"], r.f["account"], r.f["author"], r.f["written_on"], r.f["text"]]))
    rows = []
    for p in w.placements:
        rows += versions_rows(p, lambda d, s, p=p: [d, p.id, client_account(s["account"].id, s["client_style"]),
                                                    s["debtor_name"], s["debtor_dob"], s["debtor_address"],
                                                    s["debtor_phone"], mdy(s["placed_date"]), m(s["placed_balance"]),
                                                    m(s["current_balance"]), s["status"], s["last_activity"]])
    t["agency/placements.csv"] = sort_rows(rows)
    t["agency/requests.csv"] = sort_rows(event_rows(
        w.requests, lambda r: r.first_day,
        lambda d, r: [d, r.id, r.f["placement"],
                      client_account(r.f["placement"].f["account"].id,
                                     r.f.get("client_style") or r.f["placement"].f["client_style"]),
                      r.f["requested_action"], mdy(r.f["requested_date"]), r.f["agency_note"]]))
    t["documents/index.csv"] = sort_rows(event_rows(
        w.docs, lambda r: r.f["received_on"],
        lambda d, r: [d, r.id, r.f["app"], r.f["name_on_document"], r.f["doc_type"], r.f["received_on"],
                      f"files/{r.id}.txt"]))
    rows = []
    for s in pools.STAFF:
        sid, first, last, role, limit, dob, addr, city, zip_code = s
        phone = {"S-004": "555-482-7710"}.get(sid, f"555-3{int(sid[2:]):02d}-{4100 + int(sid[2:]) * 37:04d}")
        email = f"{first[0].lower()}{last.lower().replace('-', '')}@hbch.example"
        rows.append((HISTORY_START, 0, [HISTORY_START, sid, first, last, role, limit, email, dob, addr, city, "CA",
                                        zip_code, phone, "Y"]))
    t["staff/staff.csv"] = sort_rows(rows)
    t["policy/index.csv"] = [
        [date(2025, 1, 1), "2020-01-01", "2020-01-01", "2025-06-30", "fap_2020-01-01.md"],
        [date(2025, 7, 1), "2025-07-01", "2025-07-01", "", "fap_2025-07-01.md"],
    ]
    return t


def answer_tables(w: World) -> dict[str, list[list]]:
    m = R.money
    t = {}
    rows = []
    for a in w.answers:
        rows.append([a["account"].id, a["person"].pid, a["outcome"], R.pct_str(a["fpl_pct"]), m(a["adjustment"]),
                     m(a["patient_owes"]), m(a["refund"]),
                     "" if a["monthly_payment"] is None else f"{a['monthly_payment']}.00", a["handling"],
                     a["ask_role"], a["approver_role"], ";".join(_act(x) for x in a["required"]),
                     ";".join(_act(x) for x in a["forbidden"]), ";".join(a["planted"]), a["reason"]])
    t["live_accounts.csv"] = sorted(rows, key=lambda r: r[0])
    rows = []
    for f in w.findings:
        rows.append([f["finding"], f["app"].id, f["person"].pid, ";".join(x.id for x in f["accounts"]),
                     f["decision_date"], f["decided_by"], f["stated_reason"], R.pct_str(f["fpl_pct"]),
                     f["correct_outcome"], m(f["adjustment"]), m(f["refund"]), f["law"], f["reason"]])
    t["history_findings.csv"] = sorted(rows, key=lambda r: (r[0], r[1]))
    rows = []
    for c in w.backtest:
        rows.append([c["app"].id, c["person"].pid, ";".join(x.id for x in c["accounts"]), c["original_status"],
                     c["original_decision"], c["with_rule"], c["changes"], m(c["dollars"]), c["reason"]])
    t["calfresh_backtest.csv"] = sorted(rows, key=lambda r: r[0])
    t["patterns.csv"] = [[p["pattern"], p["evidence_count"], p["legal"], p["note"]] for p in w.patterns]
    return t


def _act(x) -> str:
    """Actions may hold records (request, mrn); resolve them to ids."""
    if isinstance(x, tuple):
        kind, *refs = x
        if kind == "MERGE":
            return "MERGE:" + "+".join(sorted(r.id for r in refs))
        return f"{kind}:{refs[0].id}"
    return x


def planted_json(w: World) -> list[dict]:
    out = []
    for i, c in enumerate(w.planted, start=1):
        rec = {k: sorted({_rid(x) for x in c["records"].get(k, [])}) for k in
               ("mrn", "account_no", "application_id", "doc_id", "request_id", "staff_id")}
        out.append({"id": c["id"], "category": c["category"], "period": c["period"], "summary": c["summary"],
                    "records": rec, "fix": c["fix"], "dollars": round(c["dollars"] / 100, 2)})
    return out


def _rid(x) -> str:
    return x.id if isinstance(x, Rec) else str(x)


def write_all(w: World, root: Path) -> dict[str, int]:
    """Write every file. `root` is the data/ folder (or a temp copy of it)."""
    world_dir = root / "world"
    key_dir = root / "answer_key"
    for d in (world_dir, key_dir):
        if d.exists():
            shutil.rmtree(d)
    counts: dict[str, int] = {}
    tables = world_tables(w)
    for rel, rows in tables.items():
        path = world_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(csv_text(COLUMNS[rel], rows), encoding="utf-8")
        counts[rel] = len(rows)
    files_dir = world_dir / "documents" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    n_files = 0
    for doc in w.docs:
        if clamp(doc.f["received_on"]) > WORLD_END:
            continue
        (files_dir / f"{doc.id}.txt").write_text(doc.f["text"], encoding="utf-8")
        n_files += 1
    counts["documents/files"] = n_files
    for name in ("fap_2020-01-01.md", "fap_2025-07-01.md"):
        shutil.copyfile(POLICY_DIR / name, world_dir / "policy" / name)
    world_meta = {
        "hospital": "Halcyon Bay Community Hospital (fictional)",
        "city": "Halcyon Bay, CA (fictional)",
        "seed": 13,
        "history": {"start": HISTORY_START.isoformat(), "end": HISTORY_END.isoformat()},
        "live": {"start": LIVE_START.isoformat(), "end": WORLD_END.isoformat()},
        "onboarding_loads_recorded_on_through": HISTORY_END.isoformat(),
        "regenerate": "python3 data/generate/generate.py",
        "rows": dict(sorted(counts.items())),
        "synthetic": "Every person, account and document here is made up.",
    }
    (world_dir / "world.json").write_text(json.dumps(world_meta, indent=2) + "\n", encoding="utf-8")
    key_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in answer_tables(w).items():
        (key_dir / name).write_text(csv_text(ANSWER_COLUMNS[name], rows), encoding="utf-8")
        counts[f"answer_key/{name}"] = len(rows)
    planted = planted_json(w)
    (key_dir / "planted_cases.json").write_text(json.dumps(planted, indent=2) + "\n", encoding="utf-8")
    counts["answer_key/planted_cases.json"] = len(planted)
    return counts
