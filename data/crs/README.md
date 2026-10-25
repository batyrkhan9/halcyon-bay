# CRS sandbox client

The output shape is in `data/FORMAT.md`, section "CRS sandbox".

```bash
python3 data/crs/crs.py check --ssn 666701007 --first MARCUS --last BELLAMY --dob 1975-12-05 --phone 5550101007
python3 data/crs/check.py            # all 20 personas live, compared with the expected outcomes (exit 1 on a mismatch)
python3 data/crs/check.py --record   # also rewrites recorded/P01.json ... P20.json
python3 -m unittest data/crs/test_crs.py   # offline, no network
```

From Python: `sys.path.insert(0, "data/crs"); import crs; crs.check_person({"ssn": ..., "first_name": ..., ...})`.

## Rules the code enforces

- Only the 20 persona SSNs in `personas.json` are ever sent, and each one is sent with that persona's registered body. Nothing is built from caller data. Any other SSN gets `sent: false` and no network call.
- Only four routes are allowed: TruValidate `/basic`, PitchPoint `/pp/fcrablj/data`, AccurateAppend `/reverse` and the TU prequal credit report. Criminal, eviction, Fraud Finder, Equifax and Experian are never called.
- Credit scores, the FACTA score alerts and TruValidate risk points are dropped before anything is returned or stored. The stored credit report keeps only file status, error messages and public records.
- If the sandbox can't be reached, the answer comes from `recorded/<persona>.json` with `source: "recorded"` and a `fallback_reason`.

## Login

- The client logs in once and caches the token in `.token.json` (mode 600, gitignored) until about 2 minutes before it expires (tokens last 3600 s).
- A failed login writes `.login_failed`, and every later login is refused, because repeated failed logins disable the account with no warning. To recover, fix `CRS_USERNAME` / `CRS_PASSWORD` in the repo-root `.env` (keep the password in double quotes: an unquoted `#` starts a comment), then delete `data/crs/.login_failed`.
