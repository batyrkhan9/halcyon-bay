#!/usr/bin/env python3
"""Run all 20 CRS sandbox personas live through crs.check_person and compare with what each should return.

    python3 data/crs/check.py            # live run, prints a table, exit 1 on any mismatch
    python3 data/crs/check.py --record   # also writes recorded/P01.json ... P20.json (the offline fallback)

It also reads the account's request log to prove every call matched a sandbox persona
(billable: false, so nothing reached a real bureau) and spot-checks one call in retention.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crs  # noqa: E402

IDENTITY = {"P12": "FAIL", "P13": "FAIL", "P14": "FAIL", "P16": "STEP_UP"}          # the rest PASS
DECEASED = {"P14"}
BANKRUPTCIES = {"P06": [("7", "DISCHARGED")], "P07": [("13", "OPEN")]}
LIENS_JUDGMENTS = {"P08": [("JUDGMENT", 12300.0), ("TAX_LIEN", 7450.0)], "P11": [("JUDGMENT", 4850.0)]}
CONTACT = {"P04": None, "P13": None, "P12": "RAJESH MENON"}                          # the rest their own name


def person_input(persona: dict) -> dict:
    i = persona["identity"]
    return {"ssn": i["ssn"], "first": i["first_name"], "last": i["last_name"], "dob": i["dob"],
            "phone": i["phone"], "address_line1": i["street1"], "city": i["city"], "state": i["state"],
            "zip": i["zip"]}


def mismatches(persona: dict, r: dict) -> list[str]:
    pid = persona["id"]
    bad = []

    def want(label, got, expected):
        if got != expected:
            bad.append(f"{label}: got {got!r}, expected {expected!r}")

    want("sent", r.get("sent"), True)
    want("source", r.get("source"), "live")
    want("errors", r.get("errors"), {})
    want("input_matches", r.get("input_matches"), {"name": True, "dob": True, "address": True, "phone": True})
    want("identity", (r.get("identity") or {}).get("result"), IDENTITY.get(pid, "PASS"))
    want("deceased", r.get("deceased"), pid in DECEASED)
    bk = r.get("bankruptcy") or {}
    want("bankruptcy records", [(b["chapter"], b["status"]) for b in bk.get("records", [])], BANKRUPTCIES.get(pid, []))
    want("bankruptcy open", bk.get("open"), pid == "P07")
    want("liens/judgments", [(x["type"], x["amount"]) for x in r.get("liens_judgments") or []],
         LIENS_JUDGMENTS.get(pid, []))
    contact = r.get("contact") or {}
    want("contact", contact.get("name"), CONTACT.get(pid, persona["name"]))
    want("contact found", contact.get("found"), CONTACT.get(pid, persona["name"]) is not None)
    return bad


def money(x) -> str:
    return "?" if x is None else f"${x:,.0f}"


def row(persona: dict, r: dict, ok: bool) -> str:
    ident = r.get("identity") or {}
    codes = ",".join(p["code"] for p in ident.get("problems", []))
    identity = ident.get("result", "") + (f" {codes}" if codes else "")
    deceased = {True: "YES", False: "no", None: "?"}[r.get("deceased")]
    bk = r.get("bankruptcy")
    if bk is None:
        bankruptcy = "?"
    elif not bk["records"]:
        bankruptcy = "none"
    else:
        bankruptcy = ("OPEN " if bk["open"] else "") + ", ".join(f"ch{b['chapter']} {b['status']}" for b in bk["records"])
        bankruptcy += " (TU agrees)" if bk.get("sources_agree") else ""
    lj = r.get("liens_judgments")
    liens = "?" if lj is None else ("none" if not lj else "; ".join(f"{x['type']} {money(x['amount'])}" for x in lj))
    contact = r.get("contact")
    contact_name = "?" if contact is None else (contact["name"] or "no record")
    return (f"{persona['id']:<4} {persona['name']:<19} {identity:<20} {deceased:<4} {bankruptcy:<30} "
            f"{liens:<34} {contact_name:<19} {r.get('source') or '-':<8} {'ok' if ok else 'MISMATCH'}")


def show_account() -> None:
    status, user = crs.account_get("/users")
    if status != 200 or not isinstance(user, dict):
        print(f"GET /users -> HTTP {status}")
        return
    roles = user.get("roles")
    bits = [i for i in range(64) if isinstance(roles, int) and roles >> i & 1]
    print(f"Account enabled={user.get('enabled')} roles bitmask={roles} (bits {' '.join(map(str, bits))}). "
          "CRS does not publish the bit names, so access is shown per product by the live answers below.")


def request_log_proof(request_ids: set[str]) -> tuple[int, int, int]:
    """(found, billable_false, billable_true) for our request IDs in /users/logs."""
    found, free, billable = 0, 0, 0
    remaining = set(request_ids)
    for page in range(10):
        status, logs = crs.account_get(f"/users/logs?page={page}&size=100")
        items = logs.get("content", []) if isinstance(logs, dict) else []
        for item in items:
            if item.get("id") in remaining:
                remaining.discard(item["id"])
                found += 1
                if item.get("billable") is False:
                    free += 1
                else:
                    billable += 1
        if not remaining or status != 200 or not (isinstance(logs, dict) and logs.get("hasMore")):
            break
    return found, free, billable


def retention_spot_check(persona: dict, product: str, request_id: str) -> str:
    status, ret = crs.retention(request_id)
    if status != 200 or not isinstance(ret, dict):
        return f"retention {request_id}: HTTP {status}"
    try:
        sent = json.loads(ret.get("rawClientRequest") or "null")
    except (TypeError, ValueError):
        sent = ret.get("rawClientRequest")
    same = sent == persona["requests"][product]["body"]
    return (f"retention {persona['id']} {product} {request_id}: what CRS received "
            f"{'equals' if same else 'DIFFERS FROM'} the registered persona body")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", action="store_true", help="write recorded/<persona>.json for the offline fallback")
    args = ap.parse_args(argv)

    if crs.login_locked():
        print(crs._lock_message())
        return 2
    try:
        show_account()
    except crs.CRSError as e:
        print(f"Cannot reach the CRS account: {type(e).__name__}: {e}")
        return 2

    print(f"\n{'ID':<4} {'NAME':<19} {'IDENTITY':<20} {'DEC':<4} {'BANKRUPTCY':<30} {'LIENS / JUDGMENTS':<34} "
          f"{'CONTACT':<19} {'SOURCE':<8} CHECK")
    failures, request_ids, statuses = {}, set(), {p: {} for p in crs.PRODUCTS}
    first = {}
    for persona in sorted(crs.personas().values(), key=lambda p: p["id"]):
        raw = {}
        result = crs.check_person(person_input(persona), raw_out=raw)
        bad = mismatches(persona, result)
        print(row(persona, result, not bad))
        if result.get("source") != "live":
            print(f"     not live: {result.get('reason') or ''} {result.get('detail') or result.get('fallback_reason') or ''}")
        if bad:
            failures[persona["id"]] = bad
        for product, resp in raw.items():
            statuses[product][resp["status"]] = statuses[product].get(resp["status"], 0) + 1
            if resp.get("request_id"):
                request_ids.add(resp["request_id"])
                first.setdefault((persona["id"], product), resp["request_id"])
        if args.record:
            if result.get("source") == "live" and not result.get("errors"):
                crs.RECORDED_DIR.mkdir(exist_ok=True)
                (crs.RECORDED_DIR / f"{persona['id']}.json").write_text(json.dumps({
                    "persona": persona["id"],
                    "recorded_at": result["checked_at"],
                    "note": "Synthetic CRS sandbox persona. Raw answers trimmed to the fields the checks read; "
                            "no credit rating data, no token.",
                    "result": result,
                    "raw": raw,
                }, indent=2) + "\n", encoding="utf-8")
            else:
                print(f"     not recorded (an earlier recording is kept): source={result.get('source')} "
                      f"errors={result.get('errors')}")

    print("\nHTTP status per product: " + "; ".join(
        f"{p} {', '.join(f'{s}x{n}' for s, n in sorted(c.items())) or 'not called'}" for p, c in statuses.items()))
    denied = {p: c for p, c in statuses.items() if 401 in c or 403 in c}
    if denied:
        print("No access (401/403): " + ", ".join(denied))
        failures["account"] = [f"401/403 from {', '.join(denied)}"]

    if request_ids:
        found, free, billable = request_log_proof(request_ids)
        print(f"Request log: {found} of {len(request_ids)} calls found, {free} billable=false "
              f"(answered by the sandbox persona service), {billable} billable=true")
        if billable:
            failures["billable"] = [f"{billable} request(s) reached a real vendor"]
        if ("P07", "pitchpoint_blj") in first:
            print(retention_spot_check(crs.persona_by_id("P07"), "pitchpoint_blj", first[("P07", "pitchpoint_blj")]))

    guard = crs.check_person({"ssn": "123-45-6789", "first": "ROSA", "last": "DIAZ"})
    print(f"Guard: non-persona SSN -> sent={guard['sent']} reason={guard.get('reason')}")
    if guard["sent"] is not False:
        failures["guard"] = ["a non-persona SSN was sent"]

    if args.record:
        print(f"Recorded answers in {crs.RECORDED_DIR}")
    if failures:
        print(f"\n{len(failures)} problem(s):")
        for key, bad in failures.items():
            for b in bad:
                print(f"  {key}: {b}")
        return 1
    print("\nAll 20 personas match their expected outcomes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
