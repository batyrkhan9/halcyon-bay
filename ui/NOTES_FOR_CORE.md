# Notes for the core (from ui/)

What the screens assume for the "Coming" endpoints, and what they need that `core/INTERFACE.md` doesn't give yet. The UI already works against every "Live now" endpoint as written. Until an endpoint below exists, its screen shows sample data in exactly these shapes (`ui/src/mock/engine.ts`), and switches to the core on its own once the endpoint answers. Money is integer cents everywhere, dates are ISO sim days.

## Coming endpoints

### `POST /sim/advance` `{"days": 1}` → the `/state` shape

Nothing more needed. The UI diffs the state before and after to say what the day did ("+5 proposed · +2 needs info").

### `GET /discovery`

```json
{
  "as_of": "2026-06-30",
  "history": {"from": "2025-01-01", "to": "2026-06-30", "applications": 979, "accounts": 1710},
  "law": {"id": "AB 2297", "name": "California AB 2297", "effective": "2025-01-01",
          "text": "From January 1, 2025, savings and other monetary assets can't be counted, there can be no application deadline, and other proof of income must be accepted."},
  "total_cents": 22777845,
  "patterns_learned": 8,
  "patterns_flagged": 3,
  "findings": [
    {"id": "F-001", "kind": "ILLEGAL_DENIAL", "application_id": "FA-24-04117", "account_ids": ["HB24310922"],
     "patient_name": "Brianna Novak", "decision_date": "2025-01-12", "decided_by": "S-006",
     "stated_reason": "over asset limit (chk/sav approx 47k)", "reason_code": "SAVINGS_OVER_LIMIT",
     "fpl_pct": 378.9, "correct_outcome": "DISCOUNT", "law": "AB 2297", "law_text": "...",
     "adjustment_cents": 411446, "refund_cents": 411446,
     "proposal": {"id": "P-0003", "kind": "REVERSAL", "status": "PROPOSED", "legal_question": true, "...": "the full Proposal object"}}
  ]
}
```

- `kind` is `ILLEGAL_DENIAL` (reverse it) or `ILLEGAL_REASON_SAME_OUTCOME` (reason broke the law, outcome stands, `proposal: null`). The headline counts the `law: "AB 2297"` denials (rules that changed in January 2025) with adjustment + refund; the screen mentions the AB 1020 ones ("over income" at or under 400%) separately, so set `law` per finding.
- Please embed the whole REVERSAL Proposal in `proposal`, so the compliance officer approves from this screen through `POST /proposals/{id}/decision` (the "Approve all" button sends one decision per proposal).

### `GET /learned`

```json
{
  "patterns": [
    {"id": "LP-01", "text": "Medi-Cal enrollees get free care without income documents", "evidence_count": 211, "legal": true, "status": "LEARNED"},
    {"id": "LP-08", "text": "Savings over $10,000 disqualify", "evidence_count": 19, "legal": false, "status": "FLAGGED",
     "law": "AB 2297", "law_text": "Savings and other monetary assets can't be counted.", "note": "optional"}
  ],
  "precedents": [
    {"id": "PR-01", "correction_id": "C-0001", "account_id": "HB70031877", "patient_name": "IMANI BROOKS", "by": "S-001", "on": "2026-07-01",
     "correction": "CalFresh enrollment means household income is at or under 200%. Give free care without income documents.",
     "note": "The county benefit letter is enough proof.", "similar_cases": 10, "rule_id": "R-01"}
  ],
  "rules": [
    {"id": "R-01", "text": "Enrolled in CalFresh: free care without income documents", "pattern": "CALFRESH_FREE_CARE", "from_precedent": "PR-01",
     "backtest": {"cases_checked": 1412, "cases_changed": 10, "dollars_moved_cents": 4312000,
                  "examples": [{"application_id": "FA-25-00731", "patient_name": "Rosario Delgado", "before": "Needs info (stuck 94 days)", "after": "Free care", "dollars_cents": 521000}]},
     "status": "PROPOSED", "proposal": {"id": "P-0042", "kind": "NEW_RULE", "...": "the full Proposal object"},
     "decided_by": null, "decided_on": null, "decision_note": null}
  ],
  "rejected": [
    {"pattern": "DISCOUNT_WITHOUT_INCOME_DOCS", "text": "Discounts without income documents", "proposal_id": "P-0035",
     "rejected_by": "S-002", "rejected_on": "2026-07-01", "note": "A discount needs proof of income.", "blocked_since": 2}
  ]
}
```

- `rules[].status` mirrors the NEW_RULE proposal's status. The director approves or rejects through `POST /proposals/{id}/decision`.
- `rejected` is the `rejected_patterns` table plus `text` (words for people) and `blocked_since` (how many later proposals the gateway refused with "Not proposed again").

### `POST /corrections` `{"actor_id", "account_id", "correction", "note"}`

```json
{"correction_id": "C-0002", "precedent_id": "PR-02", "similar_cases": 4, "rule_proposal_id": "P-0051",
 "message": "Saved as precedent PR-02. It found 4 similar past cases and proposed rule R-03 for the director."}
```

`rule_proposal_id` is null when no rule is proposed. `message` is optional; the UI writes its own line without it. A non-staff actor should get the usual 403.

### `GET /score`

```json
{"as_of": "2026-07-14",
 "precision": {"value": 0.996, "correct": 248, "total": 249},
 "auto_share": {"value": 0.71, "auto": 412, "total": 580},
 "charity_cents": 128450000,
 "payment_plan_collected_cents": 1834000,
 "violations_prevented": {"count": 47, "by_law": {"SB 1061 credit reports blocked": 12, "AB 2297 denials reversed": 31, "Gateway refusals": 4}},
 "answer_key": {"accounts_scored": 580, "matched": 571}}
```

`value` may be 0..1 or a percent. `by_law` keys are shown as written, so make them readable.

### `POST /judge-box` `{"text": "..."}`

```json
{"account_id": "HB70090001", "work_item_id": "WI-0412"}
```

Please return as soon as the account and work item exist, then work it in the background. The UI opens `/accounts/{id}` and polls it every second, so each audit row appears as the agent writes it. If the call blocks until the agent is done, it still works, but the judge sees the result at once instead of the steps.

## Supported now from `origin/core` (db1e42d)

The UI already handles these and lights up as soon as the branch merges; against today's main core it simply doesn't show them (`/work` is detected through `/openapi.json`).

- `POST /work-items/{id}/work`: "Work it now" on the account story for NEW/SCREENING items, called automatically after a person answers a question, and on the judge box's new work item. A 503 shows as a calm "The agent can't work right now" with your `detail`.
- `documents[]` (raw text in monospace, quoted evidence highlighted, hidden-instruction quotes in red) and `agency_requests[]` (OPEN/BLOCKED) on `GET /accounts/{id}`.
- Evidence `{fact, document_id, quote}` (fact, quote, link to the document), `pattern` and `subject` badges.
- Audit `read_case` (expandable: facts with quotes, "refused by code" with `why`, conflicts by `description`, missing) and `follow_hidden_instructions` (red "Hidden instructions ignored" row; `/audit?allowed=false` shows them).

## Still needed

1. **CRS on the account.** Please put the `data/crs` `check_person()` result, unchanged, in `account.sources.crs` (including `source: "live" | "recorded"`). The card says "Live from the CRS sandbox" only when `source` is `live`, "Recorded CRS sandbox answer" when `recorded`. A `crs_check` audit row makes "why are collections paused?" one search.
2. **`account.sources` from sync.** Any JSON renders; `billing`, `fa`, `agency`, `documents` and `staff` get proper layouts (shapes in the sample world: `ui/src/mock/real.json` is extracted from `data/` by `npm run extract-sample`).
3. **Judge box returns `work_item_id`.** The UI then opens the account and calls `/work` on it, so the judge watches it get read.
4. **NEW_RULE without a work item.** `Gateway.propose()` needs a work item, but a rule belongs to no account. The UI handles `work_item_id: null, account_id: null`.
5. **One-query "why" by person.** `/audit?q=` doesn't search `actor_id`, so `q=S-004` misses rows where S-004 is only the actor.
6. **Wording.** `permissions.py` still says "The AI proposes and never approves. A agent can't approve." Suggest "The agent can't approve."
7. **Names.** Send `patient_name` first name first ("Marcus Bellamy", not billing's "BELLAMY, MARCUS").
