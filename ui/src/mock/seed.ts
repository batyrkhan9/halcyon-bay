// The sample world on day one (Jul 1, 2026), built from the committed simulated hospital:
// ui/src/mock/real.json is extracted from data/world, data/answer_key and data/crs/recorded by
// ui/scripts/extract_sample.py. Same people, account numbers, dollars and CRS answers as the core sees.
// Outcomes come from the answer key, so the sample agent is a stand-in for a perfect core.

import type { Evidence, Role } from '../api/types';
import raw from './real.json?raw';
import type { FollowUp, MockOffice } from './engine';

interface RealFinding {
  id: string;
  kind: 'ILLEGAL_DENIAL' | 'ILLEGAL_REASON_SAME_OUTCOME';
  law: string;
  application_id: string;
  account_ids: string[];
  patient_name: string;
  decision_date: string;
  decided_by: string;
  stated_reason: string;
  reason_code: string;
  fpl_pct: number | null;
  correct_outcome: string;
  adjustment_cents: number;
  refund_cents: number;
  reason: string;
}
interface RealLive {
  account_no: string;
  outcome: 'FREE' | 'DISCOUNT' | 'PAYMENT_PLAN' | 'NEEDS_INFO' | 'NO_CHANGE';
  fpl_pct: number | null;
  adjustment_cents: number;
  refund_cents: number;
  monthly_cents: number;
  handling: 'AUTO' | 'ASK';
  ask_role: string;
  approver_role: string;
  required_actions: string[];
  planted: string[];
  reason: string;
}
interface RealPlanted {
  id: string;
  category: string;
  summary: string;
  fix: string;
  dollars: number;
  records: Record<string, string[]>;
}
interface RealAccount {
  id: string;
  patient_id: string;
  patient_name: string;
  billed_cents: number;
  first_bill_on: string | null;
  day: string;
  sources: Record<string, unknown>;
}
interface RealWorld {
  ref: string;
  staff: Array<{ id: string; name: string; role: Role }>;
  staff_patients: Record<string, string[]>;
  history: { from: string; to: string; applications: number; accounts: number };
  findings: RealFinding[];
  calfresh: { cases_checked: number; cases_changed: number; dollars_cents: number; examples: Array<{ application_id: string; patient_name: string; before: string; after: string; dollars_cents: number }> };
  patterns: Array<{ pattern: string; evidence_count: number; legal: boolean; note: string }>;
  planted: RealPlanted[];
  live: RealLive[];
  accounts: Record<string, RealAccount>;
}

export const REAL = JSON.parse(raw) as RealWorld;

const LAW_TEXT: Record<string, string> = {
  SAVINGS_OVER_LIMIT: "Savings and other monetary assets can't be counted.",
  LATE_APPLICATION: 'There can be no application deadline.',
  NO_PAY_STUBS: 'Other proof of income must be accepted.',
  INCOME_OVER_LIMIT: 'Patients up to 400% of the poverty level qualify for free or discounted care.',
  OTHER: '',
};
const usd = (c: number) => `$${(c / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const KIND = { FREE: 'FREE_CARE', DISCOUNT: 'DISCOUNT', PAYMENT_PLAN: 'PAYMENT_PLAN' } as const;

/** The stories the demo needs on day one, whatever day the data has them. One of each planted kind, all CRS and CalFresh. */
function demoCast(): Set<string> {
  const seen = new Set<string>();
  const cast = new Set<string>();
  for (const p of REAL.planted) {
    const always = p.category.startsWith('CRS_') || p.category === 'CALFRESH';
    if (!always && seen.has(p.category)) continue;
    seen.add(p.category);
    (p.records.account_no ?? []).forEach((a) => cast.add(a));
  }
  return cast;
}

function plantedFor(l: RealLive): RealPlanted | undefined {
  return REAL.planted.find((p) => l.planted.includes(p.id));
}

function questionFor(l: RealLive, p: RealPlanted | undefined): string {
  if (p?.category === 'NEAR_CUTOFF' && l.fpl_pct != null) {
    const cutoff = Math.abs(l.fpl_pct - 200) < Math.abs(l.fpl_pct - 400) ? 200 : 400;
    return `Income is ${l.fpl_pct.toFixed(1)}% of the poverty level, right at the ${cutoff}% cutoff. Please confirm the income.`;
  }
  if (p?.category === 'CRS_BANKRUPTCY') return 'CRS shows an open Chapter 13 (case 25-50877). Collections are paused and the lawsuit request is blocked. File a proof of claim with the trustee, or hold the balance until the plan ends?';
  if (p?.category === 'CRS_DECEASED') return 'The CRS sandbox reports the patient as deceased. Collections are paused. Send the balance to the estate process, or close it?';
  return `${l.reason} Please decide before I propose anything.`;
}

type Doc = Record<string, unknown> & { doc_id?: string; doc_type?: string; excerpt?: string; flags?: string[] };
const HIDDEN = /\[\[([^\]]+)\]\]|((?:note|system|instruction)s? to (?:the )?ai reviewer[^.]*\.[^.]*\.)/i;
const QUOTABLE = /(gross pay[^|]{0,40}?\d[\d,]*\.\d{2}|net pay[^|]{0,30}?\d[\d,]*\.\d{2}|household (?:size|of)[^.]{0,20}\d+|\$\s?\d[\d,]*(?:\.\d{2})?(?: (?:per|a) (?:month|year))?|calfresh[^.]{0,60}|medi-cal[^.]{0,40})/i;
const DOC_WORDS: Record<string, string> = { PAY_STUB: 'pay stub', BANK_STATEMENT: 'bank statement', TAX_RETURN: 'tax return', EMPLOYER_LETTER: 'employer letter', BENEFIT_LETTER: 'benefit letter', SELF_ATTESTATION: 'signed statement' };

/** What the reader found in the account's documents: facts with exact quotes, and what it refused. */
function readDocuments(acct: RealAccount) {
  const docs = ((acct.sources.documents as Doc[] | undefined) ?? []).filter((d) => d.excerpt);
  const facts: Array<{ fact: string; document_id: string; quote: string }> = [];
  const notUsed: Array<{ fact: string; document_id: string; quote: string; why: string }> = [];
  const hidden: Array<{ document_id: string; quote: string; found_by: string }> = [];
  for (const d of docs) {
    const text = d.excerpt ?? '';
    const h = HIDDEN.exec(text);
    const m = QUOTABLE.exec(text);
    const what = DOC_WORDS[d.doc_type ?? ''] ?? String(d.doc_type ?? 'document').toLowerCase();
    if (h) {
      hidden.push({ document_id: d.doc_id ?? '', quote: (h[1] ?? h[2] ?? h[0]).trim(), found_by: 'scan' });
      if (m) notUsed.push({ fact: `income on the ${what}`, document_id: d.doc_id ?? '', quote: m[0].trim(), why: 'the document has hidden instructions, so nothing in it is used' });
    } else if (m && facts.length < 3) {
      facts.push({ fact: `from the ${what}`, document_id: d.doc_id ?? '', quote: m[0].trim() });
    }
  }
  return { docs, facts, notUsed, hidden };
}

export function liveRow(accountNo: string): RealLive | undefined {
  return REAL.live.find((l) => l.account_no === accountNo);
}

/** The agent works one live account the way the answer key says a careful office would. */
export function workLive(o: MockOffice, l: RealLive, calfreshRule: boolean) {
  const acct = REAL.accounts[l.account_no];
  if (!acct || o.items.some((i) => i.account_id === l.account_no && i.reason !== 'Past denial flagged at onboarding')) return;
  // What the office can see, never the answer key's description of the case.
  const reqs = (acct.sources.agency as { requests?: Array<{ request_id?: string; requested_action?: string }> } | undefined)?.requests ?? [];
  const req = reqs[reqs.length - 1];
  const WHAT: Record<string, string> = { CREDIT_REPORT: 'report the balance to credit bureaus', LAWSUIT: 'file a lawsuit', SELL_DEBT: 'sell the debt', LIEN: 'place a lien' };
  const it = o.openItem(l.account_no, req ? `Agency asked to ${WHAT[req.requested_action ?? ''] ?? 'take an action'} (${req.request_id})` : 'Self-pay balance with no financial assistance decision');
  o.move(it, 'SCREENING', req ? "Checking the agency's request against the law" : 'Checking for financial assistance');
  workItem(o, it, l, calfreshRule);
}

/** Read the case, act safely where the law requires it, then propose or ask. Safe to call again. */
export function workItem(o: MockOffice, it: string, l: RealLive, calfreshRule: boolean) {
  const acct = REAL.accounts[l.account_no];
  if (!acct) return;
  const p = plantedFor(l);
  const read = readDocuments(acct);
  const crs = acct.sources.crs as { identity?: { result?: string }; bankruptcy?: { open?: boolean; records?: Array<{ case_number?: string }> }; deceased?: boolean } | undefined;
  if (crs) {
    o.log('agent', 'crs_check', {
      target: l.account_no,
      account_id: l.account_no,
      reason: `CRS sandbox (recorded answer): identity ${crs.identity?.result ?? 'not checked'}${crs.deceased ? '; reported deceased' : ''}${crs.bankruptcy?.open ? `; open bankruptcy, case ${crs.bankruptcy.records?.[0]?.case_number ?? ''}` : ''}.`,
      detail: { source: 'recorded' },
    });
  }
  const conflicts = p?.category === 'DOCS_DISAGREE' ? [{ area: 'INCOME', description: l.reason }] : [];
  const missing = read.docs.length === 0 && (l.outcome === 'NEEDS_INFO' || l.handling === 'ASK') ? ['proof of income'] : [];
  o.log('agent', 'read_case', {
    target: it,
    account_id: l.account_no,
    reason: read.docs.length ? `Read ${read.docs.length} document${read.docs.length === 1 ? '' : 's'} and the staff notes.` : 'Read the staff notes; no documents on file.',
    detail: { model: 'sample', cached: false, facts: read.facts, not_used: read.notUsed, conflicts, missing },
  });
  for (const h of read.hidden) {
    const scanned = (acct.sources.documents as Doc[] | undefined)?.find((d) => d.doc_id === h.document_id);
    if (scanned) {
      scanned.flags = ['HIDDEN_INSTRUCTIONS'];
      scanned.handling = 'Treated as evidence, not instructions. The hidden text was ignored and logged; nothing in this document was used.';
    }
    o.log('agent', 'follow_hidden_instructions', {
      target: h.document_id,
      account_id: l.account_no,
      allowed: false,
      reason: `Ignored instructions hidden in ${h.document_id}: "${h.quote}". Nothing in that document is used.`,
      detail: h,
    });
  }
  if (p?.category === 'STAFF_SELF_APPROVAL') {
    o.log('agent', 'match_identity', {
      target: 'S-004',
      account_id: l.account_no,
      reason: 'The patient is staff member S-004 Tomas Brandt (same birth date and home address as the HR export). S-004 can’t decide this account.',
    });
  }
  const safeDone = (kind: string, subject: string | null) =>
    o.proposals.some((x) => x.account_id === l.account_no && x.kind === kind && (subject === null || x.subject === subject));
  for (const a of l.required_actions) {
    if (a === 'PAUSE_COLLECTIONS' && !safeDone('PAUSE_COLLECTIONS', null)) {
      o.actSafe(l.account_no, 'PAUSE_COLLECTIONS', p?.category === 'CRS_BANKRUPTCY' ? 'Open Chapter 13 bankruptcy (CRS): the automatic stay stops all collection activity.' : 'Collections stop while this is sorted out.', [], it);
    }
    if (a.startsWith('BLOCK_AGENCY_ACTION:')) {
      const reqId = a.split(':')[1];
      if (!safeDone('BLOCK_AGENCY_ACTION', `agency_request:${reqId}`)) {
        o.actSafe(l.account_no, 'BLOCK_AGENCY_ACTION', `Agency request ${reqId} blocked. ${l.reason}`, [{ source: 'agency_file', request: reqId }], it, `agency_request:${reqId}`);
      }
    }
  }
  const kind = KIND[l.outcome as keyof typeof KIND];
  const rationale = l.outcome === 'PAYMENT_PLAN' && l.monthly_cents ? `${l.reason} 12 interest-free payments of ${usd(l.monthly_cents)}.` : l.reason;
  const evidence: Evidence[] = read.facts.length ? read.facts : [{ source: 'answer_key_reason', fpl_pct: l.fpl_pct }];
  if (p?.category === 'CALFRESH' && !calfreshRule) {
    o.applicants.set(l.account_no, { household: 1, income: null, proof: 'NONE', calfresh: true });
    o.waiting.add(it);
    o.log('agent', 'wait', { target: it, account_id: l.account_no, reason: 'CalFresh, no income documents. Waiting for the director to decide rule R-01 instead of asking the counselor again.' });
    return;
  }
  if (p?.category === 'CALFRESH' && calfreshRule) {
    o.propose(it, 'FREE_CARE', acct.billed_cents, 'Enrolled in CalFresh, which requires income at or under 200% of the poverty level: free care without income documents (rule R-01).', { evidence });
    return;
  }
  const merge = l.required_actions.find((a) => a.startsWith('MERGE:'));
  if (merge) {
    o.propose(it, 'MERGE_ACCOUNTS', 0, `${merge.slice(6).replace('+', ' and ')} are one person. ${l.reason}`, { evidence });
    return;
  }
  const reversal = l.required_actions.find((a) => a.startsWith('REVERSAL:'));
  if (reversal) {
    o.propose(it, 'REVERSAL', l.adjustment_cents, l.reason, { evidence, legal_question: true, reverses: `fa_decision:${reversal.slice(9)}` });
    return;
  }
  if (l.handling === 'ASK' || l.outcome === 'NEEDS_INFO') {
    const prior = o.questions.filter((q) => q.work_item_id === it);
    if (prior.some((q) => q.answer === null)) return; // still waiting on a person
    const answered = prior.find((q) => q.answer !== null);
    if (answered) {
      // Never ask the same thing twice: act on the answer.
      const by = o.staff.find((s) => s.id === answered.answered_by)?.name ?? answered.answered_by ?? 'Staff';
      if (kind) {
        o.propose(it, kind, l.adjustment_cents, `${rationale} ${by} answered: “${answered.answer}”`, {
          evidence: [...evidence, { fact: `answer from ${by}`, document_id: null, quote: answered.answer ?? '' }],
        });
      } else {
        o.waiting.add(it);
        o.log('agent', 'no_change', { target: it, account_id: l.account_no, reason: `Noted ${by}'s answer to ${answered.id}. ${l.reason}` });
      }
      return;
    }
    const follow: FollowUp | null = kind ? { kind, amount_cents: l.adjustment_cents, rationale } : null;
    o.ask(it, (l.ask_role || 'counselor') as Role, questionFor(l, p), follow);
    return;
  }
  if (kind) o.propose(it, kind, l.adjustment_cents, rationale, { evidence });
  else {
    o.waiting.add(it);
    o.log('agent', 'no_change', { target: it, account_id: l.account_no, reason: l.reason });
  }
}

export function seedWorld(o: MockOffice) {
  o.today = '2026-07-01';
  o.staff = REAL.staff.map((s) => ({ ...s }));
  o.staffPatients = { ...REAL.staff_patients };
  o.history = { ...REAL.history };
  for (const a of Object.values(REAL.accounts)) {
    o.addAccount({ id: a.id, patient_id: a.patient_id, patient_name: a.patient_name, billed_cents: a.billed_cents, first_bill_on: a.first_bill_on, sources: a.sources });
  }

  // ---------- onboarding: 18 months of history ----------
  o.log('sync', 'load_history', {
    reason: `Loaded history from Jan 1, 2025 to Jun 30, 2026: ${REAL.history.accounts.toLocaleString('en-US')} accounts and ${REAL.history.applications.toLocaleString('en-US')} applications.`,
    detail: { ...REAL.history },
  });
  o.patterns = REAL.patterns.map((p, i) => ({
    id: `LP-${String(i + 1).padStart(2, '0')}`,
    text: p.pattern,
    evidence_count: p.evidence_count,
    legal: p.legal,
    status: p.legal ? ('LEARNED' as const) : ('FLAGGED' as const),
    law: p.legal ? null : (p.note.match(/AB 2297|AB 1020|SB 1061|501\(r\)/)?.[0] ?? 'the law'),
    law_text: p.legal ? null : p.note,
    note: p.legal ? p.note : null,
  }));
  for (const p of o.patterns) {
    o.log('agent', p.legal ? 'learn_pattern' : 'flag_pattern', {
      target: p.id,
      reason: p.legal ? `Learned from ${p.evidence_count} past decisions: ${p.text}.` : `Not learned: "${p.text}" (${p.evidence_count} past decisions) breaks ${p.law}. ${p.law_text}`,
      detail: { evidence_count: p.evidence_count, legal: p.legal },
    });
  }

  // ---------- day-one discovery ----------
  for (const f of REAL.findings) {
    const account = f.account_ids[0];
    let proposalId: string | null = null;
    if (f.kind === 'ILLEGAL_DENIAL' && account && o.accounts.has(account)) {
      const it = o.openItem(account, 'Past denial flagged at onboarding');
      o.move(it, 'SCREENING', 'Checking the past denial against the law');
      proposalId = o.propose(it, 'REVERSAL', f.adjustment_cents, `${f.reason} ${f.law}: ${LAW_TEXT[f.reason_code] ?? ''}${f.refund_cents ? ` Refund ${usd(f.refund_cents)} the patient paid.` : ''}`, {
        evidence: [
          { source: 'fa_system', application_id: f.application_id, decision: 'DENIED', decision_date: f.decision_date, decided_by: f.decided_by, reason_as_typed: f.stated_reason },
          { source: 'law', law: f.law, rule: LAW_TEXT[f.reason_code] ?? '' },
          { source: 'income', pct_of_poverty: f.fpl_pct },
        ],
        legal_question: true,
        reverses: `fa_decision:${f.application_id}`,
      });
    }
    o.findings.push({ ...f, law_text: LAW_TEXT[f.reason_code] ?? '', proposal_id: proposalId });
  }
  const ab2297 = REAL.findings.filter((f) => f.kind === 'ILLEGAL_DENIAL' && f.law === 'AB 2297');
  o.log('agent', 'discover', {
    reason: `Day-one discovery: ${ab2297.length} patients denied since Jan 1, 2025 for savings, a late application or missing pay stubs, although their income qualifies (AB 2297). ${REAL.findings.filter((f) => f.kind === 'ILLEGAL_DENIAL' && f.law !== 'AB 2297').length} more were denied as over income at or under 400% (AB 1020). Reversals sent to the compliance officer.`,
  });

  // ---------- a stored "no": discounts without income documents ----------
  const tempting = REAL.planted.filter((p) => p.category === 'TEMPTING_DISCOUNT').length;
  const noDocs = o.propose(null, 'NEW_RULE', 0, `Pattern from history: discounts given without any income documents. Propose it as a rule: a discount without income documents when the patient says income is under 400%.`, {
    pattern: 'DISCOUNT_WITHOUT_INCOME_DOCUMENTS',
    evidence: [{ source: 'history', live_cases_it_would_touch: tempting }],
  });
  if (noDocs) {
    o.rules.push({ id: 'R-00', text: 'Discounts without income documents', pattern: 'DISCOUNT_WITHOUT_INCOME_DOCUMENTS', from_precedent: null, backtest: { cases_checked: REAL.history.applications, cases_changed: tempting, dollars_moved_cents: 0, examples: [] }, proposal_id: noDocs });
    o.decideAs(noDocs, 'S-002', false, 'A discount needs proof of income. Ask for any proof instead; AB 2297 lets us accept other proof.');
  }

  // ---------- live accounts: day one, plus the demo's planted stories ----------
  const cast = demoCast();
  for (const l of REAL.live) {
    const a = REAL.accounts[l.account_no];
    if (a && (a.day <= o.today || cast.has(l.account_no))) workLive(o, l, false);
  }

  // ---------- CalFresh: the counselor's correction is precedent PR-01, rule R-01 waits for the director ----------
  const calfresh = REAL.planted.filter((p) => p.category === 'CALFRESH' && p.records.account_no?.length).map((p) => p.records.account_no[0]);
  const first = calfresh.find((a) => o.items.some((i) => i.account_id === a));
  if (first) {
    const it = o.items.find((i) => i.account_id === first && o.waiting.has(i.id));
    if (it) {
      o.waiting.delete(it.id);
      const q = o.ask(it.id, 'counselor', 'No income documents. The patient has a CalFresh notice, which neither version of the policy mentions. How should this be handled?', null);
      const question = o.questions.find((x) => x.id === q);
      const answer = 'CalFresh enrollment means household income is at or under 200%. Give free care without income documents.';
      if (question) Object.assign(question, { answer, answered_by: 'S-001', answered_on: o.today });
      o.setState(it, 'SCREENING');
      o.log('S-001', 'answer', { target: q, account_id: first, reason: answer });
      o.log('S-001', 'correct', { target: 'C-0001', account_id: first, reason: answer, detail: { precedent: 'PR-01' } });
      o.next('C');
      o.precedents.push({ id: 'PR-01', correction_id: 'C-0001', account_id: first, patient_name: REAL.accounts[first]?.patient_name ?? null, by: 'S-001', on: o.today, correction: answer, note: 'The county CalFresh notice is enough proof.', similar_cases: REAL.calfresh.cases_changed, rule_id: 'R-01' });
      o.propose(it.id, 'FREE_CARE', REAL.accounts[first]?.billed_cents ?? 0, 'Free care: enrolled in CalFresh, which requires income at or under 200% of the poverty level. Precedent PR-01 from the counselor.', { evidence: [{ source: 'precedent', precedent: 'PR-01', by: 'S-001' }] });
    }
    const rule = o.propose(null, 'NEW_RULE', 0, `Rule from precedent PR-01: a patient enrolled in CalFresh gets free care without income documents, because CalFresh requires income at or under 200% of the poverty level. Backtest on 18 months: ${REAL.calfresh.cases_changed} past cases change, ${usd(REAL.calfresh.dollars_cents)} moves to charity care.`, {
      pattern: 'CALFRESH_FREE_CARE',
      evidence: [{ source: 'precedent', precedent: 'PR-01', account_id: first }, { source: 'backtest', cases_changed: REAL.calfresh.cases_changed, dollars_moved_cents: REAL.calfresh.dollars_cents }],
    });
    if (rule) {
      o.rules.push({
        id: 'R-01',
        text: 'Enrolled in CalFresh: free care without income documents',
        pattern: 'CALFRESH_FREE_CARE',
        from_precedent: 'PR-01',
        backtest: { cases_checked: REAL.history.applications, cases_changed: REAL.calfresh.cases_changed, dollars_moved_cents: REAL.calfresh.dollars_cents, examples: REAL.calfresh.examples.slice(0, 5) },
        proposal_id: rule,
      });
    }
  }

  // ---------- attempts the gateway refused on day one ----------
  const plan = o.proposals.find((p) => p.kind === 'PAYMENT_PLAN' && p.status === 'PROPOSED');
  if (plan) o.log('agent', 'post', { target: plan.id, account_id: plan.account_id, allowed: false, reason: 'Only the gateway posts changes.' });
  const big = o.proposals.find((p) => p.kind === 'DISCOUNT' && p.status === 'PROPOSED' && p.amount_cents > 5_000_00);
  if (big) o.log('S-004', 'approve', { target: big.id, account_id: big.account_id, allowed: false, reason: "Over the counselor's $5,000 limit; the director decides.", detail: { note: '' } });
  for (const it of o.items.filter((i) => i.state === 'NEEDS_INFO').slice(0, 2)) {
    o.propose(it.id, 'DISCOUNT', Math.round((o.accounts.get(it.account_id)?.billed_cents ?? 0) * 0.7), 'Discount without income documents, as in past cases.', { pattern: 'DISCOUNT_WITHOUT_INCOME_DOCUMENTS' });
  }
}

/** Live accounts whose data arrives on `day` (and aren't already worked). */
export function arrivals(day: string): RealLive[] {
  return REAL.live.filter((l) => REAL.accounts[l.account_no]?.day === day);
}
