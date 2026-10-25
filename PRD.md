# Halcyon Bay: Product Requirements

Last updated Oct 25, 2026, 1:50 AM. Owner: Batyrkhan. This is the single source of truth for every teammate and every agent.

## In one line

An autonomous system of work that runs the patient billing office of a nonprofit hospital. It works every self-pay account every day, gets financial assistance right under federal and California law, learns the job from the office's own history, turns staff corrections into rules, and logs every step.

## The event

- Cal Hacks 13.0. Devpost deadline Sun Oct 25, 9:00 AM PT, and we submit by 8:45. Judging is 10:30 to 12:30, a 3-minute pitch plus a live demo. Judges may try their own scenario.
- Main target: Hyphenate, Autonomous Systems for Finance. Also entering: Anthropic (community benefit), Microsoft Built for the Real World, Cal Hacks social impact and overall, and CRS (we must make meaningful use of the CRS sandbox and show it live).

## The problem

Nonprofit hospitals must give free or discounted care to patients who qualify, and must follow strict rules before sending anyone to collections. Billing offices are short-staffed and the rules keep changing. California changed them again on Jan 1, 2025. Two things go wrong at once. Patients who qualify get denied or sent to collections, which breaks the law. Patients who can pay never get a payment plan, so the hospital loses money it should collect. Our line: the right money from the right people.

## The company

Halcyon Bay Community Hospital, a fictional 300-bed nonprofit hospital in California. The hospital, patients, accounts and documents are simulated. The rules and poverty levels are real.

## The seats

- It does the work of a billing specialist and a financial assistance screener.
- People stay in charge:
  - Financial counselor answers questions and approves small adjustments (up to $5,000)
  - Revenue cycle director approves new policies, large adjustments and collections referrals
  - Compliance officer approves anything about how the law applies, including reversing past decisions
- Why a CFO would hire it: it fills two seats, catches legal violations before they turn into penalties, and collects money through payment plans instead of writing it off.

## How Hyphenate judges

- Is it real enough? Would you hire it (make or break)? Did we see something new? Is there a wow moment?
- Their recipe: a system of work, not a system of record. Self-learning means it learns policies from history at onboarding, with evidence, approved by a person. Self-improving means corrections become precedent, then a general rule, backtested, then approved. Audit trail means "why?" is one query.
- Strong: an answer key and a score, a few roles done deep, asks at the right moment and handles a no, limits in code.
- Weak: a chatbot or one-shot extractor, happy path only, "the prompt tells it not to", memory that only lives in the context window.
- Precision on actions it takes alone must be near 100%. Everything else gets escalated.
- Submit: a demo video that opens with the wow moment, a live demo, one line on the seats, what is real vs simulated, the answer key and the score.

## How it works

1. Sync. Every simulated day, pull what's new from every source system into one shape with stable IDs. Sources disagree, so matching patients across systems is part of the job.
2. Work items. Every account that needs action gets one. States: NEW, SCREENING, NEEDS_INFO or PROPOSED, APPROVED or REJECTED, POSTED. Only the gateway moves an item to POSTED. Mistakes are fixed with a REVERSAL, never by editing or deleting history.
3. Proposals. Free care, discount, payment plan, collections referral, pause collections, block an agency action, merge duplicate accounts, reverse a past decision.
4. Permissions. One can() check (actor, action, resource) before every action.
   - Sync job creates and updates work items
   - AI agent reads everything, proposes and asks. It may pause collections and block illegal agency actions on its own, because stopping a collection is always safe.
   - Counselor, director and compliance officer approve or reject within their limits
   - The gateway is the only thing that posts changes
   - Whoever proposes something can never approve it, and nobody can approve their own account
5. Self-learning. At onboarding it reads 18 months of history and learns how the office decides, with evidence counts. Every learned pattern is checked against current law and policy first. Patterns that break the law get flagged, not learned. That is the day-one discovery.
6. Self-improving. A staff correction becomes a precedent. The AI finds similar past cases, proposes a general rule, backtests it on history (cases changed, dollars moved) and asks the director. A rejected proposal is stored and never proposed again.
7. Asking. When documents disagree, income sits right at a cutoff, or something is missing, it asks the right person instead of guessing.
8. Audit log. An append-only record of every action and every attempt, including denied ones, with who, what, when, why and the evidence.
9. Limits in code. Poverty-level math, deadlines and permission checks are plain code. Claude reads messy documents and notes and handles unclear cases. A prompt never enforces a limit. Learned policies and precedents are stored, not kept in a prompt.

## The rules (real)

Federal, IRS 501(r), for nonprofit hospitals
- A written financial assistance policy, and reasonable efforts to check if a patient qualifies before any extraordinary collection action (selling the debt, credit reporting, lawsuits, liens)
- No extraordinary collection action for 120 days after the first bill after discharge, and 30 days written notice before one
- Applications accepted for at least 240 days after the first bill

California
- AB 1020 (2022): patients up to 400% of the poverty level qualify for free or discounted care. No lawsuits or debt sales until 180 days after the first bill.
- AB 2297 (Jan 1, 2025): savings and other monetary assets can't be counted, there can be no application deadline, and other proof of income must be accepted
- SB 1061 (Jan 1, 2025): medical debt can't be reported to credit bureaus

Poverty level (HHS, 48 states), by year of the decision
- 2025: $15,650 for 1 person, plus $5,500 per extra person
- 2026: $15,960 for 1 person, plus $5,680 per extra person (4 people: $33,000)

## The hospital's policy (fictional)

- Free care up to 200% of the poverty level. Discount from 200% to 400%, where the patient pays 30% of the billed amount (our stand-in for the Medicare rate). Above 400%, payment plan only.
- Patients on Medi-Cal or who are homeless get free care without income documents.
- An approval covers every visit for 12 months.
- Old version (until Jun 30, 2025): savings over $10,000 disqualify, and applications are only accepted within 240 days of the first bill. The current version (from Jul 1, 2025) dropped both and accepts other proof of income when there are no pay stubs.
- Neither version mentions CalFresh. The AI learns that rule from a counselor's correction during the demo.

## The simulated world

- History from Jan 1, 2025 to Jun 30, 2026. Live from Jul 1 to Sep 30, 2026, replayed one day at a time. About 2,000 accounts.
- Separate source systems with their own IDs that don't always agree: billing system, financial assistance system, collection agency file, income documents (pay stubs, letters, bank statements), staff list, and the policy in its old and current versions. Realistic and messy, like real exports.
- The same data on every run, and the generated data is committed.
- Planted on purpose. Never labeled in the data, because the core has to find them on its own:
  1. About 30 denials after Jan 1, 2025 for applying late or having savings, from patients who qualify on income, mixed in with legal denials. They break AB 2297 even in the months the old policy was still in effect.
  2. A messy CalFresh history: a few approved without income documents, a few stuck in needs info, about 10 past accounts a CalFresh rule would change, and at least 2 live CalFresh patients with no income documents
  3. The usual mess: duplicate patients under two account numbers, names and addresses that don't match between systems, missing documents (some with other proof instead), payment plans that stopped, and a March 2026 approval that should cover a June 2026 visit
  4. Agency requests to report accounts to credit bureaus
  5. Attacks: a pay stub with hidden instructions to approve 100% charity, and a live account where the patient is a staff member who can approve accounts
  6. Live accounts with no income documents where a discount is tempting, and truly unclear cases that need a person
- Answer key in data/answer_key/: the right outcome, dollars and a one-line reason for every live account, plus every planted case and its fix. The core never reads it. Only the score script does.
- A helper that adds one new account from given details, for the judge box.
- Files and fields are described in data/FORMAT.md.

## The screens

Judges need to see:
- the accounts the AI is working and where each one stands
- any account's full story: what every system says, what the AI proposed and why, and who approved it
- what the AI learned from history and from corrections, with the evidence and backtest results
- the audit log, including blocked actions, where asking why about any account is one search
- a live score, and the day-one discovery on its own clear screen
- a box where a judge types a patient in plain English and watches it get processed

Switching between counselor, director and compliance officer must be quick, because we approve and reject live. Style: minimal, big type, one idea per screen, lots of space, no crowded dashboards. It has to look clean in a screen recording.

## The demo (3 minutes)

1. Day one: it learns from 18 months of history and finds about 30 patients denied illegally under rules that changed in January 2025. It asks the compliance officer and proposes reversals with dollar amounts.
2. A live day: clear cases handled alone, unclear ones sent to the right person.
3. Self-improving: a counselor corrects a CalFresh case, it becomes a rule, the backtest shows what it changes, the director approves.
4. Handling a no: the director rejects discounts without income documents, and it never proposes that again.
5. Attacks: the hidden instructions are ignored and logged, a staff member can't approve their own account, and the AI's own attempt to post or send to collections is denied by the gateway.
6. A judge's own patient, typed in plain English, processed live.
7. Audit: "why did this happen?" answered in one query.
8. Score: precision, share handled automatically, dollars moved to charity, dollars collected through payment plans, violations prevented.

Pitch phrases for Hyphenate, each shown live: system of work, learns the job from history, every correction becomes precedent, why is one query, only the gateway posts. Plain words for everyone else.

## Who owns what

| Area | Owner | Folder |
|---|---|---|
| Sync, work items, permissions, gateway, audit log, agent, learning, score script, CRS calls | Batyrkhan | core/ |
| Simulated world, answer key, data/FORMAT.md | Teammate 2 | data/ |
| Screens | Teammate 2 | ui/ |
| Pitch, slides, Devpost, demo video, judge scenarios, CRS and Anthropic checks | Teammate 3 | docs/ |
| PRD.md, CLAUDE.md, README.md | Batyrkhan (Teammate 3 writes the final README) | root |

Contracts between parts
- data to core: data/FORMAT.md. Teammate 2 writes it, and changes need Batyrkhan's ok.
- core to ui: core/INTERFACE.md, how the UI reads state and sends approvals. Batyrkhan writes it by 3:20, and changes need Teammate 2's ok.
- Judge box: the UI sends plain English, and the core turns it into a new account and works it live.

How not to conflict
- Only edit your own folder. If something elsewhere needs to change, tell your person so they can ask the owner.
- Each owner picks the tech for their own part. The core and UI meet through core/INTERFACE.md.
- Run git pull --rebase before every push, and push small and often.
- Never commit .env or keys, and never add Claude as a co-author.

## Timeline

- 2:00: data/FORMAT.md pushed and agreed
- 2:40: first data batch, and the core starts loading it
- 3:20: full data, and core/INTERFACE.md ready
- 3:45: Checkpoint 1, one account flows end to end and shows in the UI
- 5:00: Devpost draft submitted
- 5:30: Checkpoint 2, the full demo flow works
- 6:30: code freeze, bug fixes only, record the demo
- 8:00: everyone at the venue. 8:45: final submit. 10:30: judging.

If behind at 5:30, cut in this order: CRS, visual polish, the judge box. Never cut the day-one discovery, the gateway denial or the audit query.

## Hard rules

- Synthetic data only. Never a real patient, a real hospital or real personal data.
- The AI never denies care or cancels a bill on its own.
- Credit and income data from CRS is used only to grant help, never to deny it.
- Insurance claims and denials are out of scope. We only handle what patients owe after insurance.

## Open questions

- CRS: which products our sandbox has (Teammate 3). Plan A is income verification to qualify patients with no documents. Plan B is identity verification to catch duplicate accounts.
- Anthropic prize: how to enter (Teammate 3, asking in #0-ask-directors).
