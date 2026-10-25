# data/

The simulated hospital, the answer key and the CRS sandbox calls. Owner: Noriaki. The contract with the core is [FORMAT.md](FORMAT.md).

## What is real and what is simulated

- Real: the laws (IRS 501(r), California AB 1020, AB 2297 and SB 1061), the federal poverty levels for 2025 and 2026, and the CRS sandbox API, called live.
- Simulated: Halcyon Bay Community Hospital, its policy, its staff, every patient, account, document and collection agency record. Every SSN is fake by construction and every phone uses area code 555.
- The 20 CRS sandbox personas are CRS's own fake people. Nine of our patients are personas, so the CRS checks return real sandbox answers for them.

## The world

18 months of history (Jan 2025 to Jun 2026) and 3 live months (Jul to Sep 2026), replayed one day at a time: 1,796 patients, 1,961 accounts, 1,257 assistance applications, 1,587 income documents, 26 collection agency requests and 14 staff. It is exported like five separate systems that don't agree with each other: billing, financial assistance, the collection agency, the mailroom's scans and HR.

Nothing in `world/` is labeled. The core has to find the problems on its own, including:

- 30 patients denied in the history under the rules that changed in January 2025: $227,778.45 to make them whole. Two more were denied as over income when they were under 400%.
- 8 denials with an illegal stated reason but the right outcome, which must not be reversed.
- A CalFresh rule the office never wrote down: it changes 10 past cases worth $59,235.30.
- Duplicates, mismatched names, missing documents with other proof, stopped payment plans and a 12-month approval that should cover a later visit.
- Illegal agency requests, a pay stub with hidden instructions, and a counselor who is also a patient.
- 316 live accounts that need work: 292 clear cases and 24 that need a person.

## Answer key

`answer_key/` has the right outcome, dollars and reason for every live account, every history finding, the CalFresh backtest, the patterns to learn and all 149 planted cases. The core never reads it. Only the score script does.

## CRS

Our sandbox has no income product, so we use CRS only to help a patient or stop a collection: identity before a merge, deceased and bankruptcy before any collection action, and a current address so the legal notice reaches the patient. Credit scores are dropped before anything sees them. Criminal and eviction data are never used. The client only ever sends a sandbox persona's own registered request, so nothing can reach a real bureau.

## Commands

```bash
python3 data/generate/generate.py        # regenerate world/ and answer_key/ (same seed, same bytes)
python3 data/generate/validate.py        # every check, including determinism and agreement with core/
python3 data/crs/check.py                # all 20 CRS personas, live
python3 -m unittest data/crs/test_crs.py # CRS client tests, offline
python3 data/tools/add_account.py --day 2026-07-15 --json '{...}'   # judge box: add one patient
python3 data/tools/add_account.py --reset
```

CRS needs `CRS_USERNAME` and `CRS_PASSWORD` in the repo root `.env`.
