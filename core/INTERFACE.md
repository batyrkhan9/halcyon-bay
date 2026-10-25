# Core to UI interface

How the UI reads state and sends approvals. Batyrkhan writes this file; changes need Noriaki's ok.

Status: draft. Everything under "Live now" works today against a small fake office. Everything under "Coming" is the planned shape, and may still change before 3:20.

## Run it

From the repo root:

```bash
uv venv core/.venv --python 3.12
uv pip install --python core/.venv/bin/python -r core/requirements.txt
core/.venv/bin/python -m core.dev_seed
core/.venv/bin/uvicorn core.api:main --factory --port 8000
```

The API is at http://localhost:8000, and every endpoint is listed at http://localhost:8000/docs. `core.dev_seed` fills `core/state/halcyon.db` with a few made-up accounts so you can build screens before the real data lands. Set `HALCYON_DB` to use another file.

## Conventions

- JSON in and out. CORS is open, so any local port can call it.
- Money is always integer cents: `amount_cents`, `billed_cents`. Show `123456` as $1,234.56.
- Dates are ISO strings in simulated time (`2026-07-01`). `/state` gives today's simulated date.
- The UI acts as a person by sending their `actor_id` (from `/actors`). There is no login.
- A refused action returns `403` with `{"denied": true, "reason": "..."}`. Show the reason; it is written for people. The refusal is already in the audit log.
- An unknown ID returns `404`.

## Roles and states

Roles: `counselor`, `director`, `compliance` (people) and `sync`, `agent`, `gateway` (the system).

Work item states: `NEW`, `SCREENING`, `NEEDS_INFO`, `PROPOSED`, `APPROVED`, `REJECTED`, `POSTED`.

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
  "work_items_by_state": {"NEW": 0, "SCREENING": 0, "NEEDS_INFO": 2, "PROPOSED": 5, "APPROVED": 0, "REJECTED": 0, "POSTED": 0},
  "open_proposals": 5,
  "open_questions": 2
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

Body: `{"actor_id": "S-001", "answer": "Use the employer letter"}`. Returns the updated Question.

### `GET /accounts/{account_id}`

An account's full story in one call.

```json
{
  "account": {"id": "ACC-1005", "patient_id": "PAT-1005", "patient_name": "Ruth Calloway", "billed_cents": 650000,
              "first_bill_on": "2026-03-02", "collections_paused": true, "sources": {}},
  "work_items": [WorkItem],
  "proposals": [Proposal],
  "questions": [Question],
  "ledger": [{"seq": 1, "proposal_id": "P-0005", "account_id": "ACC-1005", "kind": "BLOCK_AGENCY_ACTION",
              "amount_cents": 0, "reverses": null, "posted_on": "2026-07-01"}],
  "audit": [AuditRow]
}
```

`sources` will hold what each source system says about the account once sync is built.

### `GET /audit?account_id=&actor_id=&allowed=&q=&limit=200`

Every filter is optional. Newest first. `allowed=false` gives only blocked actions. `q` searches the reason, target, details and account ID, so "why did this happen?" is one search.

### Objects

Proposal:

```json
{"id": "P-0002", "work_item_id": "WI-0002", "account_id": "ACC-1002", "kind": "DISCOUNT", "amount_cents": 840000,
 "rationale": "Income is 300% of the poverty level, between 200% and 400%: patient pays 30% of the bill.",
 "evidence": [{"source": "seed", "household": 4, "income": 99000, "proof": "PAY_STUBS"}],
 "pattern": null, "legal_question": false, "reverses": null, "status": "PROPOSED",
 "proposed_by": "agent", "proposed_on": "2026-07-01", "decided_by": null, "decided_on": null, "decision_note": null}
```

`amount_cents` is the change to what the patient owes: for a discount, the part forgiven.

Question:

```json
{"id": "Q-0001", "work_item_id": "WI-0003", "account_id": "ACC-1003", "to_role": "counselor",
 "question": "Income is 200.1% of the poverty level, right at the 200% cutoff. Please confirm the income.",
 "asked_by": "agent", "asked_on": "2026-07-01", "answer": null, "answered_by": null, "answered_on": null}
```

AuditRow:

```json
{"seq": 25, "logged_at": "2026-10-25T09:12:03+00:00", "sim_day": "2026-07-01", "actor_id": "agent", "actor_role": "agent",
 "action": "post", "target": "P-0001", "account_id": "ACC-1001", "allowed": false,
 "reason": "Only the gateway posts changes.", "detail": {}}
```

## Coming

Planned shapes. They will be built in this order.

- `POST /sim/advance` with `{"days": 1}`: run the next simulated day (sync, then the agent works every item). Returns `/state`.
- `GET /discovery`: the day-one discovery. Patterns learned from 18 months of history, and the ones flagged as illegal, with the affected accounts, the law each breaks and the dollars involved.
- `GET /learned`: learned policies and rules from corrections, each with evidence counts, the backtest (cases changed, dollars moved) and its status.
- `POST /corrections` with `{"actor_id", "account_id", "correction", "note"}`: a staff correction that becomes a precedent.
- `GET /score`: precision, share handled automatically, dollars moved to charity, dollars collected through payment plans and violations prevented, scored against the answer key.
- `POST /judge-box` with `{"text": "..."}`: a patient described in plain English becomes a new account and is worked live. Returns the account ID to open.
