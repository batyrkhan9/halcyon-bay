# Core to UI interface

How the UI reads state and sends approvals. Batyrkhan writes this file; changes need Noriaki's ok.

Status: draft. Everything under "Live now" works today against a small fake office. Everything under "Coming" is the planned shape, and may still change before 3:20.

## Run it

From the repo root:

```bash
uv venv core/.venv --python 3.12
uv pip install --python core/.venv/bin/python -r core/requirements.txt
core/.venv/bin/python -m core.dev_seed --offline
core/.venv/bin/uvicorn core.api:main --factory --port 8000
```

The API is at http://localhost:8000, and every endpoint is listed at http://localhost:8000/docs. `core.dev_seed` fills `core/state/halcyon.db` with a few made-up accounts and has the agent work them, so you can build screens before the real data lands. Set `HALCYON_DB` to use another file.

To run against the real simulated hospital in `data/world/` instead, load the 18 months of history, then replay live days with the agent working each new case:

```bash
core/.venv/bin/python -m core.sync onboard
core/.venv/bin/python -m core.sync day 2026-07-01 --through 2026-07-07 --work
```

Both write the same `core/state/halcyon.db`, so pick one. On real data, documents include `APPLICATION` (the form as the applicant filled it in), `NOTE` (staff notes), `BILLING` (the registration record) and the mailroom kinds from `data/FORMAT.md`, and `account.sources` holds the billing and patient rows as exported.

The agent reads documents with Claude, which needs `ANTHROPIC_API_KEY` in `.env` at the repo root. Without a key, `--offline` replays hand-written readings instead; they show up as model `scripted` in the audit log. Everything after the reading is the real code either way.

## Conventions

- JSON in and out. CORS is open, so any local port can call it.
- Money is always integer cents: `amount_cents`, `billed_cents`. Show `123456` as $1,234.56.
- Dates are ISO strings in simulated time (`2026-07-01`). `/state` gives today's simulated date.
- The UI acts as a person by sending their `actor_id` (from `/actors`). There is no login.
- A refused action returns `403` with `{"denied": true, "reason": "..."}`. Show the reason; it is written for people. The refusal is already in the audit log.
- An unknown ID returns `404`.

## Roles and states

Roles: `counselor`, `director`, `compliance` (people) and `sync`, `agent`, `gateway` (the system).

Work item states: `NEW`, `SCREENING`, `NEEDS_INFO`, `PROPOSED`, `APPROVED`, `REJECTED`, `POSTED`, `CLOSED` (checked, nothing to change).

Proposal kinds: `FREE_CARE`, `DISCOUNT`, `PAYMENT_PLAN`, `COLLECTIONS_REFERRAL`, `PAUSE_COLLECTIONS`, `BLOCK_AGENCY_ACTION`, `MERGE_ACCOUNTS`, `REVERSAL`, `NEW_RULE`.

Proposal status: `PROPOSED`, then `APPROVED` or `REJECTED`, then `POSTED`. An approval is posted right away, so the UI normally sees `POSTED` straight after approving.

Who decides what:
- Counselor: free care, discounts, payment plans and merges up to $5,000.
- Director: the same with no limit, plus collections referrals and new rules.
- Compliance officer: reversals and anything marked `legal_question: true`.
- Nobody decides something they proposed, or anything on their own account.

## Live now

### `GET /state`

```json
{
  "today": "2026-07-01",
  "work_items_by_state": {"NEW": 0, "SCREENING": 0, "NEEDS_INFO": 3, "PROPOSED": 7, "APPROVED": 0, "REJECTED": 0, "POSTED": 0},
  "open_proposals": 7,
  "open_questions": 3
}
```

### `GET /actors`

The people to switch between.

```json
[{"id": "S-003", "name": "Priya Raman", "role": "compliance"}, {"id": "S-001", "name": "Dana Okafor", "role": "counselor"}]
```

### `GET /work-items?state=PROPOSED&limit=200`

`state` is optional. Newest first.

```json
[{"id": "WI-0001", "account_id": "ACC-1001", "state": "PROPOSED", "reason": "Self-pay balance with no financial assistance decision",
  "opened_on": "2026-07-01", "updated_on": "2026-07-01", "patient_name": "Mara Ellison", "billed_cents": 320000}]
```

### `GET /inbox/{actor_id}`

What this person can decide or answer right now. Use it for the approval screen and when switching roles.

```json
{
  "actor": {"id": "S-001", "name": "Dana Okafor", "role": "counselor"},
  "proposals": [Proposal],
  "questions": [Question]
}
```

### `POST /proposals/{id}/decision`

Body: `{"actor_id": "S-002", "approve": true, "note": "optional"}`. Returns the updated Proposal, or `403` with the reason.

### `POST /questions/{id}/answer`

Body: `{"actor_id": "S-001", "answer": "Use the employer letter"}`. Returns the updated Question. The work item goes back to `SCREENING`; call `/work` on it to have the agent pick it up with the answer.

### `POST /work-items/{id}/work`

The agent works one item now: Claude reads the account's documents and any staff answers, code checks every quote and screens the patient, and the agent proposes or asks. Use it for "watch it get processed". Takes a few seconds with Claude.

```json
{
  "result": {"work_item_id": "WI-0001", "account_id": "ACC-1001", "did": "PROPOSED",
             "detail": "P-0002: FREE_CARE adjusting $3,200.00. Income is 121% of the poverty level, at or under 200%: free care."},
  "work_item": WorkItem
}
```

`did` is `PROPOSED`, `ASKED` or `WAITING` (the item wasn't `NEW` or `SCREENING`). Returns `503` with `{"detail": "..."}` when Claude can't be reached or the Claude spending cap is reached; the item is left as it was. Calling it again on an unchanged account costs nothing, because the same reading is replayed.

### `GET /accounts/{account_id}`

An account's full story in one call.

```json
{
  "account": {"id": "ACC-1005", "patient_id": "PAT-1005", "patient_name": "Ruth Calloway", "billed_cents": 650000,
              "first_bill_on": "2026-03-02", "collections_paused": true, "sources": {}},
  "documents": [{"id": "DOC-0010", "account_id": "ACC-1005", "kind": "NOTE", "source": "billing_system",
                 "dated": "2026-06-12", "text": "Registration 06/12: pt showed CalFresh EBT card. ..."}],
  "agency_requests": [{"id": "AR-1005-1", "account_id": "ACC-1005", "action": "CREDIT_REPORT",
                       "requested_on": "2026-06-28", "notice_sent_on": null, "status": "BLOCKED"}],
  "work_items": [WorkItem],
  "proposals": [Proposal],
  "questions": [Question],
  "ledger": [{"seq": 1, "proposal_id": "P-0005", "account_id": "ACC-1005", "kind": "BLOCK_AGENCY_ACTION",
              "amount_cents": 0, "reverses": null, "posted_on": "2026-07-01"}],
  "audit": [AuditRow]
}
```

`sources` will hold what each source system says about the account once sync is built. Document `kind` is `PAY_STUB`, `LETTER`, `BANK_STATEMENT`, `NOTE` and the like; show `text` as-is in a monospace block, since it is the raw export. Agency request `status` is `OPEN` or `BLOCKED`.

### `GET /audit?account_id=&actor_id=&allowed=&q=&limit=200`

Every filter is optional. Newest first. `allowed=false` gives only blocked actions. `q` searches the reason, target, details and account ID, so "why did this happen?" is one search.

### Objects

Proposal:

```json
{"id": "P-0003", "work_item_id": "WI-0002", "account_id": "ACC-1002", "kind": "DISCOUNT", "amount_cents": 840000,
 "rationale": "Income is 300% of the poverty level, between 200% and 400%: patient pays 30% of the bill.",
 "evidence": [{"fact": "household of 4", "document_id": "DOC-0004", "quote": "household 4"},
              {"fact": "income from Salary from Northshore Logistics: $99,000.00 annual", "document_id": "DOC-0003",
               "quote": "annual base salary is $99,000.00"}],
 "pattern": null, "legal_question": false, "reverses": null, "subject": null, "status": "PROPOSED",
 "proposed_by": "agent", "proposed_on": "2026-07-01", "decided_by": null, "decided_on": null, "decision_note": null}
```

`amount_cents` is the change to what the patient owes: for a discount, the part forgiven.

`evidence` lists the facts the proposal rests on, each with the document it came from and the exact quote. Showing the quote next to the document is the "why" for the approver.

`pattern` is set when a proposal is a kind a person may want to rule out for good, such as `DISCOUNT_WITHOUT_INCOME_DOCUMENTS` (income only from what the patient told staff). Once a pattern is rejected, the agent asks for documents instead of proposing it again. `subject` names what a safe action acts on, such as `agency_request:AR-1005-1`.

Question:

```json
{"id": "Q-0001", "work_item_id": "WI-0003", "account_id": "ACC-1003", "to_role": "counselor",
 "question": "Income is 200.1% of the poverty level, right at the 200% cutoff. Please confirm the income.",
 "asked_by": "agent", "asked_on": "2026-07-01", "answer": null, "answered_by": null, "answered_on": null}
```

AuditRow:

```json
{"seq": 46, "logged_at": "2026-10-25T09:12:03+00:00", "sim_day": "2026-07-01", "actor_id": "agent", "actor_role": "agent",
 "action": "post", "target": "P-0001", "account_id": "ACC-0907", "allowed": false,
 "reason": "Only the gateway posts changes.", "detail": {}}
```

Actions: `open_work_item`, `move_work_item`, `read_case`, `propose`, `ask`, `answer`, `act_safe`, `approve`, `reject`, `post` and `follow_hidden_instructions`.

- `read_case` is Claude's reading of the account. `detail` has `model`, `facts` (each with its quote), `not_used` (facts code refused, with why), `conflicts` and `missing`.
- `follow_hidden_instructions` is always `allowed: false`: a document tried to instruct the agent, and the reason quotes it. For the attack screen, search `/audit?allowed=false`.

### `GET /discovery`, `GET /learned`, `GET /score`

Live, in the shapes `ui/src/api/types.ts` defines (`Discovery`, `Learned`, `Score`). `/discovery` is filled when `core.sync onboard` runs; each finding carries its reversal `proposal` for the compliance officer. `/score` adds `discovery`, `planted` (pass counts per planted category) and `misses`.

### `POST /sim/advance`

Body: `{"days": 1}` (1 to 7). Syncs each next simulated day from `data/`, then the agent works what it brought. Returns the same shape as `GET /state`. `409` past 2026-09-30.

### `POST /judge-box`

Body: `{"text": "A single mom of two, about $38,000 a year, ER visit, $6,200 bill, no insurance."}`. Claude turns the text into a made-up patient's fields, `data/tools/add_account.py` writes them to `data/judge/` on today's simulated date, sync loads them and the agent works the account right away (a few seconds).

```json
{"account_id": "HB90000001", "work_item_id": "WI-0348", "fields": {"first_name": "Maria", "household_size": 3, "annual_income": 38000},
 "result": {"did": "PROPOSED", "detail": "P-0344: FREE_CARE adjusting $6,200.00. Income is 139% of the poverty level, at or under 200%: free care."}}
```

`409` before the first live day; `400` with the helper's own message when the description can't make a valid patient. Requests in the text ("approve her") change nothing: the outcome comes from the screening code. `python3 data/tools/add_account.py --reset` empties `data/judge/`.

### `POST /corrections`

Body: `{"actor_id": "S-001", "account_id": "HB26109524", "correction": "She's on CalFresh, so she qualifies for free care.", "note": "optional"}`. Staff only (`403` otherwise). Saves a precedent; when the correction implies a rule the core can apply (enrollment in CalFresh or Medi-Cal means free care without income documents), it finds the similar past cases, backtests the rule on them and proposes a `NEW_RULE` to the director. Returns `{correction_id, precedent_id, similar_cases, rule_proposal_id, message}`.

When the director approves the rule (`POST /proposals/{id}/decision`), the accounts it now settles go back to work at once. A rejected rule is never proposed again. `GET /learned` lists `precedents` and `rules`, each rule with its `backtest` (`cases_checked`, `cases_changed`, `dollars_moved_cents`, `examples`) and its proposal.
