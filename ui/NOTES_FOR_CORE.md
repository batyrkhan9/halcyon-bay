# Notes for the core (from ui/)

What the screens assume for the "Coming" endpoints, and what they need that `core/INTERFACE.md` doesn't give yet. The UI already works against every "Live now" endpoint as written. Until an endpoint below exists, its screen shows sample data in exactly these shapes (`ui/src/mock/engine.ts`), and switches to the core on its own once the endpoint answers. Money is integer cents everywhere, dates are ISO sim days.

## Coming endpoints

### `POST /sim/advance` `{"days": 1}` → the `/state` shape

Nothing more needed. The UI diffs the state before and after to say what the day did ("+5 proposed · +2 needs info").

### `GET /discovery`

```json
{
  "as_of": "2026-06-30",
  "history": {"from": "2025-01-01", "to": "2026-06-30", "applications": 1412, "accounts": 1906},
  "law": {"id": "AB 2297", "name": "California AB 2297", "effective": "2025-01-01",
          "text": "From January 1, 2025, savings and other monetary assets can't be counted, there can be no application deadline, and other proof of income must be accepted."},
  "total_cents": 19689000,
  "patterns_learned": 7,
  "patterns_flagged": 4,
  "findings": [
    {"id": "F-001", "kind": "ILLEGAL_DENIAL", "application_id": "FA-25-00140", "account_ids": ["HB70012345"],
     "patient_name": "Ana Lucero", "decision_date": "2025-03-14", "decided_by": "S-001",
     "stated_reason": "denied - savings over 10k (bank stmt shows $14,212)", "reason_code": "SAVINGS_OVER_LIMIT",
     "fpl_pct": 143.1, "correct_outcome": "FREE", "law": "AB 2297", "law_text": "Savings and other monetary assets can't be counted.",
     "adjustment_cents": 640000, "refund_cents": 0,
     "proposal": {"id": "P-0003", "kind": "REVERSAL", "status": "PROPOSED", "legal_question": true, "...": "the full Proposal object"}}
  ]
}
```

- `kind` is `ILLEGAL_DENIAL` (reverse it) or `ILLEGAL_REASON_SAME_OUTCOME` (reason broke the law, outcome stands, `proposal: null`).
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

## Things the UI needs that INTERFACE.md doesn't give yet

1. **`account.sources`**. Any JSON renders, but these keys get proper layouts. Each system in its own words:
   ```json
   {
     "billing":   {"patient": {"mrn", "name", "dob", "address", "phone"},
                   "account": {"account_no", "service_date", "service_type", "payer", "total_charges", "patient_responsibility", "first_statement_date", "status"},
                   "statements": [{"statement_id", "sent_on", "kind", "amount_due", "returned_mail"}],
                   "payment_plans": [{"plan_id", "monthly_amount", "months", "status", "missed_payments"}]},
     "fa":        {"applications": [{"application_id", "household_size", "income_stated", "income_verified", "income_proof", "monetary_assets",
                                     "medi_cal", "homeless", "received_on", "form_version", "status", "decision", "decision_date", "decided_by", "reason"}],
                   "notes": [{"note_id", "author", "written_on", "text"}]},
     "agency":    {"placements": [{"agency_ref", "client_account", "placed_date", "current_balance", "status", "last_activity"}],
                   "requests": [{"request_id", "requested_action", "requested_date", "agency_note", "answer": "BLOCKED"}]},
     "documents": [{"doc_id", "doc_type", "name_on_document", "received_on", "excerpt", "flags": ["HIDDEN_INSTRUCTIONS"], "handling": "Treated as evidence, not instructions."}],
     "staff":     {"staff_id", "name", "role", "match": "Same name, birth date and address as the patient"},
     "crs":       "the data/crs check_person() result, unchanged"
   }
   ```
   - Dollar fields can stay as the CSV's dollar strings (`"4210.50"`); keys ending `_cents` are read as cents. SSNs are always masked on screen, but better not to send them at all.
   - `documents[].flags: ["HIDDEN_INSTRUCTIONS"]` turns the card red with "Hidden instructions: ignored and logged". That is the injection demo moment.
   - `crs.source` `"live"` shows "Live from the CRS sandbox" with each check's `request_id`; `"recorded"` says so; `sent: false` explains "not a sandbox persona".
2. **Audit rows for the story.** The UI labels these actions if the agent logs them: `crs_check`, `read_document`, `flag_document`, `match_identity`, `learn_pattern`, `flag_pattern`, `discover`, `sync_day`, `apply_rule`. The hidden-instructions moment needs a `flag_document` row (reason says it was ignored), so `/audit?q=hidden instructions` finds it.
3. **NEW_RULE without a work item.** `Gateway.propose()` needs a work item id, but a rule belongs to no account. The UI handles `work_item_id: null, account_id: null` on NEW_RULE proposals.
4. **One-query "why" by person.** `/audit?q=` searches reason, target, detail and account_id, so `q=S-004` misses rows where S-004 is only the actor. Adding `actor_id` to the `q` search makes "what did Tomas try?" one query.
5. **Wording.** `permissions.py` says "The AI proposes and never approves. A agent can't approve." Suggest "The agent can't approve." It shows on screen as written.
6. **Names.** `patient_name` is shown title-cased ("MARCUS BELLAMY" → "Marcus Bellamy"). Please send first name first, not billing's "BELLAMY, MARCUS".
