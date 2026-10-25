// Shapes from core/INTERFACE.md. "Live now" types match core/api.py exactly.
// "Coming" types are what the UI assumes until the core ships them (see ui/NOTES_FOR_CORE.md).

export type StaffRole = 'counselor' | 'director' | 'compliance';
export type Role = StaffRole | 'sync' | 'agent' | 'gateway';

export const WORK_STATES = ['NEW', 'SCREENING', 'NEEDS_INFO', 'PROPOSED', 'APPROVED', 'REJECTED', 'POSTED'] as const;
export type WorkState = (typeof WORK_STATES)[number];

export type ProposalKind =
  | 'FREE_CARE'
  | 'DISCOUNT'
  | 'PAYMENT_PLAN'
  | 'COLLECTIONS_REFERRAL'
  | 'PAUSE_COLLECTIONS'
  | 'BLOCK_AGENCY_ACTION'
  | 'MERGE_ACCOUNTS'
  | 'REVERSAL'
  | 'NEW_RULE';

export type ProposalStatus = 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'POSTED';

export interface CoreState {
  today: string;
  work_items_by_state: Record<WorkState, number>;
  open_proposals: number;
  open_questions: number;
}

export interface Actor {
  id: string;
  name: string;
  role: Role;
}

export interface WorkItem {
  id: string;
  account_id: string;
  state: WorkState;
  reason: string;
  opened_on: string;
  updated_on: string;
  patient_name?: string | null;
  billed_cents?: number | null;
}

export type Evidence = Record<string, unknown>;

export interface Proposal {
  id: string;
  work_item_id: string | null;
  account_id: string | null;
  kind: ProposalKind;
  amount_cents: number;
  rationale: string;
  evidence: Evidence[];
  pattern: string | null;
  legal_question: boolean;
  reverses: string | null;
  status: ProposalStatus;
  proposed_by: string;
  proposed_on: string;
  decided_by: string | null;
  decided_on: string | null;
  decision_note: string | null;
}

export interface Question {
  id: string;
  work_item_id: string;
  account_id: string;
  to_role: Role;
  question: string;
  asked_by: string;
  asked_on: string;
  answer: string | null;
  answered_by: string | null;
  answered_on: string | null;
}

export interface Inbox {
  actor: Actor;
  proposals: Proposal[];
  questions: Question[];
}

export interface LedgerRow {
  seq: number;
  proposal_id: string;
  account_id: string | null;
  kind: ProposalKind;
  amount_cents: number;
  reverses: string | null;
  posted_on: string;
}

export interface AuditRow {
  seq: number;
  logged_at: string;
  sim_day: string;
  actor_id: string;
  actor_role: Role;
  action: string;
  target: string | null;
  account_id: string | null;
  allowed: boolean;
  reason: string;
  detail: Record<string, unknown>;
}

export interface Account {
  id: string;
  patient_id: string | null;
  patient_name: string | null;
  billed_cents: number;
  first_bill_on: string | null;
  collections_paused: boolean;
  sources: Record<string, unknown>;
}

export interface AccountStory {
  account: Account;
  work_items: WorkItem[];
  proposals: Proposal[];
  questions: Question[];
  ledger: LedgerRow[];
  audit: AuditRow[];
}

export interface AuditQuery {
  account_id?: string;
  actor_id?: string;
  allowed?: boolean;
  q?: string;
  limit?: number;
}

// ---------- Coming ----------

export interface DiscoveryFinding {
  id: string;
  kind: 'ILLEGAL_DENIAL' | 'ILLEGAL_REASON_SAME_OUTCOME';
  application_id: string;
  account_ids: string[];
  patient_name: string;
  decision_date: string;
  decided_by: string | null;
  stated_reason: string;
  reason_code: string;
  fpl_pct: number | null;
  correct_outcome: string;
  law: string;
  law_text: string;
  adjustment_cents: number;
  refund_cents: number;
  proposal: Proposal | null;
}

export interface Discovery {
  as_of: string;
  history: { from: string; to: string; applications: number; accounts: number };
  law: { id: string; name: string; effective: string; text: string };
  total_cents: number;
  findings: DiscoveryFinding[];
  patterns_learned: number;
  patterns_flagged: number;
}

export interface LearnedPattern {
  id: string;
  text: string;
  evidence_count: number;
  legal: boolean;
  status: 'LEARNED' | 'FLAGGED';
  law?: string | null;
  law_text?: string | null;
  note?: string | null;
}

export interface Precedent {
  id: string;
  correction_id?: string | null;
  account_id: string;
  patient_name?: string | null;
  by: string;
  on: string;
  correction: string;
  note?: string | null;
  similar_cases: number;
  rule_id?: string | null;
}

export interface BacktestExample {
  application_id: string;
  patient_name?: string | null;
  before: string;
  after: string;
  dollars_cents: number;
}

export interface Backtest {
  cases_checked: number;
  cases_changed: number;
  dollars_moved_cents: number;
  examples?: BacktestExample[];
}

export interface LearnedRule {
  id: string;
  text: string;
  pattern: string;
  from_precedent?: string | null;
  backtest: Backtest;
  status: ProposalStatus;
  proposal: Proposal | null;
  decided_by?: string | null;
  decided_on?: string | null;
  decision_note?: string | null;
}

export interface RejectedPattern {
  pattern: string;
  text?: string | null;
  proposal_id: string;
  rejected_by: string;
  rejected_on: string;
  note: string | null;
  blocked_since?: number;
}

export interface Learned {
  patterns: LearnedPattern[];
  precedents: Precedent[];
  rules: LearnedRule[];
  rejected: RejectedPattern[];
}

export interface CorrectionIn {
  actor_id: string;
  account_id: string;
  correction: string;
  note: string;
}

export interface CorrectionResult {
  correction_id: string;
  precedent_id: string;
  similar_cases: number;
  rule_proposal_id: string | null;
  message?: string | null;
}

export interface Score {
  as_of: string;
  precision: { value: number; correct: number; total: number };
  auto_share: { value: number; auto: number; total: number };
  charity_cents: number;
  payment_plan_collected_cents: number;
  violations_prevented: { count: number; by_law?: Record<string, number> };
  answer_key?: { accounts_scored: number; matched: number } | null;
}

export interface JudgeBoxResult {
  account_id: string;
  work_item_id?: string | null;
}
