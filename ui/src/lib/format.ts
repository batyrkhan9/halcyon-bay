import type { Proposal, ProposalKind, Role, StaffRole, WorkState } from '../api/types';

/** Integer cents to dollars. `whole` drops the cents for big headline numbers. */
export function money(cents: number | null | undefined, opts: { whole?: boolean } = {}): string {
  if (cents == null || !Number.isFinite(cents)) return '—';
  const whole = opts.whole ?? false;
  const s = (Math.abs(cents) / 100).toLocaleString('en-US', {
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: whole ? 0 : 2,
  });
  return `${cents < 0 ? '−' : ''}$${s}`;
}

/** Dollar strings from the source systems ("4210.50") or numbers in dollars. */
export function dollars(v: unknown): string {
  const n = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN;
  if (!Number.isFinite(n)) return String(v ?? '—');
  return money(Math.round(n * 100));
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const ISO_TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

function utcDay(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function isIsoDay(v: unknown): v is string {
  return typeof v === 'string' && ISO_DAY.test(v);
}

export function isIsoTs(v: unknown): v is string {
  return typeof v === 'string' && ISO_TS.test(v);
}

/** "Jul 1, 2026" for a simulated ISO day. */
export function day(iso: string | null | undefined): string {
  if (!iso) return '—';
  if (!ISO_DAY.test(iso.slice(0, 10))) return iso;
  return utcDay(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

/** "Jul 1" */
export function dayShort(iso: string | null | undefined): string {
  if (!iso) return '—';
  if (!ISO_DAY.test(iso.slice(0, 10))) return iso;
  return utcDay(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

/** "Wednesday, July 1, 2026" */
export function dayLong(iso: string | null | undefined): string {
  if (!iso) return '—';
  return utcDay(iso).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

/** Wall-clock time of an audit row, in the viewer's zone. */
export function clock(ts: string | null | undefined): string {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' });
}

/** A fraction (0.996) as a percent ("99.6%"). */
export function percent(v: number, digits = 1): string {
  if (!Number.isFinite(v)) return '—';
  return `${(v * 100).toFixed(digits).replace(/\.0+$/, '')}%`;
}

export function count(n: number): string {
  return n.toLocaleString('en-US');
}

export function titleCase(name: string | null | undefined): string {
  if (!name) return 'Unknown patient';
  if (name !== name.toUpperCase()) return name;
  return name
    .toLowerCase()
    .replace(/(^|[\s'’-])([a-z])/g, (_m, sep: string, ch: string) => sep + ch.toUpperCase())
    .replace(/\bO'([a-z])/g, (_m, ch: string) => `O'${ch.toUpperCase()}`);
}

export const KIND_LABEL: Record<ProposalKind, string> = {
  FREE_CARE: 'Free care',
  DISCOUNT: 'Discount',
  PAYMENT_PLAN: 'Payment plan',
  COLLECTIONS_REFERRAL: 'Send to collections',
  PAUSE_COLLECTIONS: 'Pause collections',
  BLOCK_AGENCY_ACTION: 'Block an agency action',
  MERGE_ACCOUNTS: 'Merge duplicate accounts',
  REVERSAL: 'Reverse a past decision',
  NEW_RULE: 'New rule',
};

export function kindLabel(kind: string): string {
  return KIND_LABEL[kind as ProposalKind] ?? humanize(kind);
}

export const STATE_LABEL: Record<WorkState, string> = {
  NEW: 'New',
  SCREENING: 'Screening',
  NEEDS_INFO: 'Needs info',
  PROPOSED: 'Proposed',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  POSTED: 'Posted',
};

export const STATE_HINT: Record<WorkState, string> = {
  NEW: 'Just synced in',
  SCREENING: 'The AI is working it',
  NEEDS_INFO: 'Asked a person',
  PROPOSED: 'Waiting for a decision',
  APPROVED: 'Approved, posting',
  REJECTED: 'A person said no',
  POSTED: 'Done, in the ledger',
};

export const ROLE_LABEL: Record<string, string> = {
  counselor: 'Financial counselor',
  director: 'Revenue cycle director',
  compliance: 'Compliance officer',
  agent: 'AI agent',
  gateway: 'Gateway',
  sync: 'Sync job',
};

export const ROLE_SHORT: Record<string, string> = {
  counselor: 'Counselor',
  director: 'Director',
  compliance: 'Compliance',
  agent: 'AI agent',
  gateway: 'Gateway',
  sync: 'Sync',
};

export function roleLabel(role: Role | string | null | undefined): string {
  return role ? (ROLE_LABEL[role] ?? humanize(role)) : '';
}

export const SAFE_KINDS: ProposalKind[] = ['PAUSE_COLLECTIONS', 'BLOCK_AGENCY_ACTION'];

/** Who decides, from "Who decides what" in core/INTERFACE.md. A hint for people only: the gateway decides. */
export function deciderRole(p: Proposal): StaffRole | null {
  if (SAFE_KINDS.includes(p.kind)) return null;
  if (p.legal_question || p.kind === 'REVERSAL') return 'compliance';
  if (p.kind === 'NEW_RULE' || p.kind === 'COLLECTIONS_REFERRAL') return 'director';
  if (p.amount_cents > 5_000_00) return 'director';
  return 'counselor';
}

/** What the proposal's amount means, in words. Null when the amount isn't the point. */
export function amountMeaning(p: Proposal): string | null {
  if (!p.amount_cents) return null;
  switch (p.kind) {
    case 'FREE_CARE':
      return 'forgiven as free care';
    case 'DISCOUNT':
      return 'forgiven as a discount';
    case 'REVERSAL':
      return 'moved back to charity care';
    default:
      return 'change to what the patient owes';
  }
}

const ACRONYMS: Record<string, string> = {
  mrn: 'MRN',
  dob: 'Birth date',
  ssn: 'SSN',
  id: 'ID',
  fa: 'Financial assistance',
  crs: 'CRS',
  fpl: 'FPL',
  pct: '%',
  er: 'ER',
  url: 'URL',
  no: 'no.',
};

export function humanize(key: string): string {
  const words = key
    .replace(/_cents$/, '')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => ACRONYMS[w.toLowerCase()] ?? w.toLowerCase());
  if (!words.length) return key;
  const s = words.join(' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const DOLLAR_KEYS = new Set([
  'total_charges',
  'insurance_paid',
  'insurance_adjustment',
  'patient_responsibility',
  'amount',
  'amount_due',
  'monthly_amount',
  'placed_balance',
  'current_balance',
  'income_stated',
  'income_verified',
  'monetary_assets',
  'income',
  'annual_income',
  'gross_semi_monthly',
  'patient_paid',
  'dollars_moved',
  'agi',
  'poverty_line',
  'approval_limit',
  'balance',
]);

export function maskSsn(v: unknown): string {
  const s = String(v ?? '').replace(/\D/g, '');
  return s.length >= 4 ? `•••-••-${s.slice(-4)}` : '•••';
}
