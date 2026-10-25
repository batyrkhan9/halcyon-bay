// Defensive normalizers for the "Coming" endpoints, so a small shape difference in the core's
// first version shows up as a missing number instead of a blank screen.

import type { Discovery, DiscoveryFinding, Learned, Score } from './types';

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : {});
const arr = <T = unknown>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const num = (v: unknown, d = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : d);
const str = (v: unknown, d = ''): string => (typeof v === 'string' ? v : v == null ? d : String(v));

export function normalizeDiscovery(raw: unknown): Discovery {
  const r = obj(raw);
  const findings = arr<Obj>(r.findings).map((f, i): DiscoveryFinding => ({
    id: str(f.id, `F-${i + 1}`),
    kind: f.kind === 'ILLEGAL_REASON_SAME_OUTCOME' ? 'ILLEGAL_REASON_SAME_OUTCOME' : 'ILLEGAL_DENIAL',
    application_id: str(f.application_id),
    account_ids: arr<string>(f.account_ids ?? (f.account_id ? [f.account_id] : [])).map(String),
    patient_name: str(f.patient_name, 'Unknown patient'),
    decision_date: str(f.decision_date),
    decided_by: f.decided_by == null ? null : str(f.decided_by),
    stated_reason: str(f.stated_reason),
    reason_code: str(f.reason_code),
    fpl_pct: typeof f.fpl_pct === 'number' ? f.fpl_pct : null,
    correct_outcome: str(f.correct_outcome),
    law: str(f.law, 'AB 2297'),
    law_text: str(f.law_text),
    adjustment_cents: num(f.adjustment_cents),
    refund_cents: num(f.refund_cents),
    proposal: (f.proposal as DiscoveryFinding['proposal']) ?? null,
  }));
  const law = obj(r.law);
  const history = obj(r.history);
  return {
    as_of: str(r.as_of),
    history: {
      from: str(history.from, '2025-01-01'),
      to: str(history.to, '2026-06-30'),
      applications: num(history.applications),
      accounts: num(history.accounts),
    },
    law: {
      id: str(law.id, 'AB 2297'),
      name: str(law.name, 'California AB 2297'),
      effective: str(law.effective, '2025-01-01'),
      text: str(law.text),
    },
    total_cents: num(r.total_cents, findings.reduce((s, f) => s + f.adjustment_cents + f.refund_cents, 0)),
    findings,
    patterns_learned: num(r.patterns_learned),
    patterns_flagged: num(r.patterns_flagged),
  };
}

export function normalizeLearned(raw: unknown): Learned {
  const r = obj(raw);
  return {
    patterns: arr(r.patterns) as Learned['patterns'],
    precedents: arr(r.precedents) as Learned['precedents'],
    rules: arr<Obj>(r.rules).map((x) => ({
      ...(x as unknown as Learned['rules'][number]),
      backtest: {
        cases_checked: num(obj(x.backtest).cases_checked),
        cases_changed: num(obj(x.backtest).cases_changed),
        dollars_moved_cents: num(obj(x.backtest).dollars_moved_cents),
        examples: arr(obj(x.backtest).examples) as Learned['rules'][number]['backtest']['examples'],
      },
    })),
    rejected: arr(r.rejected) as Learned['rejected'],
  };
}

const fraction = (v: number) => (v > 1 ? v / 100 : v);

export function normalizeScore(raw: unknown): Score {
  const r = obj(raw);
  const p = obj(r.precision);
  const a = obj(r.auto_share);
  const v = obj(r.violations_prevented);
  return {
    as_of: str(r.as_of),
    precision: { value: fraction(num(p.value, typeof r.precision === 'number' ? r.precision : 0)), correct: num(p.correct), total: num(p.total) },
    auto_share: { value: fraction(num(a.value, typeof r.auto_share === 'number' ? r.auto_share : 0)), auto: num(a.auto), total: num(a.total) },
    charity_cents: num(r.charity_cents),
    payment_plan_collected_cents: num(r.payment_plan_collected_cents),
    violations_prevented: {
      count: num(v.count, typeof r.violations_prevented === 'number' ? r.violations_prevented : 0),
      by_law: (v.by_law as Record<string, number>) ?? undefined,
    },
    answer_key: (r.answer_key as Score['answer_key']) ?? null,
  };
}
