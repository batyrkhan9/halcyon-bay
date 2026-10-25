// The SAMPLE world: a small in-memory Halcyon Bay office that answers every endpoint in
// core/INTERFACE.md, so the screens work with no core (VITE_MOCK=1) and the "Coming" screens
// have something real-looking until the core ships them. Everything here is synthetic.
//
// The permission checks below mirror core/permissions.py only so the sample world refuses the
// same things the real gateway refuses. In live mode the core decides; the UI never does.

import type {
  Account,
  AccountStory,
  Actor,
  AuditQuery,
  AuditRow,
  Backtest,
  CoreState,
  CorrectionIn,
  CorrectionResult,
  Discovery,
  DiscoveryFinding,
  Evidence,
  Inbox,
  JudgeBoxResult,
  Learned,
  LearnedPattern,
  LedgerRow,
  Precedent,
  Proposal,
  ProposalKind,
  ProposalStatus,
  Question,
  RejectedPattern,
  Role,
  Score,
  WorkItem,
  WorkState,
} from '../api/types';
import { WORK_STATES } from '../api/types';
import { Denied, HttpError } from '../api/errors';
import { parseJudgeText, povertyLine, screen, type Applicant } from './law';
import { seedWorld } from './seed';

const STAFF_ROLES: Role[] = ['counselor', 'director', 'compliance'];
const SAFE_KINDS: ProposalKind[] = ['PAUSE_COLLECTIONS', 'BLOCK_AGENCY_ACTION'];
const ADJUSTMENTS: ProposalKind[] = ['FREE_CARE', 'DISCOUNT', 'PAYMENT_PLAN', 'MERGE_ACCOUNTS'];
const DECIDES: Record<string, ProposalKind[]> = {
  counselor: ADJUSTMENTS,
  director: [...ADJUSTMENTS, 'COLLECTIONS_REFERRAL', 'NEW_RULE'],
  compliance: ['REVERSAL'],
};
const COUNSELOR_LIMIT_CENTS = 5_000_00;

const SYSTEM_ACTORS: Record<string, Actor> = {
  sync: { id: 'sync', name: 'Sync job', role: 'sync' },
  agent: { id: 'agent', name: 'AI agent', role: 'agent' },
  gateway: { id: 'gateway', name: 'Gateway', role: 'gateway' },
};

/** What the agent proposes once a person answers its question. */
export interface FollowUp {
  kind: ProposalKind;
  amount_cents: number;
  rationale: string;
  evidence?: Evidence[];
}

export interface MockQuestion extends Question {
  follow?: FollowUp | null;
}

export interface RuleRecord {
  id: string;
  text: string;
  pattern: string;
  from_precedent: string | null;
  backtest: Backtest;
  proposal_id: string;
}

export type FindingRecord = Omit<DiscoveryFinding, 'proposal'> & { proposal_id: string | null };

interface Decision {
  allowed: boolean;
  reason: string;
}

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

export function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return t.toISOString().slice(0, 10);
}

export function shortDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const usd = (cents: number) =>
  `$${(cents / 100).toLocaleString('en-US', { minimumFractionDigits: cents % 100 ? 2 : 0, maximumFractionDigits: 2 })}`;

export class MockOffice {
  today = '2026-07-01';
  staff: Actor[] = [];
  staffPatients: Record<string, string[]> = {};
  accounts = new Map<string, Account>();
  applicants = new Map<string, Applicant>();
  items: WorkItem[] = [];
  proposals: Proposal[] = [];
  questions: MockQuestion[] = [];
  ledger: LedgerRow[] = [];
  auditLog: AuditRow[] = [];
  rejected: RejectedPattern[] = [];
  findings: FindingRecord[] = [];
  patterns: LearnedPattern[] = [];
  precedents: Precedent[] = [];
  rules: RuleRecord[] = [];
  waiting = new Set<string>();
  pendingFollow = new Set<string>();
  history = { from: '2025-01-01', to: '2026-06-30', applications: 1412, accounts: 1906 };
  planCollectedCents = 18_340_00;
  rand: () => number = mulberry32(20261025);
  nameSeq = 0;
  judgeSeq = 0;
  seeding = true;

  private seqs: Record<string, number> = {};
  private auditSeq = 0;
  private clock = Date.now() - 48 * 60 * 1000;
  private listeners = new Set<() => void>();

  constructor() {
    seedWorld(this);
    this.seeding = false;
  }

  // ---------- plumbing ----------

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  emit() {
    if (!this.seeding) this.listeners.forEach((fn) => fn());
  }

  next(prefix: string, width = 4): string {
    const n = (this.seqs[prefix] ?? 0) + 1;
    this.seqs[prefix] = n;
    return `${prefix}-${String(n).padStart(width, '0')}`;
  }

  actorOf(id: string): Actor {
    const a = SYSTEM_ACTORS[id] ?? this.staff.find((s) => s.id === id);
    if (!a) throw new HttpError(404, `No actor ${id}`);
    return a;
  }

  log(
    actorId: string,
    action: string,
    o: { target?: string | null; account_id?: string | null; allowed?: boolean; reason: string; detail?: Record<string, unknown> },
  ): AuditRow {
    const actor = this.actorOf(actorId);
    this.clock = this.seeding ? this.clock + 900 + Math.floor(this.rand() * 2600) : Date.now();
    const row: AuditRow = {
      seq: ++this.auditSeq,
      logged_at: new Date(this.clock).toISOString().replace(/\.\d{3}Z$/, '+00:00'),
      sim_day: this.today,
      actor_id: actor.id,
      actor_role: actor.role,
      action,
      target: o.target ?? null,
      account_id: o.account_id ?? null,
      allowed: o.allowed ?? true,
      reason: o.reason,
      detail: o.detail ?? {},
    };
    this.auditLog.push(row);
    return row;
  }

  refuse(actorId: string, action: string, target: string | null, accountId: string | null, reason: string, detail?: Record<string, unknown>): never {
    this.log(actorId, action, { target, account_id: accountId, allowed: false, reason, detail });
    this.emit();
    throw new Denied(reason);
  }

  // ---------- the office's moves (mirror core/gateway.py) ----------

  addAccount(a: Omit<Account, 'collections_paused'> & { collections_paused?: boolean }, applicant?: Applicant) {
    this.accounts.set(a.id, { collections_paused: false, ...a });
    if (applicant) this.applicants.set(a.id, applicant);
  }

  item(id: string): WorkItem | undefined {
    return this.items.find((i) => i.id === id);
  }

  setState(item: WorkItem, state: WorkState) {
    item.state = state;
    item.updated_on = this.today;
  }

  openItem(accountId: string, reason: string): string {
    const id = this.next('WI');
    this.items.push({ id, account_id: accountId, state: 'NEW', reason, opened_on: this.today, updated_on: this.today });
    this.log('sync', 'open_work_item', { target: id, account_id: accountId, reason });
    return id;
  }

  move(itemId: string, state: WorkState, why: string) {
    const item = this.item(itemId);
    if (!item) return;
    const from = item.state;
    this.setState(item, state);
    this.log('agent', 'move_work_item', { target: itemId, account_id: item.account_id, reason: why, detail: { from, to: state } });
  }

  propose(
    itemId: string | null,
    kind: ProposalKind,
    amount_cents: number,
    rationale: string,
    o: { evidence?: Evidence[]; pattern?: string | null; legal_question?: boolean; reverses?: string | null; account_id?: string | null } = {},
  ): string | null {
    const item = itemId ? this.item(itemId) : undefined;
    const accountId = item?.account_id ?? o.account_id ?? null;
    const detail = { kind, amount_cents, rationale, pattern: o.pattern ?? null };
    const earlier = o.pattern ? this.rejected.find((r) => r.pattern === o.pattern) : undefined;
    if (earlier) {
      this.log('agent', 'propose', {
        target: itemId ?? `account:${accountId}`,
        account_id: accountId,
        allowed: false,
        reason: `Not proposed again: ${earlier.rejected_by} rejected '${earlier.pattern}' on ${earlier.rejected_on} (${earlier.note || 'no note'}).`,
        detail,
      });
      return null;
    }
    const id = this.next('P');
    this.proposals.push({
      id,
      work_item_id: itemId,
      account_id: accountId,
      kind,
      amount_cents,
      rationale,
      evidence: o.evidence ?? [],
      pattern: o.pattern ?? null,
      legal_question: o.legal_question ?? false,
      reverses: o.reverses ?? null,
      status: 'PROPOSED',
      proposed_by: 'agent',
      proposed_on: this.today,
      decided_by: null,
      decided_on: null,
      decision_note: null,
    });
    if (item) this.setState(item, 'PROPOSED');
    this.log('agent', 'propose', { target: id, account_id: accountId, reason: rationale, detail: { ...detail, evidence: o.evidence ?? [] } });
    return id;
  }

  ask(itemId: string, toRole: Role, question: string, follow: FollowUp | null = null): string {
    const item = this.item(itemId);
    const id = this.next('Q');
    const accountId = item?.account_id ?? '';
    this.questions.push({
      id,
      work_item_id: itemId,
      account_id: accountId,
      to_role: toRole,
      question,
      asked_by: 'agent',
      asked_on: this.today,
      answer: null,
      answered_by: null,
      answered_on: null,
      follow,
    });
    if (item && item.state === 'SCREENING') this.setState(item, 'NEEDS_INFO');
    this.log('agent', 'ask', { target: id, account_id: accountId, reason: question, detail: { to_role: toRole } });
    return id;
  }

  actSafe(accountId: string, kind: ProposalKind, rationale: string, evidence: Evidence[] = [], itemId: string | null = null): string {
    const id = this.next('P');
    const reason = 'Stopping a collection is always safe, so it needs no approval.';
    this.proposals.push({
      id,
      work_item_id: itemId,
      account_id: accountId,
      kind,
      amount_cents: 0,
      rationale,
      evidence,
      pattern: null,
      legal_question: false,
      reverses: null,
      status: 'APPROVED',
      proposed_by: 'agent',
      proposed_on: this.today,
      decided_by: 'agent',
      decided_on: this.today,
      decision_note: reason,
    });
    this.log('agent', 'act_safe', { target: id, account_id: accountId, reason: rationale, detail: { kind, rationale, evidence } });
    this.post(id);
    return id;
  }

  post(proposalId: string) {
    const p = this.proposals.find((x) => x.id === proposalId);
    if (!p) return;
    this.ledger.push({
      seq: this.ledger.length + 1,
      proposal_id: p.id,
      account_id: p.account_id,
      kind: p.kind,
      amount_cents: p.amount_cents,
      reverses: p.reverses,
      posted_on: this.today,
    });
    p.status = 'POSTED';
    const item = p.work_item_id ? this.item(p.work_item_id) : undefined;
    if (item && !SAFE_KINDS.includes(p.kind)) this.setState(item, 'POSTED');
    if (p.kind === 'PAUSE_COLLECTIONS' && p.account_id) {
      const a = this.accounts.get(p.account_id);
      if (a) a.collections_paused = true;
    }
    this.log('gateway', 'post', {
      target: p.id,
      account_id: p.account_id,
      reason: 'Approved, so the gateway posts it.',
      detail: { kind: p.kind, amount_cents: p.amount_cents },
    });
    this.afterPost(p);
  }

  /** Seed helper: a decision a person made earlier today. */
  decideAs(proposalId: string, actorId: string, approve: boolean, note = '') {
    const p = this.proposals.find((x) => x.id === proposalId);
    if (!p) return;
    const actor = this.actorOf(actorId);
    const action = approve ? 'approve' : 'reject';
    const d = this.canDecide(actor, p, action);
    this.applyDecision(p, actor, approve, note, d.reason);
  }

  canDecide(actor: Actor, p: Proposal, action: string): Decision {
    const deny = (reason: string): Decision => ({ allowed: false, reason });
    const allow = (reason: string): Decision => ({ allowed: true, reason });
    if (!STAFF_ROLES.includes(actor.role)) return deny(`The AI proposes and never approves. The ${actor.role} can't ${action}.`);
    if (p.proposed_by === actor.id) return deny(`Whoever proposes something can never ${action} it.`);
    const acct = p.account_id ? this.accounts.get(p.account_id) : undefined;
    if (acct?.patient_id && (this.staffPatients[actor.id] ?? []).includes(acct.patient_id)) return deny(`Nobody can ${action} their own account.`);
    if (p.legal_question) {
      return actor.role === 'compliance'
        ? allow('The compliance officer decides how the law applies.')
        : deny('This is about how the law applies, so only the compliance officer decides it.');
    }
    if (!(DECIDES[actor.role] ?? []).includes(p.kind)) return deny(`A ${actor.role} can't ${action} ${p.kind}.`);
    if (actor.role === 'counselor' && p.amount_cents > COUNSELOR_LIMIT_CENTS) return deny("Over the counselor's $5,000 limit; the director decides.");
    return allow(`Within the ${actor.role}'s limits.`);
  }

  private applyDecision(p: Proposal, actor: Actor, approve: boolean, note: string, reason: string) {
    const status: ProposalStatus = approve ? 'APPROVED' : 'REJECTED';
    p.status = status;
    p.decided_by = actor.id;
    p.decided_on = this.today;
    p.decision_note = note;
    const item = p.work_item_id ? this.item(p.work_item_id) : undefined;
    if (item) this.setState(item, status);
    if (!approve && p.pattern && !this.rejected.some((r) => r.pattern === p.pattern)) {
      const rule = this.rules.find((r) => r.proposal_id === p.id);
      this.rejected.push({
        pattern: p.pattern,
        text: rule?.text ?? null,
        proposal_id: p.id,
        rejected_by: actor.id,
        rejected_on: this.today,
        note: note || null,
      });
    }
    this.log(actor.id, approve ? 'approve' : 'reject', { target: p.id, account_id: p.account_id, reason, detail: { note } });
    if (approve) this.post(p.id);
  }

  /** What changes once something is posted: an approved rule starts applying. */
  private afterPost(p: Proposal) {
    if (this.seeding || p.kind !== 'NEW_RULE' || p.pattern !== 'CALFRESH_FREE_CARE') return;
    setTimeout(() => {
      const waitingCalFresh = this.items.filter((i) => this.waiting.has(i.id) && this.applicants.get(i.account_id)?.calfresh);
      for (const it of waitingCalFresh) {
        const acct = this.accounts.get(it.account_id);
        if (!acct) continue;
        this.waiting.delete(it.id);
        this.log('agent', 'apply_rule', {
          target: it.id,
          account_id: it.account_id,
          reason: 'Rule R-01 is approved, so this CalFresh account no longer waits for a person.',
          detail: { rule: 'R-01', pattern: 'CALFRESH_FREE_CARE' },
        });
        this.propose(
          it.id,
          'FREE_CARE',
          acct.billed_cents,
          'Enrolled in CalFresh, which requires income at or under 200% of the poverty level: free care without income documents (rule R-01, approved today).',
          { evidence: [{ source: 'rule', rule: 'R-01', pattern: 'CALFRESH_FREE_CARE' }, { source: 'fa_system', calfresh: 'Y', income_proof: 'NONE' }] },
        );
      }
      this.emit();
    }, 1200);
  }

  // ---------- public API (same shapes as the core) ----------

  state(): CoreState {
    const counts = Object.fromEntries(WORK_STATES.map((s) => [s, 0])) as Record<WorkState, number>;
    for (const i of this.items) counts[i.state] += 1;
    return {
      today: this.today,
      work_items_by_state: counts,
      open_proposals: this.proposals.filter((p) => p.status === 'PROPOSED').length,
      open_questions: this.questions.filter((q) => q.answer === null).length,
    };
  }

  actors(): Actor[] {
    return clone(this.staff);
  }

  /** People from the core: the sample world accepts them too, so any of them can act on a sample screen. */
  adoptStaff(people: Actor[]) {
    for (const p of people) {
      if (!STAFF_ROLES.includes(p.role)) continue;
      const known = this.staff.find((s) => s.id === p.id);
      if (known) {
        known.name = p.name;
        known.role = p.role;
      } else this.staff.push({ id: p.id, name: p.name, role: p.role });
    }
  }

  private joined(i: WorkItem): WorkItem {
    const a = this.accounts.get(i.account_id);
    return { ...i, patient_name: a?.patient_name ?? null, billed_cents: a?.billed_cents ?? null };
  }

  workItems(state?: WorkState, limit = 200): WorkItem[] {
    const rows = this.items
      .filter((i) => !state || i.state === state)
      .sort((a, b) => (a.updated_on === b.updated_on ? a.id.localeCompare(b.id) : b.updated_on.localeCompare(a.updated_on)));
    return clone(rows.slice(0, limit).map((i) => this.joined(i)));
  }

  inbox(actorId: string): Inbox {
    const actor = this.actorOf(actorId);
    const proposals = this.proposals
      .filter((p) => p.status === 'PROPOSED')
      .filter((p) => this.canDecide(actor, p, 'approve').allowed)
      .sort((a, b) => a.id.localeCompare(b.id));
    const questions = this.questions.filter((q) => q.answer === null && q.to_role === actor.role).map(stripFollow);
    return clone({ actor, proposals, questions });
  }

  hasAccount(id: string): boolean {
    return this.accounts.has(id);
  }

  account(id: string): AccountStory {
    const account = this.accounts.get(id);
    if (!account) throw new HttpError(404, `No account ${id}`);
    return clone({
      account,
      work_items: this.items.filter((i) => i.account_id === id),
      proposals: this.proposals.filter((p) => p.account_id === id),
      questions: this.questions.filter((q) => q.account_id === id).map(stripFollow),
      ledger: this.ledger.filter((l) => l.account_id === id),
      audit: this.auditLog.filter((r) => r.account_id === id),
    });
  }

  audit(q: AuditQuery): AuditRow[] {
    const needle = q.q?.trim().toLowerCase();
    const rows = this.auditLog.filter((r) => {
      if (q.account_id && r.account_id !== q.account_id) return false;
      if (q.actor_id && r.actor_id !== q.actor_id) return false;
      if (q.allowed !== undefined && r.allowed !== q.allowed) return false;
      if (needle) {
        const hay = `${r.reason}\n${r.target ?? ''}\n${JSON.stringify(r.detail)}\n${r.account_id ?? ''}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
    return clone(rows.slice().reverse().slice(0, q.limit ?? 200));
  }

  decide(proposalId: string, actorId: string, approve: boolean, note: string): Proposal {
    const p = this.proposals.find((x) => x.id === proposalId);
    if (!p) throw new HttpError(404, `Not found: ${proposalId}`);
    const actor = this.actorOf(actorId);
    const action = approve ? 'approve' : 'reject';
    const d = this.canDecide(actor, p, action);
    if (!d.allowed) this.refuse(actor.id, action, p.id, p.account_id, d.reason, { note });
    if (p.status !== 'PROPOSED') this.refuse(actor.id, action, p.id, p.account_id, `This proposal is already ${p.status}.`);
    this.applyDecision(p, actor, approve, note, d.reason);
    this.emit();
    return clone(p);
  }

  answer(questionId: string, actorId: string, text: string): Question {
    const q = this.questions.find((x) => x.id === questionId);
    if (!q) throw new HttpError(404, `Not found: ${questionId}`);
    const actor = this.actorOf(actorId);
    if (!STAFF_ROLES.includes(actor.role)) this.refuse(actor.id, 'answer', q.id, q.account_id, 'Only staff answer questions.');
    if (actor.role !== q.to_role) this.refuse(actor.id, 'answer', q.id, q.account_id, `This question is for the ${q.to_role}, not the ${actor.role}.`);
    if (q.answer !== null) this.refuse(actor.id, 'answer', q.id, q.account_id, 'This question is already answered.');
    q.answer = text;
    q.answered_by = actor.id;
    q.answered_on = this.today;
    const item = this.item(q.work_item_id);
    const wasWaiting = item?.state === 'NEEDS_INFO';
    if (item && wasWaiting) this.setState(item, 'SCREENING');
    this.log(actor.id, 'answer', { target: q.id, account_id: q.account_id, reason: text });
    const follow = q.follow;
    if (item && wasWaiting && follow) {
      this.pendingFollow.add(item.id);
      setTimeout(() => {
        this.pendingFollow.delete(item.id);
        if (item.state !== 'SCREENING') return;
        this.propose(item.id, follow.kind, follow.amount_cents, `${follow.rationale} ${actor.name} answered: “${text}”`, {
          evidence: [...(follow.evidence ?? []), { source: 'answer', question: q.id, answered_by: actor.id, answer: text }],
        });
        this.emit();
      }, 1400);
    }
    this.emit();
    return stripFollow(clone(q));
  }

  advance(days = 1): CoreState {
    for (let d = 0; d < Math.max(1, Math.min(days, 30)); d++) this.runDay();
    this.emit();
    return this.state();
  }

  private runDay() {
    this.today = addDays(this.today, 1);
    const fresh = 4 + Math.floor(this.rand() * 4);
    const requests = 1 + Math.floor(this.rand() * 2);
    this.log('sync', 'sync_day', {
      reason: `Synced ${shortDate(this.today)} from billing, financial assistance, the agency file and the mailroom: ${fresh} new self-pay accounts, ${fresh + 3} documents, ${requests} agency requests.`,
      detail: { new_accounts: fresh, documents: fresh + 3, agency_requests: requests },
    });

    for (const it of this.items.filter((i) => i.state === 'NEW').slice(0, 5)) {
      this.move(it.id, 'SCREENING', 'Checking for financial assistance');
      this.workClear(it);
    }
    for (const it of this.items.filter((i) => i.state === 'SCREENING' && !this.waiting.has(i.id) && !this.pendingFollow.has(i.id)).slice(0, 3)) this.workClear(it);

    for (let k = 0; k < fresh; k++) {
      const g = generateAccount(this);
      const itemId = this.openItem(g.id, 'Self-pay balance with no financial assistance decision');
      const r = this.rand();
      if (r < 0.2) continue; // stays NEW until tomorrow
      this.move(itemId, 'SCREENING', 'Checking for financial assistance');
      if (r < 0.32) {
        this.waiting.add(itemId);
        this.log('agent', 'wait', { target: itemId, account_id: g.id, reason: 'Application received; waiting for the income documents the patient said are in the mail.' });
        continue;
      }
      this.workClear(this.item(itemId)!);
    }

    for (let k = 0; k < requests; k++) {
      const g = generateAccount(this, { inCollections: true });
      const itemId = this.openItem(g.id, 'Agency asked to report the balance to credit bureaus');
      this.move(itemId, 'SCREENING', "Checking the agency's request against the law");
      const req = `GCR-R-${String(400 + Math.floor(this.rand() * 500)).padStart(5, '0')}`;
      this.actSafe(
        g.id,
        'BLOCK_AGENCY_ACTION',
        `Agency asked to credit report (${req}). SB 1061: Medical debt can't be reported to credit bureaus. IRS 501(r): The patient must be checked for financial assistance first.`,
        [{ source: 'agency_file', request_id: req, requested_action: 'CREDIT_REPORT' }],
        itemId,
      );
      this.actSafe(g.id, 'PAUSE_COLLECTIONS', 'Financial assistance screening is open.', [], itemId);
      this.workClear(this.item(itemId)!);
    }

    const blocked = this.rejected[0];
    if (blocked) {
      const target = this.items.find((i) => {
        const a = this.applicants.get(i.account_id);
        return i.state === 'NEEDS_INFO' && !!a && a.proof === 'NONE' && !a.calfresh;
      });
      if (target) {
        this.propose(target.id, 'DISCOUNT', Math.round((this.accounts.get(target.account_id)?.billed_cents ?? 0) * 0.7), 'Discount without income documents, as in 14 past cases.', {
          pattern: blocked.pattern,
        });
      }
    }
    this.planCollectedCents += (240 + Math.floor(this.rand() * 520)) * 100;
  }

  /** The agent works one clear item: screen it and propose, or ask the right person. */
  workClear(item: WorkItem) {
    const acct = this.accounts.get(item.account_id);
    const a = this.applicants.get(item.account_id);
    if (!acct || !a) return;
    if (item.state === 'NEW') this.move(item.id, 'SCREENING', 'Checking for financial assistance');
    const calfreshRule = this.isRuleApproved('CALFRESH_FREE_CARE');
    const s = screen(a, acct.billed_cents, Number(this.today.slice(0, 4)), calfreshRule);
    if (s.outcome === 'NEEDS_INFO') {
      const follow: FollowUp =
        s.pct != null && s.pct > 200
          ? { kind: 'DISCOUNT', amount_cents: acct.billed_cents - Math.round(acct.billed_cents * 0.3), rationale: `Income confirmed at ${s.pct.toFixed(0)}% of the poverty level, between 200% and 400%: patient pays 30% of the bill.` }
          : { kind: 'FREE_CARE', amount_cents: acct.billed_cents, rationale: s.pct != null ? `Income confirmed at ${s.pct.toFixed(0)}% of the poverty level, at or under 200%: free care.` : 'Other proof of income accepted (AB 2297): income is at or under 200% of the poverty level, so free care.' };
      this.ask(item.id, 'counselor', s.question ?? 'Please review this account.', follow);
      return;
    }
    const evidence: Evidence[] = [
      { source: 'fa_system', household: a.household, income: a.income, proof: a.proof },
      ...(s.pct != null ? [{ source: 'law', year: Number(this.today.slice(0, 4)), poverty_line: povertyLine(Number(this.today.slice(0, 4)), a.household), pct_of_poverty: Number(s.pct.toFixed(1)) }] : []),
    ];
    this.propose(item.id, s.outcome, s.adjustment_cents, s.reason, { evidence });
  }

  isRuleApproved(pattern: string): boolean {
    const r = this.rules.find((x) => x.pattern === pattern);
    const p = r ? this.proposals.find((x) => x.id === r.proposal_id) : undefined;
    return p?.status === 'POSTED' || p?.status === 'APPROVED';
  }

  discovery(): Discovery {
    const findings: DiscoveryFinding[] = this.findings.map((f) => ({
      ...f,
      proposal: f.proposal_id ? (this.proposals.find((p) => p.id === f.proposal_id) ?? null) : null,
    }));
    const reversals = findings.filter((f) => f.kind === 'ILLEGAL_DENIAL');
    return clone({
      as_of: '2026-06-30',
      history: this.history,
      law: {
        id: 'AB 2297',
        name: 'California AB 2297',
        effective: '2025-01-01',
        text: "From January 1, 2025, savings and other monetary assets can't be counted, there can be no application deadline, and other proof of income must be accepted.",
      },
      total_cents: reversals.reduce((s, f) => s + f.adjustment_cents + f.refund_cents, 0),
      findings,
      patterns_learned: this.patterns.filter((p) => p.legal).length,
      patterns_flagged: this.patterns.filter((p) => !p.legal).length,
    });
  }

  learned(): Learned {
    const rules = this.rules.map((r) => {
      const p = this.proposals.find((x) => x.id === r.proposal_id) ?? null;
      return {
        id: r.id,
        text: r.text,
        pattern: r.pattern,
        from_precedent: r.from_precedent,
        backtest: r.backtest,
        status: p?.status ?? 'PROPOSED',
        proposal: p,
        decided_by: p?.decided_by ?? null,
        decided_on: p?.decided_on ?? null,
        decision_note: p?.decision_note ?? null,
      };
    });
    const rejected = this.rejected.map((r) => ({
      ...r,
      blocked_since: this.auditLog.filter((a) => !a.allowed && a.reason.startsWith('Not proposed again') && a.reason.includes(`'${r.pattern}'`)).length,
    }));
    return clone({ patterns: this.patterns, precedents: this.precedents, rules, rejected });
  }

  correction(body: CorrectionIn): CorrectionResult {
    const actor = this.actorOf(body.actor_id);
    if (!STAFF_ROLES.includes(actor.role)) this.refuse(actor.id, 'correct', `account:${body.account_id}`, body.account_id, 'Only staff correct the AI.');
    const correctionId = this.next('C');
    const precedentId = `PR-${String(this.precedents.length + 1).padStart(2, '0')}`;
    const acct = this.accounts.get(body.account_id);
    const calfresh = /cal\s?fresh/i.test(`${body.correction} ${body.note}`);
    let similar: number;
    let ruleProposal: string | null = null;
    let message: string;
    this.log(actor.id, 'correct', {
      target: correctionId,
      account_id: body.account_id,
      reason: body.correction,
      detail: { note: body.note, precedent: precedentId },
    });
    const existing = calfresh ? this.rules.find((r) => r.pattern === 'CALFRESH_FREE_CARE') : undefined;
    if (existing) {
      similar = existing.backtest.cases_changed;
      ruleProposal = existing.proposal_id;
      message = `Saved as precedent ${precedentId}. It matches rule ${existing.id}, which is already with the director.`;
    } else {
      similar = 2 + Math.floor(this.rand() * 6);
      const ruleId = `R-${String(this.rules.length + 1).padStart(2, '0')}`;
      const dollars = similar * (1_400_00 + Math.floor(this.rand() * 2_600_00));
      const pattern = `CORRECTION_${correctionId.replace('-', '_')}`;
      ruleProposal = this.propose(
        null,
        'NEW_RULE',
        0,
        `Rule from precedent ${precedentId}: ${body.correction.replace(/\.$/, '')}. Backtest on 18 months: ${similar} past cases change, ${usd(dollars)} moves.`,
        { pattern, evidence: [{ source: 'precedent', precedent: precedentId, account_id: body.account_id, by: actor.id }] },
      );
      if (ruleProposal) {
        this.rules.push({
          id: ruleId,
          text: body.correction.replace(/\.$/, ''),
          pattern,
          from_precedent: precedentId,
          backtest: { cases_checked: this.history.applications, cases_changed: similar, dollars_moved_cents: dollars, examples: [] },
          proposal_id: ruleProposal,
        });
      }
      message = `Saved as precedent ${precedentId}. It found ${similar} similar past cases and proposed rule ${ruleId} for the director.`;
    }
    this.precedents.push({
      id: precedentId,
      correction_id: correctionId,
      account_id: body.account_id,
      patient_name: acct?.patient_name ?? null,
      by: actor.id,
      on: this.today,
      correction: body.correction,
      note: body.note || null,
      similar_cases: similar,
      rule_id: existing?.id ?? this.rules[this.rules.length - 1]?.id ?? null,
    });
    this.emit();
    return { correction_id: correctionId, precedent_id: precedentId, similar_cases: similar, rule_proposal_id: ruleProposal, message };
  }

  score(): Score {
    const posted = (kinds: ProposalKind[]) => this.ledger.filter((l) => kinds.includes(l.kind));
    const charityLive = posted(['FREE_CARE', 'DISCOUNT', 'REVERSAL']).reduce((s, l) => s + l.amount_cents, 0);
    const reversals = posted(['REVERSAL']).length;
    const blocks = this.proposals.filter((p) => p.kind === 'BLOCK_AGENCY_ACTION' && p.status === 'POSTED');
    const sb1061 = blocks.filter((p) => p.rationale.includes('SB 1061')).length;
    const stay = blocks.filter((p) => /automatic stay/i.test(p.rationale)).length;
    const refusals = this.auditLog.filter((r) => !r.allowed).length;
    const safeAlone = this.proposals.filter((p) => SAFE_KINDS.includes(p.kind) && p.proposed_by === 'agent').length;
    const byLaw: Record<string, number> = {
      'AB 2297 denials reversed': reversals,
      'SB 1061 credit reports blocked': 11 + sb1061,
      'IRS 501(r) early actions blocked': 9,
      'AB 1020 early lawsuits blocked': 3 + stay,
      'Gateway refusals': refusals,
    };
    const workedLive = this.items.length;
    const asked = new Set(this.questions.map((q) => q.work_item_id)).size;
    return {
      as_of: this.today,
      precision: { value: (236 + safeAlone) / (237 + safeAlone), correct: 236 + safeAlone, total: 237 + safeAlone },
      auto_share: { value: (412 + workedLive - asked) / (580 + workedLive), auto: 412 + workedLive - asked, total: 580 + workedLive },
      charity_cents: 1_184_220_00 + charityLive,
      payment_plan_collected_cents: this.planCollectedCents,
      violations_prevented: { count: Object.values(byLaw).reduce((s, n) => s + n, 0), by_law: byLaw },
      answer_key: { accounts_scored: 580 + workedLive, matched: 571 + workedLive - Math.min(2, asked) },
    };
  }

  judgeBox(text: string): JudgeBoxResult {
    const p = parseJudgeText(text);
    this.judgeSeq += 1;
    const accountId = `HB7009${String(this.judgeSeq).padStart(4, '0')}`;
    const mrn = `M709${String(this.judgeSeq).padStart(4, '0')}`;
    const name = `${p.first} ${p.last}`;
    const applicant: Applicant = { household: p.household, income: p.income, proof: p.proof, mediCal: p.mediCal, homeless: p.homeless, calfresh: p.calfresh };
    const appId = `FA-26-0${String(1900 + this.judgeSeq)}`;
    this.addAccount(
      {
        id: accountId,
        patient_id: mrn,
        patient_name: name.toUpperCase(),
        billed_cents: p.billedCents,
        first_bill_on: this.today,
        sources: {
          judge_box: { text },
          billing: {
            patient: { mrn, name: `${p.last.toUpperCase()}, ${p.first.toUpperCase()}`, address: p.homeless ? 'HOMELESS' : null },
            account: {
              account_no: accountId,
              service_date: this.today,
              service_type: p.serviceType,
              payer: 'SELF PAY',
              total_charges: (p.billedCents / 100).toFixed(2),
              patient_responsibility: (p.billedCents / 100).toFixed(2),
              first_statement_date: this.today,
              status: 'OPEN',
            },
          },
          fa: {
            applications: [
              {
                application_id: appId,
                name: `${p.first} ${p.last}`,
                household_size: p.household,
                income_stated: p.income,
                income_proof: p.proof,
                monetary_assets: p.savings,
                medi_cal: p.mediCal ? 'Y' : 'N',
                homeless: p.homeless ? 'Y' : 'N',
                received_on: this.today,
                form_version: '2025',
                status: 'RECEIVED',
              },
            ],
            notes: p.calfresh ? [{ note_id: `N${9_000_000 + this.judgeSeq}`, author: 'S-001', written_on: this.today, text: 'Patient says the household gets CalFresh.' }] : [],
          },
          crs: { sent: false, reason: 'NOT_A_SANDBOX_PERSONA', source: 'live', identity: { result: 'NOT_CHECKED' }, deceased: null, bankruptcy: null, contact: null },
        },
      },
      applicant,
    );

    let itemId = '';
    const year = Number(this.today.slice(0, 4));
    const income = p.income == null ? 'no income stated' : `$${p.income.toLocaleString('en-US')} a year${p.proof !== 'NONE' ? ` (${p.proof.toLowerCase().replace(/_/g, ' ')})` : ', no documents'}`;
    const steps: Array<() => void> = [
      () => {
        itemId = this.openItem(accountId, 'New patient typed into the judge box');
      },
      () =>
        this.log('agent', 'read_intake', {
          target: accountId,
          account_id: accountId,
          reason: `Read the description: ${name}, household of ${p.household}, ${income}, ${p.serviceType} bill ${usd(p.billedCents)}${p.mediCal ? ', on Medi-Cal' : ''}${p.calfresh ? ', on CalFresh' : ''}${p.homeless ? ', homeless' : ''}.`,
          detail: { ...p },
        }),
      () => this.move(itemId, 'SCREENING', 'Checking for financial assistance'),
      () =>
        this.log('agent', 'crs_check', {
          target: accountId,
          account_id: accountId,
          reason: 'CRS sandbox: not one of the 20 sandbox personas, so nothing was sent. That means no information, not a bad result.',
          detail: { sent: false, reason: 'NOT_A_SANDBOX_PERSONA' },
        }),
      () => {
        if (p.income != null && p.proof !== 'NONE' && !p.mediCal && !p.homeless) {
          const line = povertyLine(year, p.household);
          this.log('agent', 'check_law', {
            target: accountId,
            account_id: accountId,
            reason: `Household of ${p.household}: the ${year} poverty level is $${line.toLocaleString('en-US')}. Income is ${((100 * p.income) / line).toFixed(0)}% of it.`,
            detail: { year, poverty_line: line, income: p.income, household: p.household },
          });
        } else {
          this.log('agent', 'check_law', {
            target: accountId,
            account_id: accountId,
            reason: p.mediCal || p.homeless ? 'The policy gives free care without income documents here.' : 'Income can’t be checked yet: no proof of income.',
          });
        }
      },
      () => {
        const item = this.item(itemId);
        if (item) this.workClear(item);
        const prop = this.proposals.find((x) => x.work_item_id === itemId && x.status === 'PROPOSED');
        if (prop && prop.amount_cents > COUNSELOR_LIMIT_CENTS) {
          this.log('agent', 'route', { target: prop.id, account_id: accountId, reason: "Over the counselor's $5,000 limit, so the director decides." });
        } else if (prop) {
          this.log('agent', 'route', { target: prop.id, account_id: accountId, reason: 'Within the counselor’s limit, so a counselor decides.' });
        }
      },
    ];
    steps.forEach((fn, i) =>
      setTimeout(() => {
        fn();
        this.emit();
      }, 300 + i * 950),
    );
    return { account_id: accountId };
  }
}

function stripFollow(q: MockQuestion): Question {
  const { follow: _ignored, ...rest } = q;
  void _ignored;
  return rest;
}

// ---------- generated accounts for live days ----------

const FIRST = [
  'Alma', 'Bennett', 'Carmen', 'Dmitri', 'Esther', 'Felipe', 'Gloria', 'Hiro', 'Inez', 'Jamal', 'Keiko', 'Leon', 'Mariana', 'Nikhil',
  'Oksana', 'Pablo', 'Quinn', 'Renata', 'Silas', 'Tamara', 'Umar', 'Valeria', 'Wes', 'Ximena', 'Yusuf', 'Zora', 'Andre', 'Beatriz',
  'Colin', 'Delia', 'Emeka', 'Farah', 'Gustavo', 'Hana', 'Isaac', 'Jolene', 'Kwame', 'Lucia', 'Mateo', 'Noor', 'Orlando', 'Paloma',
  'Rocio', 'Stellan', 'Thuy', 'Vivian', 'Wendy', 'Abel', 'Bao', 'Cyrus',
];
const LAST = [
  'Acosta', 'Bertrand', 'Castillo', 'Dempsey', 'Echeverria', 'Fontaine', 'Galvan', 'Hollis', 'Ibarra', 'Jovanovic', 'Kaplan', 'Lozano',
  'Mbatha', 'Novak', 'Orozco', 'Pham', 'Quintana', 'Rios', 'Sato', 'Truong', 'Uribe', 'Vance', 'Whitaker', 'Yamada', 'Zamora', 'Aldana',
  'Cordero', 'Duarte', 'Espinoza', 'Farrell', 'Guerrero', 'Haines', 'Iwata', 'Jaramillo', 'Kessler', 'Lindo', 'Marquez', 'Okoro',
  'Petrov', 'Ramos', 'Salazar', 'Tejeda', 'Valdez', 'Weller', 'Ybarra', 'Zelaya', 'Adair', 'Beltran',
];

export function generateAccount(o: MockOffice, opts: { inCollections?: boolean; band?: 'free' | 'discount' | 'plan' | 'nodocs' | 'cutoff' } = {}) {
  const r = o.rand;
  const n = o.nameSeq++;
  const first = FIRST[(n * 7 + 3) % FIRST.length];
  const last = LAST[(n * 11 + 5) % LAST.length];
  const id = `HB7005${String(1000 + ((n * 389) % 9000)).padStart(4, '0')}`;
  const mrn = `M72${String(10000 + ((n * 7919) % 90000)).padStart(5, '0')}`;
  const household = 1 + Math.floor(r() * 5);
  const year = Number(o.today.slice(0, 4));
  const line = povertyLine(year, household);
  const band = opts.band ?? (['free', 'free', 'discount', 'discount', 'plan', 'nodocs', 'free'] as const)[Math.floor(r() * 7)];
  const pct = band === 'free' ? 70 + r() * 120 : band === 'discount' ? 215 + r() * 170 : band === 'plan' ? 420 + r() * 250 : band === 'cutoff' ? 198 + r() * 4 : 0;
  const income = band === 'nodocs' ? null : Math.round((line * pct) / 100 / 100) * 100;
  const billed = Math.round((600 + r() * 8900) * 100);
  const service = (['ER', 'OUTPATIENT', 'CLINIC', 'ER', 'INPATIENT'] as const)[Math.floor(r() * 5)];
  const proof = band === 'nodocs' ? 'NONE' : (['PAY_STUBS', 'PAY_STUBS', 'TAX_RETURN', 'EMPLOYER_LETTER', 'BENEFIT_LETTER'] as const)[Math.floor(r() * 5)];
  const firstBill = addDays(o.today, -(20 + Math.floor(r() * 140)));
  const appId = `FA-26-0${String(1300 + n)}`;
  const applicant: Applicant = { household, income, proof };
  o.addAccount(
    {
      id,
      patient_id: mrn,
      patient_name: `${first} ${last}`.toUpperCase(),
      billed_cents: billed,
      first_bill_on: firstBill,
      sources: {
        billing: {
          patient: { mrn, name: `${last.toUpperCase()}, ${first.toUpperCase()}`, phone: `(408) 555-${String(1000 + ((n * 37) % 9000)).slice(0, 4)}` },
          account: {
            account_no: id,
            service_date: addDays(firstBill, -18),
            service_type: service,
            payer: 'SELF PAY',
            total_charges: (billed / 100).toFixed(2),
            patient_responsibility: (billed / 100).toFixed(2),
            first_statement_date: firstBill,
            status: opts.inCollections ? 'IN_COLLECTIONS' : 'OPEN',
          },
        },
        fa: {
          applications: [
            {
              application_id: appId,
              name: `${first} ${last}`,
              household_size: household,
              income_stated: income,
              income_verified: proof === 'NONE' ? null : income,
              income_proof: proof,
              received_on: addDays(o.today, -Math.floor(r() * 10)),
              form_version: '2025',
              status: 'RECEIVED',
            },
          ],
        },
        documents:
          proof === 'NONE'
            ? []
            : [{ doc_id: `DOC-00${5000 + n}`, doc_type: proof === 'PAY_STUBS' ? 'PAY_STUB' : proof, name_on_document: `${first} ${last}`.toUpperCase(), received_on: addDays(o.today, -2) }],
        crs: { sent: false, reason: 'NOT_A_SANDBOX_PERSONA', source: 'live', identity: { result: 'NOT_CHECKED' }, deceased: null, bankruptcy: null, contact: null },
      },
    },
    applicant,
  );
  return { id, mrn, first, last, applicant, billed };
}

export const mock = new MockOffice();
