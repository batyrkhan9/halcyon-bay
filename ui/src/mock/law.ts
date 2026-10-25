// Screening math for the SAMPLE world only, so the mock behaves like the office.
// The real legal math lives in core/law.py and core/policy.py; the UI never decides anything for the core.

export const POVERTY: Record<number, [number, number]> = {
  2025: [15_650, 5_500],
  2026: [15_960, 5_680],
};

export function povertyLine(year: number, household: number): number {
  const [first, extra] = POVERTY[year] ?? POVERTY[2026];
  return first + extra * (Math.max(1, household) - 1);
}

export function pctOfPoverty(income: number, household: number, year: number): number {
  return (100 * income) / povertyLine(year, household);
}

export type Proof = 'PAY_STUBS' | 'TAX_RETURN' | 'EMPLOYER_LETTER' | 'BENEFIT_LETTER' | 'SELF_ATTESTATION' | 'NONE';

export interface Applicant {
  household: number;
  income: number | null;
  proof: Proof;
  mediCal?: boolean;
  homeless?: boolean;
  calfresh?: boolean;
}

export interface Screened {
  outcome: 'FREE_CARE' | 'DISCOUNT' | 'PAYMENT_PLAN' | 'NEEDS_INFO';
  adjustment_cents: number;
  pct: number | null;
  reason: string;
  question?: string;
}

const pct0 = (p: number) => `${p.toFixed(0)}%`;

export function monthlyPlanCents(billedCents: number): number {
  return Math.max(25_00, Math.ceil(billedCents / 12 / 100) * 100);
}

export function screen(a: Applicant, billedCents: number, year = 2026, calfreshRule = false): Screened {
  if (a.homeless) {
    return { outcome: 'FREE_CARE', adjustment_cents: billedCents, pct: null, reason: 'Homeless: free care without income documents, as the policy says.' };
  }
  if (a.mediCal) {
    return { outcome: 'FREE_CARE', adjustment_cents: billedCents, pct: null, reason: 'Enrolled in Medi-Cal: free care without income documents, as the policy says.' };
  }
  if (a.calfresh && (a.income == null || a.proof === 'NONE')) {
    if (calfreshRule) {
      return {
        outcome: 'FREE_CARE',
        adjustment_cents: billedCents,
        pct: null,
        reason: 'Enrolled in CalFresh, which requires income at or under 200% of the poverty level: free care without income documents (rule R-01).',
      };
    }
    return {
      outcome: 'NEEDS_INFO',
      adjustment_cents: 0,
      pct: null,
      reason: 'CalFresh, no income documents',
      question: 'No income documents. The patient says they are on CalFresh, which neither version of the policy mentions. How should this be handled?',
    };
  }
  if (a.income == null || a.proof === 'NONE') {
    return {
      outcome: 'NEEDS_INFO',
      adjustment_cents: 0,
      pct: null,
      reason: 'No income documents',
      question:
        'No income documents. Please ask for any proof of income: pay stubs, a tax return, an employer or benefit letter, or a signed statement. AB 2297 says other proof must be accepted.',
    };
  }
  const pct = pctOfPoverty(a.income, a.household, year);
  for (const cutoff of [200, 400]) {
    if (Math.abs(pct - cutoff) <= 5) {
      return {
        outcome: 'NEEDS_INFO',
        adjustment_cents: 0,
        pct,
        reason: `Near the ${cutoff}% cutoff`,
        question: `Income is ${pct.toFixed(1)}% of the poverty level, right at the ${cutoff}% cutoff. Please confirm the income.`,
      };
    }
  }
  if (pct <= 200) {
    return { outcome: 'FREE_CARE', adjustment_cents: billedCents, pct, reason: `Income is ${pct0(pct)} of the poverty level, at or under 200%: free care.` };
  }
  if (pct <= 400) {
    const pays = Math.round(billedCents * 0.3);
    return {
      outcome: 'DISCOUNT',
      adjustment_cents: billedCents - pays,
      pct,
      reason: `Income is ${pct0(pct)} of the poverty level, between 200% and 400%: patient pays 30% of the bill.`,
    };
  }
  const monthly = monthlyPlanCents(billedCents);
  return {
    outcome: 'PAYMENT_PLAN',
    adjustment_cents: 0,
    pct,
    reason: `Income is ${pct0(pct)} of the poverty level, over 400%: an interest-free payment plan of 12 payments of $${(monthly / 100).toFixed(0)}.`,
  };
}

// ---------- the judge box, sample version ----------

const WORD_NUMBERS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, a: 1, an: 1,
};
const toInt = (s: string) => (/^\d+$/.test(s) ? Number(s) : WORD_NUMBERS[s.toLowerCase()] ?? NaN);

function money(raw: string, k?: string): number {
  const n = Number(raw.replace(/[,$\s]/g, ''));
  return k && /k/i.test(k) ? n * 1000 : n;
}

export interface ParsedPatient {
  first: string;
  last: string;
  household: number;
  income: number | null;
  incomeText: string | null;
  proof: Proof;
  mediCal: boolean;
  homeless: boolean;
  calfresh: boolean;
  billedCents: number;
  serviceType: 'ER' | 'INPATIENT' | 'OUTPATIENT' | 'CLINIC';
  savings: number | null;
}

const NOT_NAMES = new Set([
  'The', 'She', 'He', 'They', 'Her', 'His', 'Their', 'Bill', 'ER', 'No', 'Medi', 'Cal', 'CalFresh', 'Medi-Cal', 'Self', 'Pay',
  'Patient', 'Mom', 'Dad', 'Mr', 'Mrs', 'Ms', 'Dr', 'A', 'An', 'In', 'On', 'At', 'Last', 'This', 'Came', 'Has', 'Is', 'Was',
  'I', 'We', 'It', 'Family', 'Household', 'Single', 'Works', 'Lives', 'California', 'Halcyon', 'Bay', 'Hospital',
]);

export function parseJudgeText(text: string): ParsedPatient {
  const t = text.replace(/\s+/g, ' ').trim();

  let first = 'New';
  let last = 'Patient';
  const nameRe = /\b([A-Z][a-zA-Z'’-]+)\s+([A-Z][a-zA-Z'’-]+)\b/g;
  for (let m = nameRe.exec(t); m; m = nameRe.exec(t)) {
    if (!NOT_NAMES.has(m[1]) && !NOT_NAMES.has(m[2])) {
      first = m[1];
      last = m[2];
      break;
    }
  }

  let household = 1;
  const hh = t.match(/(?:family|household)\s+of\s+(\w+)/i) || t.match(/(\w+)[- ]person household/i);
  if (hh && !Number.isNaN(toInt(hh[1]))) household = toInt(hh[1]);
  else {
    const kids = t.match(/(\w+)\s+(?:kids|children|sons|daughters)/i);
    const partner = /\b(husband|wife|partner|spouse|married)\b/i.test(t);
    if (kids && !Number.isNaN(toInt(kids[1]))) household = 1 + toInt(kids[1]) + (partner ? 1 : 0);
    else if (partner) household = 2;
  }

  let income: number | null = null;
  let incomeText: string | null = null;
  const inc =
    t.match(/\$?\s?(\d[\d,]*(?:\.\d+)?)\s?(k)?\s*(?:a|per|\/|each)\s*(year|yr|annually|month|mo|week|wk|hour|hr)/i) ||
    t.match(/(?:earns?|makes?|income(?: is| of)?)\s+(?:about|around|roughly|~)?\s*\$?\s?(\d[\d,]*(?:\.\d+)?)\s?(k)?/i);
  if (inc) {
    const amount = money(inc[1], inc[2]);
    const per = (inc[3] || 'year').toLowerCase();
    const mult = per.startsWith('mo') ? 12 : per.startsWith('w') ? 52 : per.startsWith('h') ? 2080 : 1;
    income = Math.round(amount * mult);
    incomeText = inc[0].trim();
  }
  if (/\b(no|zero|without)\s+(income|job|work)\b|\bunemployed\b/i.test(t) && income == null) income = 0;

  let billedCents = 0;
  const bill =
    t.match(/(?:bill|charges?|owes?|balance|statement)\D{0,24}\$\s?(\d[\d,]*(?:\.\d+)?)\s?(k)?/i) ||
    t.match(/\$\s?(\d[\d,]*(?:\.\d+)?)\s?(k)?\s*(?:ER|hospital|medical)?\s*(?:bill|charges?|balance)/i);
  if (bill) billedCents = Math.round(money(bill[1], bill[2]) * 100);
  if (!billedCents) {
    const any = [...t.matchAll(/\$\s?(\d[\d,]*(?:\.\d+)?)\s?(k)?/gi)].map((m) => money(m[1], m[2]));
    const candidates = any.filter((n) => n !== income && n < 200_000);
    if (candidates.length) billedCents = Math.round(Math.max(...candidates) * 100);
  }
  if (!billedCents) billedCents = 4_800_00;

  const savingsM = t.match(/(?:savings|saved|in the bank)\D{0,16}\$\s?(\d[\d,]*)\s?(k)?/i);
  const mediCal = /medi[\s-]?cal/i.test(t);
  const homeless = /\bhomeless|unhoused|shelter\b/i.test(t);
  const calfresh = /cal\s?fresh|food stamps|\bEBT\b|\bSNAP\b/i.test(t);
  let proof: Proof = 'NONE';
  if (/pay\s?stubs?|paycheck/i.test(t)) proof = 'PAY_STUBS';
  else if (/tax return|w-?2|1099/i.test(t)) proof = 'TAX_RETURN';
  else if (/employer letter|letter from (?:her|his|their) (?:employer|boss)/i.test(t)) proof = 'EMPLOYER_LETTER';
  else if (/benefit letter|award letter|social security|unemployment/i.test(t)) proof = 'BENEFIT_LETTER';
  else if (/signed statement|self[- ]attest/i.test(t)) proof = 'SELF_ATTESTATION';
  if (/\bno (documents|docs|paperwork|pay\s?stubs|proof)\b/i.test(t)) proof = 'NONE';
  if (proof === 'NONE' && income != null && !/\bno (documents|docs|paperwork|proof)\b/i.test(t) && /brought|has|with|sent/i.test(t)) {
    proof = 'SELF_ATTESTATION';
  }

  const serviceType = /\bER\b|emergency/i.test(t)
    ? 'ER'
    : /admitted|inpatient|surgery|stayed|nights?/i.test(t)
      ? 'INPATIENT'
      : /clinic|check-?up/i.test(t)
        ? 'CLINIC'
        : 'OUTPATIENT';

  return {
    first,
    last,
    household,
    income,
    incomeText,
    proof,
    mediCal,
    homeless,
    calfresh,
    billedCents,
    serviceType,
    savings: savingsM ? money(savingsM[1], savingsM[2]) : null,
  };
}
