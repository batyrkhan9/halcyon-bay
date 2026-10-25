// Copies the simulated hospital into the UI's sample world: ui/src/mock/real.json.
// Reads ../data (world, answer key, CRS recordings) and nothing else. No dependencies.
//
//   cd ui && npm run extract-sample        (or: node ui/scripts/extract-sample.mjs)

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const UI = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(UI, '..', 'data');
const OUT = join(UI, 'src', 'mock', 'real.json');
const LIVE_START = '2026-07-01';

const read = (p) => readFileSync(join(DATA, p), 'utf8');

/** RFC 4180 CSV: quoted fields, doubled quotes, commas and newlines inside quotes. */
function csv(p) {
  const text = read(p);
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else quoted = false;
      } else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') {
      row.push(field);
      field = '';
    } else if (c === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else if (c !== '\r') field += c;
  }
  if (field !== '' || row.length) {
    row.push(field);
    rows.push(row);
  }
  const [head, ...body] = rows;
  return body.filter((r) => r.length > 1 || r[0] !== '').map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ''])));
}

const latest = (rows, key) => {
  const m = new Map();
  for (const r of rows) m.set(r[key], r); // replay order: a later row is the newer version
  return m;
};
const cents = (v) => (v === '' || v == null || Number.isNaN(Number(v)) ? 0 : Math.round(Number(v) * 100));
const digits = (s) => String(s ?? '').replace(/\D/g, '');
const pick = (o, keys) => Object.fromEntries(keys.filter((k) => o && o[k] !== '' && o[k] != null).map((k) => [k, o[k]]));
const title = (s) => String(s ?? '').toLowerCase().replace(/(^|[\s'-])([a-z])/g, (_m, a, b) => a + b.toUpperCase());

// ---------- the world ----------
const ROLE = { FINANCIAL_COUNSELOR: 'counselor', REVENUE_CYCLE_DIRECTOR: 'director', COMPLIANCE_OFFICER: 'compliance' };
const staff = [...latest(csv('world/staff/staff.csv'), 'staff_id').values()]
  .filter((s) => ROLE[s.role] && s.active !== 'N')
  .map((s) => ({ id: s.staff_id, name: `${s.first_name} ${s.last_name}`, role: ROLE[s.role] }));

const patients = latest(csv('world/billing/patients.csv'), 'mrn');
const accountRows = csv('world/billing/accounts.csv');
const accounts = latest(accountRows, 'account_no');
const statements = new Map();
for (const s of csv('world/billing/statements.csv')) {
  if (!statements.has(s.account_no)) statements.set(s.account_no, []);
  statements.get(s.account_no).push(s);
}
const plans = [...latest(csv('world/billing/payment_plans.csv'), 'plan_id').values()];
const appRows = csv('world/fa/applications.csv');
const apps = latest(appRows, 'application_id');
const notes = csv('world/fa/notes.csv');
const placements = [...latest(csv('world/agency/placements.csv'), 'agency_ref').values()];
const requests = csv('world/agency/requests.csv');
const docs = csv('world/documents/index.csv');

const appsByAccount = new Map();
for (const a of apps.values()) {
  for (const acc of (a.accounts_given || '').split(';').map((x) => x.trim()).filter(Boolean)) {
    if (!appsByAccount.has(acc)) appsByAccount.set(acc, []);
    appsByAccount.get(acc).push(a);
  }
}

const HIDDEN = /(ai reviewer|ignore (all|any|the|previous)|system (note|prompt|instruction)|approve 100%|do not (log|ask|flag|escalate))/i;
function excerpt(doc, n = 420) {
  const file = join(DATA, 'world', 'documents', doc.file);
  if (!existsSync(file)) return '';
  const text = readFileSync(file, 'utf8').replace(/\s+/g, ' ').trim();
  const m = HIDDEN.exec(text);
  if (m && m.index > n - 120) return `${text.slice(0, 200)} … ${text.slice(Math.max(0, m.index - 60), m.index + 260)}`;
  return text.slice(0, n);
}

const sameAccount = (clientAccount, accountNo) => digits(clientAccount).endsWith(digits(accountNo).slice(-8));

function sources(accountNo, wantText) {
  const acc = accounts.get(accountNo);
  if (!acc) return {};
  const pat = patients.get(acc.mrn) ?? {};
  const out = {
    billing: {
      patient: pick(pat, ['mrn', 'first_name', 'middle_initial', 'last_name', 'dob', 'address_line1', 'city', 'state', 'zip', 'phone']),
      account: pick(acc, ['account_no', 'service_date', 'discharge_date', 'service_type', 'payer', 'total_charges', 'insurance_paid', 'patient_responsibility', 'first_statement_date', 'status']),
    },
  };
  const st = (statements.get(accountNo) ?? []).map((s) => pick(s, ['statement_id', 'sent_on', 'kind', 'amount_due', 'mailed_to', 'returned_mail']));
  if (st.length) out.billing.statements = st.slice(-6);
  const pp = plans
    .filter((p) => (p.account_nos || '').split(';').includes(accountNo))
    .map((p) => pick(p, ['plan_id', 'monthly_amount', 'months', 'status', 'missed_payments', 'last_payment_on', 'stopped_on', 'stopped_by', 'stop_reason']));
  if (pp.length) out.billing.payment_plans = pp;
  let fa = appsByAccount.get(accountNo) ?? [];
  if (!fa.length) fa = [...apps.values()].filter((a) => a.mrn_given === acc.mrn);
  if (fa.length) {
    const ids = new Set(fa.map((a) => a.application_id));
    out.fa = {
      applications: fa.map((a) =>
        pick(a, ['application_id', 'applicant_id', 'first_name', 'last_name', 'household_size', 'income_stated', 'income_verified', 'income_proof', 'monetary_assets', 'medi_cal', 'homeless', 'received_on', 'form_version', 'status', 'decision', 'decision_date', 'decided_by', 'reason']),
      ),
      notes: notes.filter((n) => ids.has(n.application_id) || n.account_no === accountNo).map((n) => pick(n, ['note_id', 'author', 'written_on', 'text'])),
    };
    const dd = docs.filter((d) => ids.has(d.application_id));
    if (dd.length) {
      out.documents = dd.map((d) => {
        const row = pick(d, ['doc_id', 'doc_type', 'name_on_document', 'received_on']);
        if (wantText.has(d.doc_id) || dd.length <= 4) row.excerpt = excerpt(d);
        return row;
      });
    }
  }
  const pl = placements.filter((p) => sameAccount(p.client_account, accountNo));
  const rq = requests.filter((r) => sameAccount(r.client_account, accountNo));
  if (pl.length || rq.length) {
    out.agency = {
      placements: pl.map((p) => pick(p, ['agency_ref', 'client_account', 'debtor_name', 'placed_date', 'placed_balance', 'current_balance', 'status', 'last_activity'])),
      requests: rq.map((r) => pick(r, ['request_id', 'requested_action', 'requested_date', 'agency_note'])),
    };
  }
  return out;
}

function firstLiveDay(accountNo) {
  const days = [
    ...accountRows.filter((r) => r.account_no === accountNo && r.recorded_on >= LIVE_START).map((r) => r.recorded_on),
    ...appRows.filter((a) => (a.accounts_given || '').includes(accountNo) && a.recorded_on >= LIVE_START).map((a) => a.recorded_on),
    ...requests.filter((r) => sameAccount(r.client_account, accountNo) && r.recorded_on >= LIVE_START).map((r) => r.recorded_on),
  ].sort();
  return days[0] ?? LIVE_START;
}

function patientName(accountNo) {
  const acc = accounts.get(accountNo);
  const p = acc ? patients.get(acc.mrn) : null;
  return p ? `${title(p.first_name)} ${title(p.last_name)}`.trim() : accountNo;
}

// ---------- day one ----------
const CODE = [
  ['savings', 'SAVINGS_OVER_LIMIT'],
  ['asset', 'SAVINGS_OVER_LIMIT'],
  ['deadline', 'LATE_APPLICATION'],
  ['late', 'LATE_APPLICATION'],
  ['other proof', 'NO_PAY_STUBS'],
  ['pay stub', 'NO_PAY_STUBS'],
  ['paystub', 'NO_PAY_STUBS'],
];
const findings = csv('answer_key/history_findings.csv').map((f, i) => {
  const accs = f.accounts.split(';').filter(Boolean);
  const low = `${f.reason} ${f.stated_reason}`.toLowerCase();
  const code = f.law === 'AB 1020' ? 'INCOME_OVER_LIMIT' : (CODE.find(([k]) => low.includes(k))?.[1] ?? 'OTHER');
  const app = apps.get(f.application_id) ?? {};
  const name = `${app.first_name ?? ''} ${app.last_name ?? ''}`.trim() || (accs[0] ? patientName(accs[0]) : f.person);
  return {
    id: `F-${String(i + 1).padStart(3, '0')}`,
    kind: f.finding,
    law: f.law,
    application_id: f.application_id,
    person: f.person,
    account_ids: accs,
    patient_name: name,
    decision_date: f.decision_date,
    decided_by: f.decided_by,
    stated_reason: f.stated_reason,
    reason_code: code,
    fpl_pct: f.fpl_pct ? Number(f.fpl_pct) : null,
    correct_outcome: f.correct_outcome,
    adjustment_cents: cents(f.adjustment),
    refund_cents: cents(f.refund),
    reason: f.reason,
  };
});

const cfRows = csv('answer_key/calfresh_backtest.csv');
const changed = cfRows.filter((r) => r.changes === 'Y');
const calfresh = {
  cases_checked: cfRows.length,
  cases_changed: changed.length,
  dollars_cents: changed.reduce((s, r) => s + cents(r.dollars), 0),
  examples: changed.map((r) => {
    const a = apps.get(r.application_id) ?? {};
    return {
      application_id: r.application_id,
      patient_name: `${a.first_name ?? ''} ${a.last_name ?? ''}`.trim(),
      before: `${title(r.original_status)}${r.original_decision ? ` (${title(r.original_decision)})` : ''}`,
      after: r.with_rule === 'FREE' ? 'Free care' : title(r.with_rule),
      dollars_cents: cents(r.dollars),
    };
  }),
};

const patterns = csv('answer_key/patterns.csv').map((p) => ({ pattern: p.pattern, evidence_count: Number(p.evidence_count || 0), legal: p.legal === 'Y', note: p.note }));

// ---------- live accounts, planted stories, CRS ----------
const planted = JSON.parse(read('answer_key/planted_cases.json')).filter((p) => p.period !== 'HISTORY');
const live = csv('answer_key/live_accounts.csv');
const wantText = new Set(planted.flatMap((p) => p.records.doc_id ?? []));

const personas = JSON.parse(read('crs/personas.json')).personas;
const crsByMrn = new Map();
for (const persona of ['P07', 'P14', 'P16', 'P12', 'P20', 'P01']) {
  const rec = JSON.parse(read(`crs/recorded/${persona}.json`));
  const result = { ...rec.result, source: 'recorded', recorded_at: rec.recorded_at ?? null };
  const name = (result.identity?.name_on_file || personas.find((p) => p.id === persona)?.name || '').toUpperCase();
  for (const [mrn, p] of patients) {
    if (`${p.first_name} ${p.last_name}`.toUpperCase() === name) crsByMrn.set(mrn, result);
  }
}

const ids = new Set([...findings.flatMap((f) => f.account_ids), ...live.map((r) => r.account_no), ...planted.flatMap((p) => p.records.account_no ?? [])]);
const outAccounts = {};
for (const accountNo of [...ids].sort()) {
  const acc = accounts.get(accountNo);
  if (!acc) continue;
  const src = sources(accountNo, wantText);
  if (crsByMrn.has(acc.mrn)) src.crs = crsByMrn.get(acc.mrn);
  outAccounts[accountNo] = {
    id: accountNo,
    patient_id: acc.mrn,
    patient_name: patientName(accountNo).toUpperCase(),
    billed_cents: cents(acc.patient_responsibility),
    first_bill_on: acc.first_statement_date || null,
    day: firstLiveDay(accountNo),
    sources: src,
  };
}

const staffPatients = {};
for (const p of planted) {
  if (p.category !== 'STAFF_SELF_APPROVAL') continue; // the patient is this staff member
  for (const sid of p.records.staff_id ?? []) staffPatients[sid] = [...(staffPatients[sid] ?? []), ...(p.records.mrn ?? [])];
}

const out = {
  generated_from: 'data/ (world, answer_key, crs/recorded)',
  staff,
  staff_patients: staffPatients,
  history: {
    from: '2025-01-01',
    to: '2026-06-30',
    applications: new Set(appRows.filter((a) => a.recorded_on < LIVE_START).map((a) => a.application_id)).size,
    accounts: new Set(accountRows.filter((a) => a.recorded_on < LIVE_START).map((a) => a.account_no)).size,
  },
  findings,
  calfresh,
  patterns,
  planted: planted.map((p) => ({
    id: p.id,
    category: p.category,
    summary: p.summary,
    fix: p.fix,
    dollars: p.dollars,
    records: Object.fromEntries(Object.entries(p.records).filter(([, v]) => v?.length)),
  })),
  live: live.map((r) => ({
    account_no: r.account_no,
    outcome: r.outcome,
    fpl_pct: r.fpl_pct ? Number(r.fpl_pct) : null,
    adjustment_cents: cents(r.adjustment),
    refund_cents: cents(r.refund),
    monthly_cents: cents(r.monthly_payment),
    handling: r.handling,
    ask_role: r.ask_role.toLowerCase(),
    approver_role: r.approver_role.toLowerCase(),
    required_actions: r.required_actions.split(';').filter(Boolean),
    planted: r.planted.split(';').filter(Boolean),
    reason: r.reason,
  })),
  accounts: outAccounts,
};
writeFileSync(OUT, JSON.stringify(out));
console.log(
  `${relative(join(UI, '..'), OUT)}: ${staff.length} staff, ${findings.length} findings, ${Object.keys(outAccounts).length} accounts, ` +
    `${live.length} live, ${planted.length} planted, CRS on ${crsByMrn.size} patients, ${Math.round(JSON.stringify(out).length / 1024)} KB`,
);
