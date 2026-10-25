"""Offline tests for the CRS sandbox client. No network: every test patches crs._http.

    python3 -m unittest data/crs/test_crs.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402
import crs  # noqa: E402

FIXTURES = sorted(crs.RECORDED_DIR.glob("P*.json"))
SCORE_KEY = re.compile(r"score|fico|vantage", re.I)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def score_hits(obj, path="$") -> list[str]:
    """Every key that looks like a score, and every string value that mentions one."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if SCORE_KEY.search(str(k)):
                hits.append(f"{path}.{k}")
            hits += score_hits(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += score_hits(v, f"{path}[{i}]")
    elif isinstance(obj, str) and "score" in obj.lower():
        hits.append(f"{path}={obj[:60]!r}")
    return hits


def fixture_responder(pid: str, calls: list):
    """A fake _http that answers login and the four products from a recorded fixture."""
    raw = load(crs.RECORDED_DIR / f"{pid}.json")["raw"]
    by_path = {crs.PRODUCTS[p].split(" ", 1)[1]: r for p, r in raw.items()}

    def fake(method, path, body=None, token=None, timeout=None):
        calls.append((method, path, body))
        if path == "/users/login":
            return 200, {}, json.dumps({"token": "tok-1", "expires": 3600, "refreshToken": "ref-1"}).encode()
        r = by_path[path]
        return r["status"], {"RequestID": r["request_id"]}, json.dumps(r["body"]).encode()
    return fake


def no_network(*args, **kwargs):
    raise AssertionError("the test tried to use the network")


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        for target, value in ((crs, {"TOKEN_FILE": self.tmp / ".token.json",
                                     "LOGIN_FAILED_FILE": self.tmp / ".login_failed",
                                     "credentials": lambda: ("test-user", "test-pw#secret"),
                                     "_token": None,
                                     "_http": no_network}),
                              (crs.time, {"sleep": lambda s: None})):
            for name, v in value.items():
                p = mock.patch.object(target, name, v)
                p.start()
                self.addCleanup(p.stop)


class PersonaGuard(Base):
    def test_non_persona_sends_nothing(self):
        http = mock.Mock(side_effect=AssertionError("network used"))
        with mock.patch.object(crs, "_http", http):
            for ssn in ("123-45-6789", "666701099", "66670100", "6667010071", "", None):
                r = crs.check_person({"ssn": ssn, "first": "ROSA", "last": "DIAZ", "dob": "1990-04-02"})
                self.assertIs(r["sent"], False)
                self.assertEqual(r["reason"], "NOT_A_SANDBOX_PERSONA")
                self.assertEqual(r["identity"]["result"], "NOT_CHECKED")
                for check_name in ("deceased", "bankruptcy", "liens_judgments", "contact", "persona", "source"):
                    self.assertIsNone(r[check_name], check_name)
        http.assert_not_called()

    def test_cli_non_persona_sends_nothing(self):
        http = mock.Mock(side_effect=AssertionError("network used"))
        out = io.StringIO()
        with mock.patch.object(crs, "_http", http), contextlib.redirect_stdout(out):
            crs.main(["check", "--ssn", "123456789", "--first", "ROSA", "--last", "DIAZ"])
        self.assertIs(json.loads(out.getvalue())["sent"], False)
        http.assert_not_called()

    def test_persona_gets_its_registered_body_unchanged(self):
        calls = []
        with mock.patch.object(crs, "_http", fixture_responder("P01", calls)):
            r = crs.check_person({"ssn": "666-70-1001", "first": "MAGGIE", "last": "OKAFOR", "dob": "03/14/1984",
                                  "address_line1": "77 OLD MILL RD", "city": "SAN JOSE", "zip": "95112",
                                  "phone": "(408) 555-0199"})
        persona = crs.persona_by_id("P01")
        product_calls = [c for c in calls if c[1] != "/users/login"]
        self.assertEqual(sorted(c[1] for c in product_calls),
                         sorted(e.split(" ", 1)[1] for e in crs.PRODUCTS.values()))
        registered = {crs.PRODUCTS[p].split(" ", 1)[1]: persona["requests"][p]["body"] for p in crs.PRODUCTS}
        for method, path, body in product_calls:
            self.assertEqual(method, "POST")
            self.assertEqual(body, registered[path])
        self.assertNotIn("MAGGIE", json.dumps(product_calls))
        self.assertNotIn("OLD MILL", json.dumps(product_calls))
        self.assertEqual([c[1] for c in calls].count("/users/login"), 1)
        self.assertEqual((r["sent"], r["persona"], r["source"]), (True, "P01", "live"))
        self.assertEqual(r["input_matches"], {"name": False, "dob": True, "address": False, "phone": False})

    def test_only_allowed_products(self):
        self.assertEqual(set(crs.PRODUCTS), {"tu_identity_verification", "pitchpoint_blj", "accurate_append",
                                             "credit_report_tu"})
        persona = crs.persona_by_id("P01")
        for forbidden in ("fraud_finder", "credit_report_efx", "credit_report_exp", "criminal", "eviction"):
            with self.assertRaises(crs.CRSError):
                crs._registered_request(persona, forbidden)
        tampered = json.loads(json.dumps(persona))
        tampered["requests"]["pitchpoint_blj"]["endpoint"] = "POST /criminal/new-request"
        with self.assertRaises(crs.CRSError):
            crs._registered_request(tampered, "pitchpoint_blj")


class InputMatches(unittest.TestCase):
    def test_same_person_different_spelling(self):
        p01 = crs.persona_by_id("P01")
        same = crs.input_matches({"first": "Margaret", "last": "Okafor", "dob": "1984-03-14",
                                  "address_line1": "1420 Willow Creek Drive", "zip": "95125-1234",
                                  "phone": "(555) 010-1001"}, p01)
        self.assertEqual(same, {"name": True, "dob": True, "address": True, "phone": True})

    def test_agency_style_fields(self):
        p07 = crs.persona_by_id("P07")
        m = crs.input_matches({"debtor_name": "BELLAMY, MARCUS J", "debtor_dob": "12/05/1975",
                               "debtor_address": "1507 Peachtree Industrial Boulevard, Atlanta, GA 30341",
                               "debtor_phone": "5550101007"}, p07)
        self.assertEqual(m, {"name": True, "dob": True, "address": True, "phone": True})

    def test_missing_fields_are_unknown_not_mismatches(self):
        self.assertEqual(crs.input_matches({"ssn": "666701007"}, crs.persona_by_id("P07")),
                         {"name": None, "dob": None, "address": None, "phone": None})


@unittest.skipUnless(FIXTURES, "no recorded fixtures yet: run python3 data/crs/check.py --record")
class RecordedFixtures(unittest.TestCase):
    def test_one_fixture_per_persona(self):
        self.assertEqual([f.stem for f in FIXTURES], [f"P{i:02d}" for i in range(1, 21)])

    def test_normalization_reproduces_each_fixture(self):
        for f in FIXTURES:
            with self.subTest(f.stem):
                rec = load(f)
                res = rec["result"]
                again = crs.build_result(crs.persona_by_id(rec["persona"]), rec["raw"], res["checked_at"],
                                         res["input_matches"], res["source"])
                self.assertEqual(again, res)

    def test_each_fixture_has_the_expected_outcome(self):
        for f in FIXTURES:
            with self.subTest(f.stem):
                rec = load(f)
                self.assertEqual(check.mismatches(crs.persona_by_id(rec["persona"]), rec["result"]), [])

    def test_key_personas(self):
        r = {f.stem: load(f)["result"] for f in FIXTURES}
        bk = r["P07"]["bankruptcy"]
        self.assertTrue(bk["open"])
        self.assertEqual({k: bk["records"][0][k] for k in ("chapter", "status", "filed_on", "closed_on")},
                         {"chapter": "13", "status": "OPEN", "filed_on": "2025-02-14", "closed_on": None})
        self.assertTrue(bk["sources_agree"])
        p06 = r["P06"]["bankruptcy"]
        self.assertFalse(p06["open"])
        self.assertEqual((p06["records"][0]["status"], p06["records"][0]["closed_on"]), ("DISCHARGED", "2024-01-18"))
        self.assertTrue(r["P14"]["deceased"])
        self.assertTrue(r["P14"]["credit_report"]["deceased"])
        self.assertIn("2301", [p["code"] for p in r["P14"]["identity"]["problems"]])
        self.assertEqual(r["P12"]["contact"]["name"], "RAJESH MENON")
        self.assertIsNone(r["P12"]["identity"]["name_on_file"])   # 2201: the name is not on file for that SSN
        self.assertEqual(r["P16"]["identity"]["result"], "STEP_UP")
        self.assertEqual([(x["type"], x["amount"], x["creditor"]) for x in r["P08"]["liens_judgments"]],
                         [("JUDGMENT", 12300.0, "LAKEVIEW CONTRACTORS INC"),
                          ("TAX_LIEN", 7450.0, "ILLINOIS DEPARTMENT OF REVENUE")])
        self.assertIs(r["P04"]["contact"]["found"], False)
        self.assertEqual(r["P07"]["identity"]["address_on_file"], "1507 PEACHTREE INDUSTRIAL BLVD, ATLANTA, GA 30341")


class NoScores(unittest.TestCase):
    @unittest.skipUnless(FIXTURES, "no recorded fixtures yet")
    def test_no_score_in_any_fixture(self):
        for f in FIXTURES:
            with self.subTest(f.stem):
                self.assertEqual(score_hits(load(f)), [])
                text = f.read_text()
                self.assertIsNone(re.search(r"eyJ[\w-]+\.[\w-]+\.", text), "a JWT is in the fixture")
                self.assertNotIn("Bearer", text)
                self.assertNotIn("refreshToken", text)

    def test_scrub_credit_report(self):
        body = {
            "scores": [{"modelName": "TransUnionVantageScore4.0", "scoreValue": "790", "scoreFactors": []}],
            "responseAlertMessages": [{"responseAlertMessageCategoryType": "FACTARiskScoreValue"}],
            "tradelines": [{"creditorName": "BANK", "balance": 100}],
            "summaries": {"tradeSummary": {}},
            "errorMessages": None,
            "creditFiles": [{"creditFileDetail": {"creditFileResultStatusType": "FileReturned"},
                             "employments": [{"employerName": "X"}], "riskScore": 5}],
            "publicRecords": [{"publicRecordType": "BankruptcyChapter13", "dispositionType": "Filed",
                               "filedDate": "2025-02-14"}],
        }
        clean = crs.scrub("credit_report_tu", 200, body)
        self.assertEqual(score_hits(clean), [])
        self.assertEqual(set(clean), {"errorMessages", "creditFiles", "publicRecords"})
        self.assertEqual(crs.normalize_credit_report(clean)["bankruptcies"][0]["status"], "OPEN")

    def test_scrub_identity_drops_risk_points(self):
        body = {"custom": {"idmanagerVerAnalysisV2": {"verificationSummary": {"verificationPoint": 30}}},
                "addOnProducts": [{"idManagerVerification": {"messages": []}, "fraudScore": 3}],
                "indicative": {}, "fileSummary": {}}
        clean = crs.scrub("tu_identity_verification", 200, body)
        self.assertNotIn("custom", clean)
        self.assertNotIn("fraudScore", clean["addOnProducts"][0])


class LoginLock(Base):
    def test_failed_login_writes_lock_and_never_retries(self):
        http = mock.Mock(return_value=(401, {}, b'{"codes":["CRS113"],"messages":["Access Denied test-pw#secret"]}'))
        err = io.StringIO()
        with mock.patch.object(crs, "_http", http), contextlib.redirect_stderr(err):
            with self.assertRaises(crs.LoginFailed):
                crs.get_token()
            self.assertTrue(crs.LOGIN_FAILED_FILE.exists())
            text = crs.LOGIN_FAILED_FILE.read_text()
            self.assertIn("401", text)
            self.assertNotIn("test-pw#secret", text)
            with self.assertRaises(crs.LoginLocked):
                crs.get_token()
            r = crs.check_person(check.person_input(crs.persona_by_id("P07")))
        self.assertEqual(http.call_count, 1)   # one login attempt, ever
        if FIXTURES:
            self.assertEqual(r["source"], "recorded")
            self.assertIn("LoginLocked", r["fallback_reason"])
        self.assertIn("delete", err.getvalue())

    def test_lock_file_blocks_login_without_calling(self):
        crs.LOGIN_FAILED_FILE.write_text("{}")
        http = mock.Mock(side_effect=AssertionError("network used"))
        with mock.patch.object(crs, "_http", http):
            with self.assertRaises(crs.LoginLocked):
                crs.get_token()
        http.assert_not_called()

    def test_network_error_on_login_is_not_a_failed_login(self):
        with mock.patch.object(crs, "_http", side_effect=crs.NetworkError("dns")):
            with self.assertRaises(crs.NetworkError):
                crs.get_token()
        self.assertFalse(crs.LOGIN_FAILED_FILE.exists())

    def test_token_cached_0600_and_reused(self):
        http = mock.Mock(return_value=(200, {}, b'{"token":"tok-1","expires":3600,"refreshToken":"ref-1"}'))
        with mock.patch.object(crs, "_http", http):
            self.assertEqual(crs.get_token(), "tok-1")
            crs._token = None   # a new process: reads .token.json
            self.assertEqual(crs.get_token(), "tok-1")
        self.assertEqual(http.call_count, 1)
        self.assertEqual(stat.S_IMODE(os.stat(crs.TOKEN_FILE).st_mode), 0o600)
        self.assertAlmostEqual(load(crs.TOKEN_FILE)["expires_at"], time.time() + 3600, delta=60)

    def test_401_logs_in_again_at_most_once(self):
        calls = []

        def fake(method, path, body=None, token=None, timeout=None):
            calls.append(path)
            if path == "/users/login":
                return 200, {}, b'{"token":"tok-new","expires":3600,"refreshToken":"r"}'
            return 401, {}, b'{"codes":["CRS111"],"messages":["Access Denied"]}'

        crs._token = {"token": "tok-old", "obtained_at": time.time() - 3000, "expires_at": time.time() + 600}
        persona = crs.persona_by_id("P07")
        with mock.patch.object(crs, "_http", fake):
            self.assertEqual(crs._send(persona, "pitchpoint_blj")["status"], 401)
            self.assertEqual(calls.count("/users/login"), 1)
            calls.clear()   # the new token is fresh, so another 401 means "no access", not "expired"
            self.assertEqual(crs._send(persona, "pitchpoint_blj")["status"], 401)
            self.assertEqual(calls.count("/users/login"), 0)


class OfflineFallback(Base):
    @unittest.skipUnless(FIXTURES, "no recorded fixtures yet")
    def test_network_failure_answers_from_recorded(self):
        with mock.patch.object(crs, "_http", side_effect=crs.NetworkError("unreachable")):
            r = crs.check_person({"ssn": "666701007", "first": "MARCUS", "last": "BELLAMY"})
        self.assertEqual((r["sent"], r["persona"], r["source"]), (True, "P07", "recorded"))
        self.assertTrue(r["bankruptcy"]["open"])
        self.assertEqual(r["input_matches"], {"name": True, "dob": None, "address": None, "phone": None})
        self.assertEqual(score_hits(r), [])
        self.assertFalse(crs.LOGIN_FAILED_FILE.exists())

    def test_dropped_connection_is_retried(self):
        calls = []
        responder = fixture_responder("P07", calls)
        drops = {"left": 1}

        def flaky(method, path, body=None, token=None, timeout=None):
            if path != "/users/login" and drops["left"]:
                drops["left"] -= 1
                raise crs.NetworkError("RemoteDisconnected")
            return responder(method, path, body, token, timeout)

        if not FIXTURES:
            self.skipTest("no recorded fixtures yet")
        with mock.patch.object(crs, "_http", flaky):
            r = crs.check_person(check.person_input(crs.persona_by_id("P07")))
        self.assertEqual(r["source"], "live")


class EnvParsing(unittest.TestCase):
    def test_quotes_and_comments(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('CRS_USERNAME="alice"\nCRS_PASSWORD="p#ss word"\nPLAIN=value # comment\n'
                         "export SINGLE='a#b'\n# CRS_PASSWORD=ignored\n")
            self.assertEqual(crs._read_env_file(p), {"CRS_USERNAME": "alice", "CRS_PASSWORD": "p#ss word",
                                                     "PLAIN": "value", "SINGLE": "a#b"})


if __name__ == "__main__":
    unittest.main()
