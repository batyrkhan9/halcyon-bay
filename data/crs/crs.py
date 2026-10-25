#!/usr/bin/env python3
"""CRS sandbox client for Halcyon Bay.

Four checks, used only to help a patient or stop a collection, never to deny:
identity (TransUnion TruValidate), deceased (TruValidate + TU credit report),
bankruptcy and liens/judgments (PitchPoint, cross-checked with TU credit report
public records) and contact (AccurateAppend reverse lookup by phone).

Safety rules, all enforced in this file:
- Persona guard: a request is only sent when the caller's SSN is one of the 20
  sandbox persona SSNs, and then the persona's registered body is sent unchanged.
  A body is never built from caller data. Anything else gets sent: false and no
  network call at all.
- Log in once, cache the token in .token.json (0600), reuse it until near expiry.
  A failed login writes .login_failed and every later login is refused until a
  person fixes the credentials and deletes that file.
- Credit scores and score-like fields are dropped before anything is returned or
  stored. Criminal, eviction and Fraud Finder are never called.
- If the sandbox can't be reached, the answer comes from recorded/<persona>.json
  with source "recorded".

    python3 data/crs/crs.py check --ssn 666701007 --first MARCUS --last BELLAMY \
        --dob 1975-12-05 --phone 5550101007
or
    sys.path.insert(0, "data/crs"); import crs; crs.check_person({...})
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import datetime as dt
import http.client
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
PERSONAS_FILE = HERE / "personas.json"
TOKEN_FILE = HERE / ".token.json"
LOGIN_FAILED_FILE = HERE / ".login_failed"
RECORDED_DIR = HERE / "recorded"

BASE_URL = "https://api-sandbox.stitchcredit.com/api"
TIMEOUT = 20.0          # seconds per HTTP call
EXPIRY_MARGIN = 120     # log in again when the token has less than this left
RELOGIN_MIN_AGE = 60    # a token younger than this that gets a 401 means "no access", not "expired"

# The only products we ever call, each with the only route it may use.
PRODUCTS = {
    "tu_identity_verification": "POST /transunion/identity-manager-verification/basic",
    "pitchpoint_blj": "POST /pp/fcrablj/data",
    "accurate_append": "POST /accurate-append/reverse",
    "credit_report_tu": "POST /transunion/credit-report/standard/tu-prequal-fico9",
}

NOT_A_SANDBOX_PERSONA = "NOT_A_SANDBOX_PERSONA"


class CRSError(Exception):
    """Something is wrong that a person has to look at."""


class NetworkError(CRSError):
    """The sandbox could not be reached (timeout, DNS, connection, 5xx or 429 after retries)."""

    def __init__(self, message: str, timeout: bool = False):
        super().__init__(message)
        self.timeout = timeout


class LoginLocked(CRSError):
    """An earlier login failed. No login is attempted until a person deletes .login_failed."""


class LoginFailed(CRSError):
    """The login call answered non-2xx. .login_failed has been written."""


# ---------------------------------------------------------------- credentials

def _parse_env_value(value: str) -> str:
    value = value.strip()
    if value[:1] == '"':
        out, i = [], 1
        while i < len(value):
            ch = value[i]
            if ch == "\\" and i + 1 < len(value) and value[i + 1] in '"\\':
                out.append(value[i + 1])
                i += 2
                continue
            if ch == '"':
                break
            out.append(ch)
            i += 1
        return "".join(out)
    if value[:1] == "'":
        end = value.find("'", 1)
        return value[1:end] if end > 0 else value[1:]
    # Unquoted: a '#' at the start or after whitespace starts a comment.
    return re.split(r"(?:^|\s)#", value, maxsplit=1)[0].strip()


def _read_env_file(path: Path) -> dict:
    out = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = _parse_env_value(value)
    return out


def credentials() -> tuple[str, str]:
    """CRS_USERNAME and CRS_PASSWORD from the environment, else from the repo-root .env."""
    user = os.environ.get("CRS_USERNAME")
    password = os.environ.get("CRS_PASSWORD")
    if not user or not password:
        env = _read_env_file(REPO_ROOT / ".env")
        user = user or env.get("CRS_USERNAME", "")
        password = password or env.get("CRS_PASSWORD", "")
    return user or "", password or ""


# ---------------------------------------------------------------- HTTP

def _http(method: str, path: str, body=None, token: str | None = None,
          timeout: float = TIMEOUT) -> tuple[int, dict, bytes]:
    """One HTTP call. Returns (status, headers, body bytes). Raises NetworkError if unreachable.

    Every network access in this module goes through here, so tests patch this function.
    """
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE_URL + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as e:
        try:
            payload = e.read()
        except Exception:
            payload = b""
        return e.code, dict(e.headers.items()) if e.headers else {}, payload
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError,
            http.client.HTTPException, OSError) as e:
        reason = getattr(e, "reason", e)
        raise NetworkError(f"{method} {path}: {type(e).__name__}: {reason}",
                           timeout=isinstance(reason, (socket.timeout, TimeoutError))) from None


def _header(headers: dict, name: str):
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


def _json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"_text": raw.decode("utf-8", "replace")[:2000]}


# ---------------------------------------------------------------- token cache and login

_token_lock = threading.Lock()
_token: dict | None = None


def _now() -> float:
    return time.time()


def _expiry_epoch(token: str, expires, now: float) -> float:
    """When the token expires, from the JWT's own exp claim, else the login response's expires."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        exp = json.loads(base64.urlsafe_b64decode(part)).get("exp")
        if isinstance(exp, (int, float)) and exp > 1e9:
            return float(exp)
    except Exception:
        pass
    if isinstance(expires, str):
        s = expires.strip()
        if re.fullmatch(r"\d+(\.\d+)?", s):
            expires = float(s)
        else:
            try:
                d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=dt.timezone.utc)
                return d.timestamp()
            except ValueError:
                pass
    if isinstance(expires, (int, float)) and not isinstance(expires, bool):
        if expires > 1e12:
            return expires / 1000.0
        if expires > 1e9:
            return float(expires)
        if expires > 0:
            return now + float(expires)
    return now + 30 * 60


def _usable(info: dict | None) -> bool:
    return bool(info and info.get("token")
                and float(info.get("expires_at", 0)) - _now() > EXPIRY_MARGIN)


def _load_token_file() -> dict | None:
    try:
        info = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) else None


def _save_token_file(info: dict) -> None:
    tmp = TOKEN_FILE.with_name(TOKEN_FILE.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(info, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKEN_FILE)
    os.chmod(TOKEN_FILE, 0o600)


def _lock_message() -> str:
    return (f"CRS login is locked: an earlier login failed (see {LOGIN_FAILED_FILE}). "
            "Repeated failed logins disable the account, so no login is attempted. "
            "A person must fix CRS_USERNAME / CRS_PASSWORD in the repo-root .env, "
            f"then delete {LOGIN_FAILED_FILE}.")


def login_locked() -> bool:
    return LOGIN_FAILED_FILE.exists()


def _login() -> dict:
    """POST /users/login exactly once. Never retried. A non-2xx answer writes .login_failed."""
    if LOGIN_FAILED_FILE.exists():
        raise LoginLocked(_lock_message())
    user, password = credentials()
    if not user or not password:
        raise CRSError("CRS_USERNAME / CRS_PASSWORD are not set (environment or repo-root .env). "
                       "No login was attempted.")
    status, _headers, raw = _http("POST", "/users/login", {"username": user, "password": password})
    data = _json(raw) if 200 <= status < 300 else None
    token = data.get("token") if isinstance(data, dict) else None
    if not token:
        text = raw.decode("utf-8", "replace")[:2000]
        for secret in (password, user):
            text = text.replace(secret, "***")
        LOGIN_FAILED_FILE.write_text(json.dumps({
            "failed_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": status,
            "body": text,
            "fix": "Check CRS_USERNAME / CRS_PASSWORD in the repo-root .env (password double-quoted), "
                   "then delete this file. Do not retry in a loop: failed logins disable the account.",
        }, indent=2) + "\n", encoding="utf-8")
        raise LoginFailed(f"CRS login failed with HTTP {status}. Wrote {LOGIN_FAILED_FILE}; "
                          "no further login will be attempted until a person fixes the "
                          "credentials and deletes it.")
    now = _now()
    info = {
        "token": token,
        "expires": data.get("expires"),
        "refreshToken": data.get("refreshToken"),
        "obtained_at": now,
        "expires_at": _expiry_epoch(token, data.get("expires"), now),
    }
    _save_token_file(info)
    return info


def get_token(stale: str | None = None) -> str:
    """A usable token: memory, then .token.json, then one login.

    stale: a token that just got a 401. It is replaced by a fresh login, unless another
    thread already replaced it or it is too young to have expired (then the 401 means
    the account has no access to that product, and logging in again would not help).
    """
    global _token
    with _token_lock:
        if stale is None:
            if _usable(_token):
                return _token["token"]
            cached = _load_token_file()
            if _usable(cached):
                _token = cached
                return _token["token"]
        else:
            if _token and _token.get("token") != stale and _usable(_token):
                return _token["token"]
            if _token and _token.get("token") == stale and \
                    _now() - float(_token.get("obtained_at", 0)) < RELOGIN_MIN_AGE:
                return stale
        _token = _login()
        return _token["token"]


def account_get(path: str) -> tuple[int, object]:
    """GET an account endpoint (/users, /users/logs...). Retries 429/5xx a few times."""
    token = get_token()
    delays = [0.5, 1, 2, 4]
    while True:
        status, headers, raw = _http("GET", path, token=token)
        if (status >= 500 or status == 429) and delays:
            time.sleep(_retry_after(headers, delays.pop(0)) if status == 429 else delays.pop(0))
            continue
        return status, _json(raw)


def retention(request_id: str) -> tuple[int, object]:
    """GET /users/retention/{RequestID}: what was sent and what came back. 5xx right after a
    call is normal (S3 lag); account_get retries with 0.5/1/2/4 s backoff."""
    return account_get(f"/users/retention/{request_id}")


def _retry_after(headers: dict, default: float) -> float:
    try:
        return min(max(float(_header(headers, "Retry-After")), 0.5), 10.0)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- personas and the guard

_personas_by_ssn: dict | None = None


def personas() -> dict:
    """The 20 sandbox personas keyed by SSN. Every persona SSN must be in the never-issued 666 area."""
    global _personas_by_ssn
    if _personas_by_ssn is None:
        data = json.loads(PERSONAS_FILE.read_text(encoding="utf-8"))
        out = {}
        for p in data["personas"]:
            ssn = p["identity"]["ssn"]
            if not re.fullmatch(r"666\d{6}", ssn):
                raise CRSError(f"persona {p.get('id')} has an SSN outside the 666 test area")
            out[ssn] = p
        _personas_by_ssn = out
    return _personas_by_ssn


def persona_by_id(pid: str) -> dict:
    for p in personas().values():
        if p["id"] == pid:
            return p
    raise KeyError(pid)


def _digits(value) -> str:
    return re.sub(r"\D", "", "" if value is None else str(value))


def find_persona(ssn) -> dict | None:
    """The persona whose SSN is exactly this one (digits only), or None."""
    return personas().get(_digits(ssn))


def _registered_request(persona: dict, product: str) -> tuple[str, str, dict]:
    """(method, path, body) exactly as registered for this persona and product."""
    if product not in PRODUCTS:
        raise CRSError(f"{product} is not one of the products this client may call")
    req = persona["requests"][product]
    endpoint = req["endpoint"]
    if "{config}" in endpoint:
        endpoint = endpoint.replace("{config}", req["config"])
    if endpoint != PRODUCTS[product]:
        raise CRSError(f"{persona['id']} {product}: registered endpoint {endpoint!r} is not "
                       f"the allowed route {PRODUCTS[product]!r}")
    method, path = endpoint.split(" ", 1)
    return method, path, copy.deepcopy(req["body"])


def _send(persona: dict, product: str) -> dict:
    """Send this persona's registered body for one product. Never takes a body from a caller.

    Returns {"status", "request_id", "body"} for any HTTP answer we keep (2xx and 4xx).
    Raises NetworkError when the sandbox can't be reached, LoginLocked / LoginFailed on login trouble.
    """
    method, path, body = _registered_request(persona, product)
    token = get_token()
    relogged = False
    delays_5xx = [0.5, 1.0]
    delays_dropped = [0.5, 1.0]   # a dropped connection is retried; a timeout is not (it already took 20 s)
    retries_429 = 2
    while True:
        try:
            status, headers, raw = _http(method, path, body, token=token)
        except NetworkError as e:
            if e.timeout or not delays_dropped:
                raise
            time.sleep(delays_dropped.pop(0))
            continue
        if status == 401 and not relogged:
            relogged = True
            new = get_token(stale=token)
            if new != token:
                token = new
                continue
        if status == 429 and retries_429 > 0:
            retries_429 -= 1
            time.sleep(_retry_after(headers, 2.0))
            continue
        if status >= 500 and delays_5xx:
            time.sleep(delays_5xx.pop(0))
            continue
        if status >= 500 or status == 429:
            raise NetworkError(f"{product}: HTTP {status} after retries")
        return {"status": status, "request_id": _header(headers, "RequestID"), "body": _json(raw)}


# ---------------------------------------------------------------- scrubbing

_SCORE_KEY = re.compile(r"score|fico|vantage", re.I)
# What we keep of each answer before it is stored. Everything else is dropped: tradelines,
# balances, inquiries, summaries, scores, the FACTA score alerts and TruValidate's risk points.
_KEEP = {
    "tu_identity_verification": ("fileNumber", "fileSummary", "indicative", "addOnProducts"),
    "credit_report_tu": ("responseDetail", "errorMessages", "creditFiles", "publicRecords"),
}
_KEEP_CREDIT_FILE = ("creditFileDetail", "aliases")
_KEEP_ERROR = ("timestamp", "codes", "messages", "details")


def _drop_score_keys(obj):
    if isinstance(obj, dict):
        return {k: _drop_score_keys(v) for k, v in obj.items() if not _SCORE_KEY.search(str(k))}
    if isinstance(obj, list):
        return [_drop_score_keys(v) for v in obj]
    return obj


def scrub(product: str, status: int, body):
    """The part of a raw answer we may store: no scores, nothing we don't read."""
    if isinstance(body, dict):
        if not 200 <= status < 300:
            body = {k: v for k, v in body.items() if k in _KEEP_ERROR}
        elif product in _KEEP:
            body = {k: v for k, v in body.items() if k in _KEEP[product]}
            if product == "credit_report_tu" and isinstance(body.get("creditFiles"), list):
                body["creditFiles"] = [{k: v for k, v in f.items() if k in _KEEP_CREDIT_FILE}
                                       for f in body["creditFiles"] if isinstance(f, dict)]
    return _drop_score_keys(body)


# ---------------------------------------------------------------- normalization (pure, no network)

_FAIL_CODES = {"2201", "2202", "2301"}   # SSN not this name, DOB not on file, deceased SSN
_DECEASED_CODE = "2301"


def _as_list(x) -> list:
    if x is None or x == "":
        return []
    return x if isinstance(x, list) else [x]


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _join(*parts) -> str:
    return " ".join(str(p).strip() for p in parts if p not in (None, "") and str(p).strip())


def _fmt_address(street, city, state, zip_code):
    tail = _join(state, zip_code)
    return ", ".join(p for p in (_join(street), _join(city), tail) if p).upper() or None


def _iso_date(value):
    """1975-12-05, 12/05/1975, 12-05-1975, 19751205 or 1975-12-05T00:00:00Z -> 1975-12-05."""
    s = "" if value is None else str(value).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
    else:
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s) or None
        if m:
            mo, d, y = m.groups()
        elif re.fullmatch(r"\d{8}", s):
            y, mo, d = s[:4], s[4:6], s[6:]
        else:
            return None
    try:
        return dt.date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return None


def _pp_date(value):
    if isinstance(value, dict):
        try:
            return dt.date(int(value["year"]), int(value["month"]), int(value["day"])).isoformat()
        except (KeyError, TypeError, ValueError):
            return None
    return _iso_date(value)


def _money(value):
    try:
        return round(float(str(value).replace(",", "").replace("$", "")), 2)
    except (TypeError, ValueError):
        return None


def _upper(value):
    return re.sub(r"[\s-]+", "_", str(value).strip()).upper() if value not in (None, "") else None


def _bankruptcy_status(text) -> str:
    t = (text or "").lower()
    if "discharg" in t:
        return "DISCHARGED"
    if "dismiss" in t:
        return "DISMISSED"
    if any(w in t for w in ("closed", "terminated", "completed")):
        return "CLOSED"
    # Open, Filed, Open - Plan Confirmed, or anything we don't recognise: treated as open
    # (an automatic stay) until a person reads status_text.
    return "OPEN"


def _error_text(resp: dict) -> str:
    body = _dict(resp.get("body"))
    bits = [f"HTTP {resp.get('status')}"]
    for key in ("codes", "messages", "details"):
        bits += [str(x) for x in _as_list(body.get(key))]
    return " ".join(bits)


def _tu_pick(entries):
    entries = [e for e in _as_list(entries) if isinstance(e, dict)]
    return next((e for e in entries if e.get("source") == "FILE"), entries[0] if entries else None)


def normalize_identity(body: dict):
    """TruValidate SubjectRecord -> (identity block, deceased). Raises ValueError if unreadable."""
    verification = next((a["idManagerVerification"] for a in _as_list(body.get("addOnProducts"))
                         if isinstance(a, dict) and isinstance(a.get("idManagerVerification"), dict)), None)
    if verification is None:
        raise ValueError("no addOnProducts[].idManagerVerification in the TruValidate answer")
    problems = [{"code": str(m.get("code")), "text": m.get("text")}
                for m in _as_list(verification.get("messages")) if isinstance(m, dict)]
    codes = {p["code"] for p in problems}
    if not problems:
        result = "PASS"
    elif codes & _FAIL_CODES:
        result = "FAIL"
    else:
        result = "STEP_UP"   # 2401 fraud alert, 2101 address mismatch alone, or a code we don't know
    ind = _dict(body.get("indicative"))
    # The sandbox echoes the input here (source INPUT). We only call it "on file" when TU
    # did not say that this name (2201) or this address (2101) is not on file for the SSN.
    name = address = None
    if "2201" not in codes:
        person = _dict(_dict(_tu_pick(ind.get("names") or ind.get("name"))).get("person"))
        name = _join(person.get("first"), person.get("last")).upper() or None
    if "2101" not in codes:
        entry = _tu_pick(ind.get("addresses") or ind.get("address"))
        if entry:
            st, loc = _dict(entry.get("street")), _dict(entry.get("location"))
            street = _join(*(st.get(k) for k in ("number", "preDirectional", "name", "type", "postDirectional")))
            address = _fmt_address(street, loc.get("city"), loc.get("state"), loc.get("zipCode"))
    deceased = _DECEASED_CODE in codes or bool(_as_list(verification.get("deceases")))
    return {"result": result, "problems": problems, "name_on_file": name, "address_on_file": address}, deceased


def normalize_credit_report(body: dict) -> dict:
    """TU credit report -> deceased flag and public-record bankruptcies only. No score ever leaves here.
    Raises ValueError for errorMessages that are not the deceased answer."""
    errors = [e for e in _as_list(body.get("errorMessages")) if isinstance(e, dict)]
    deceased = any("deceas" in str(e.get("creditErrorMessageText", "")).lower() for e in errors)
    if errors and not deceased:
        raise ValueError("; ".join(_join(e.get("creditErrorMessageCode"), e.get("creditErrorMessageText"))
                                   for e in errors))
    files = [f for f in _as_list(body.get("creditFiles")) if isinstance(f, dict)]
    status = _dict(files[0].get("creditFileDetail")).get("creditFileResultStatusType") if files else None
    bankruptcies = []
    for rec in _as_list(body.get("publicRecords")):
        m = re.match(r"Bankruptcy(?:Chapter)?(\d+)?", str(_dict(rec).get("publicRecordType", "")), re.I)
        if m:
            bankruptcies.append({
                "chapter": m.group(1),
                "status": _bankruptcy_status(rec.get("dispositionType")),
                "status_text": rec.get("dispositionType"),
                "filed_on": _iso_date(rec.get("filedDate")),
                "reported_on": _iso_date(rec.get("reportedDate")),
            })
    return {"file_status": "Deceased" if deceased else status, "deceased": deceased,
            "bankruptcies": bankruptcies}


def normalize_pitchpoint(body: dict):
    """PitchPoint /data -> (bankruptcy records, liens and judgments). Raises ValueError if unreadable."""
    report = body.get("DetailedBLJReport")
    if not isinstance(report, dict):
        raise ValueError("no DetailedBLJReport in the PitchPoint answer")
    bad = [m for m in _as_list(_dict(report.get("Messages")).get("Message"))
           if isinstance(m, dict) and str(m.get("Code", "0")) not in ("0", "")]
    if bad:
        raise ValueError("; ".join(_join(m.get("Code"), m.get("Text")) for m in bad))
    results = _dict(report.get("Results"))

    def court(rec):
        return _dict(rec.get("Court")).get("Name")

    def party(p):
        return _dict(_dict(p).get("Name")).get("UnparsedName")

    bankruptcies = []
    for rec in _as_list(_dict(results.get("Bankruptcies")).get("BankruptcyRecord")):
        rec = _dict(rec)
        closed = next((rec.get(k) for k in ("DischargeDate", "DismissalDate", "DismissedDate", "ClosedDate",
                                            "CloseDate") if rec.get(k)), None)
        bankruptcies.append({
            "chapter": None if rec.get("Chapter") in (None, "") else str(rec.get("Chapter")),
            "status": _bankruptcy_status(rec.get("Status")),
            "status_text": rec.get("Status"),
            "filed_on": _pp_date(rec.get("FilingDate")),
            "closed_on": _pp_date(closed),
            "court": court(rec),
            "case_number": rec.get("CourtCaseNumber"),
        })
    liens_judgments = []
    for rec in _as_list(_dict(results.get("Judgments")).get("JudgmentRecord")):
        rec = _dict(rec)
        liens_judgments.append({
            "type": "JUDGMENT", "amount": _money(rec.get("TotalJudgmentAmount")),
            "filed_on": _pp_date(rec.get("FilingDate")), "status": _upper(rec.get("Status")),
            "creditor": party(rec.get("Plaintiff")), "court": court(rec),
            "case_number": rec.get("CourtCaseNumber"),
        })
    for rec in _as_list(_dict(results.get("Liens")).get("LienRecord")):
        rec = _dict(rec)
        liens_judgments.append({
            "type": "TAX_LIEN" if rec.get("KindOfTax") or rec.get("TaxLienDate") else "LIEN",
            "amount": _money(rec.get("TotalLienAmount")),
            "filed_on": _pp_date(rec.get("FilingDate")), "status": _upper(rec.get("Status")),
            "creditor": party(rec.get("Plaintiff")), "court": court(rec),
            "case_number": rec.get("CourtCaseNumber"),
        })
    return bankruptcies, liens_judgments


def normalize_contact(body: dict, phone: str) -> dict:
    data = body.get("data")
    if not isinstance(data, dict):
        raise ValueError("no data in the AccurateAppend answer")
    records = [r for r in _as_list(data.get("records")) if isinstance(r, dict)]
    out = {"found": bool(records), "name": None, "address": None, "phone": phone}
    if records:
        r = records[0]
        out["name"] = _join(r.get("firstName"), r.get("lastName")).upper() or None
        out["address"] = _fmt_address(r.get("address") or _join(r.get("houseNo"), r.get("streetName")),
                                      r.get("city"), r.get("state"), r.get("postalCode"))
    return out


def _bk_key(b: dict):
    return (b.get("chapter"), b.get("status"), b.get("filed_on"))


def _not_checked_identity() -> dict:
    return {"result": "NOT_CHECKED", "problems": [], "name_on_file": None, "address_on_file": None,
            "request_id": None}


def build_result(persona: dict, raw: dict, checked_at: str, matches, source: str = "live") -> dict:
    """The normalized answer for one persona from its raw answers {product: {status, request_id, body}}.

    Pure: no network. Used for live answers and to re-check the recorded fixtures.
    """
    errors = {}

    def body_of(product):
        resp = raw.get(product)
        if not resp:
            errors[product] = "not called"
            return None, None
        if not 200 <= int(resp.get("status") or 0) < 300 or not isinstance(resp.get("body"), dict):
            errors[product] = _error_text(resp)
            return None, resp.get("request_id")
        return resp["body"], resp.get("request_id")

    def guarded(product, fn, *args):
        body, request_id = body_of(product)
        if body is None:
            return None, request_id
        try:
            return fn(body, *args), request_id
        except ValueError as e:
            errors[product] = str(e)
            return None, request_id

    ident, ident_rid = guarded("tu_identity_verification", normalize_identity)
    credit, credit_rid = guarded("credit_report_tu", normalize_credit_report)
    pitch, pitch_rid = guarded("pitchpoint_blj", normalize_pitchpoint)
    contact, contact_rid = guarded("accurate_append", normalize_contact, persona["identity"]["phone"])

    identity = _not_checked_identity()
    if ident:
        identity.update(ident[0])
    identity["request_id"] = ident_rid

    deceased_votes = [v for v in (ident[1] if ident else None, credit["deceased"] if credit else None)
                      if v is not None]
    deceased = any(deceased_votes) if deceased_votes else None

    # Credit report bankruptcies only count as a cross-check when TU actually returned a file.
    credit_bk = credit["bankruptcies"] if credit and credit["file_status"] == "FileReturned" else None
    bankruptcy = None
    if pitch or credit_bk is not None:
        records = pitch[0] if pitch else credit_bk
        all_records = (pitch[0] if pitch else []) + (credit_bk or [])
        bankruptcy = {
            "open": any(b["status"] == "OPEN" for b in all_records),
            "records": records,
            "credit_report_records": credit_bk,
            "sources_agree": (sorted(map(_bk_key, pitch[0])) == sorted(map(_bk_key, credit_bk))
                              if pitch and credit_bk is not None else None),
            "request_id": pitch_rid,
        }

    if contact:
        contact = dict(contact, request_id=contact_rid)

    return {
        "sent": True,
        "persona": persona["id"],
        "source": source,
        "checked_at": checked_at,
        "input_matches": matches,
        "identity": identity,
        "deceased": deceased,
        "bankruptcy": bankruptcy,
        "liens_judgments": pitch[1] if pitch else None,
        "contact": contact,
        "credit_report": None if credit is None else {
            "file_status": credit["file_status"], "deceased": credit["deceased"], "request_id": credit_rid},
        "errors": errors,
    }


# ---------------------------------------------------------------- caller input

_STREET_WORDS = {
    "STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "DRIVE": "DR", "ROAD": "RD", "BOULEVARD": "BLVD",
    "LANE": "LN", "COURT": "CT", "PLACE": "PL", "TERRACE": "TER", "CIRCLE": "CIR", "PARKWAY": "PKWY",
    "HIGHWAY": "HWY", "EXPRESSWAY": "EXPY", "FREEWAY": "FWY", "SQUARE": "SQ", "TRAIL": "TRL",
    "SUITE": "STE", "APARTMENT": "APT", "FLOOR": "FL", "BUILDING": "BLDG", "NORTH": "N", "SOUTH": "S",
    "EAST": "E", "WEST": "W", "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
}


def _field(person: dict, *names):
    for n in names:
        v = person.get(n)
        if v not in (None, "") and str(v).strip():
            return str(v).strip()
    return None


def _norm_name(value) -> str:
    return " ".join(re.sub(r"[^A-Z ]", " ", str(value or "").upper()).split())


def _norm_address(value) -> str:
    words = re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper()).split()
    return " ".join(_STREET_WORDS.get(w, w) for w in words)


def _caller_name(person: dict):
    first = _field(person, "first", "first_name", "firstName")
    last = _field(person, "last", "last_name", "lastName")
    if not (first and last):
        full = _field(person, "name", "full_name", "debtor_name")
        if full:
            if "," in full:
                last, _, rest = full.partition(",")
                first = (rest.split() or [""])[0]
            else:
                parts = full.split()
                first, last = (parts[0], parts[-1]) if len(parts) > 1 else (None, None)
    return _norm_name(first), _norm_name(last)


def input_matches(person: dict, persona: dict) -> dict:
    """Does what the caller sent agree with the persona on file? A field the caller didn't send is None."""
    ident = persona["identity"]
    first, last = _caller_name(person)
    name = None
    if first and last:
        name = first == _norm_name(ident["first_name"]) and last == _norm_name(ident["last_name"])
    dob_given = _field(person, "dob", "birth_date", "date_of_birth", "debtor_dob")
    dob = _iso_date(dob_given) == ident["dob"] if dob_given else None
    phone_digits = _digits(_field(person, "phone", "phone_number", "debtor_phone"))[-10:]
    phone = (len(phone_digits) == 10 and phone_digits == ident["phone"]) if phone_digits else None
    street = _field(person, "address_line1", "street1", "street", "addressLine1", "address", "debtor_address")
    address = None
    if street:
        got = _norm_address(street)
        zip5 = _digits(_field(person, "zip", "zip_code", "postal_code", "postalCode"))[:5]
        city = _field(person, "city")
        if got == _norm_address(ident["street1"]):
            if zip5:
                address = zip5 == ident["zip"][:5]
            elif city:
                address = _norm_address(city) == _norm_address(ident["city"])
            else:
                address = True
        else:   # one line: "street, city, ST zip"
            address = got == _norm_address(f'{ident["street1"]} {ident["city"]} {ident["state"]} {ident["zip"]}')
    return {"name": name, "dob": dob, "address": address, "phone": phone}


# ---------------------------------------------------------------- the check

def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nothing_checked(checked_at: str, reason: str, persona=None, matches=None, detail=None) -> dict:
    out = {
        "sent": False,
        "reason": reason,
        "persona": persona,
        "source": None,
        "checked_at": checked_at,
        "input_matches": matches,
        "identity": _not_checked_identity(),
        "deceased": None,
        "bankruptcy": None,
        "liens_judgments": None,
        "contact": None,
        "credit_report": None,
        "errors": {},
    }
    if detail:
        out["detail"] = detail
    return out


def _from_recorded(persona: dict, matches: dict, why: str, checked_at: str) -> dict:
    try:
        recorded = json.loads((RECORDED_DIR / f"{persona['id']}.json").read_text(encoding="utf-8"))
        result = copy.deepcopy(recorded["result"])
    except (OSError, ValueError, KeyError):
        return _nothing_checked(checked_at, "CRS_UNAVAILABLE", persona["id"], matches,
                                detail=f"{why}; no recorded answer for {persona['id']}")
    result.update(source="recorded", input_matches=matches, fallback_reason=why)
    return result


def check_person(person: dict, raw_out: dict | None = None) -> dict:
    """Run the four checks for one person. Only sandbox personas are ever sent.

    person: ssn plus any of first/first_name, last/last_name (or name), dob, phone,
    address_line1/street1, city, state, zip. raw_out: if a dict is given, the scrubbed raw
    answers are put in it (check.py --record uses this).
    """
    checked_at = _utc_now()
    persona = find_persona(person.get("ssn"))
    if persona is None:
        return _nothing_checked(checked_at, NOT_A_SANDBOX_PERSONA)
    matches = input_matches(person, persona)
    try:
        get_token()   # log in (at most once) before the parallel calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(PRODUCTS)) as pool:
            futures = {product: pool.submit(_send, persona, product) for product in PRODUCTS}
            raw = {product: f.result() for product, f in futures.items()}
    except CRSError as e:
        if isinstance(e, (LoginLocked, LoginFailed)):
            print(f"crs: {e}", file=sys.stderr)
        return _from_recorded(persona, matches, f"{type(e).__name__}: {e}", checked_at)
    raw = {p: {"status": r["status"], "request_id": r["request_id"], "body": scrub(p, r["status"], r["body"])}
           for p, r in raw.items()}
    if raw_out is not None:
        raw_out.update(raw)
    return build_result(persona, raw, checked_at, matches)


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CRS sandbox checks for one person (sandbox personas only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="run identity, deceased, bankruptcy and contact checks")
    c.add_argument("--ssn", required=True)
    c.add_argument("--first")
    c.add_argument("--last")
    c.add_argument("--dob")
    c.add_argument("--phone")
    c.add_argument("--address", dest="address_line1", help="street line")
    c.add_argument("--city")
    c.add_argument("--state")
    c.add_argument("--zip")
    args = ap.parse_args(argv)
    person = {k: v for k, v in vars(args).items() if k != "cmd" and v is not None}
    print(json.dumps(check_person(person), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
