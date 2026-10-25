import { useState, type ReactNode } from 'react';
import { isFact, type Evidence } from '../api/types';
import { day, dollars, DOLLAR_KEYS, humanize, isIsoDay, isIsoTs, maskSsn, money } from '../lib/format';
import { usePeople } from '../lib/people';
import { IconAlert, IconDoc } from './icons';
import { Badge, cx } from './ui';

type Obj = Record<string, unknown>;
const ENUM_KEYS = new Set(['status', 'service_type', 'income_proof', 'proof', 'doc_type', 'requested_action', 'kind', 'decision', 'result', 'reason', 'outcome', 'role', 'source']);
const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
const isEmpty = (v: unknown) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0) || (isObj(v) && Object.keys(v).length === 0);

/** One value from a source system, formatted by what its key means. */
export function fieldValue(key: string, v: unknown, nameOf?: (id: string) => string): ReactNode {
  if (v === null || v === undefined || v === '') return <span className="text-ink3">—</span>;
  const k = key.toLowerCase();
  if (k.includes('ssn')) return <span className="font-mono">{maskSsn(v)}</span>;
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (k.endsWith('_cents') && typeof v === 'number') return <span className="tnum">{money(v)}</span>;
  if (DOLLAR_KEYS.has(k) && (typeof v === 'number' || (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v)))) return <span className="tnum">{dollars(v)}</span>;
  if (k === 'pct_of_poverty' || k === 'fpl_pct') return <span className="tnum">{Number(v).toFixed(1)}%</span>;
  if (typeof v === 'string' && (v === 'Y' || v === 'N') && k.length > 1) return v === 'Y' ? 'Yes' : 'No';
  if (typeof v === 'string' && isIsoDay(v)) return day(v);
  if (typeof v === 'string' && ENUM_KEYS.has(k) && /^[A-Z][A-Z_]{3,}$/.test(v)) return humanize(v);
  if (typeof v === 'string' && isIsoTs(v)) return new Date(v).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });
  if (typeof v === 'string' && nameOf && /^(decided_by|author|by|stopped_by|answered_by)$/.test(k) && /^S-\d+$/.test(v)) return nameOf(v);
  if (typeof v === 'string' && /(^|_)(id|ref|no|account|mrn|request_id|case_number)$/.test(k)) return <span className="font-mono text-[0.92em]">{v}</span>;
  if (typeof v === 'number') return <span className="tnum">{v.toLocaleString('en-US')}</span>;
  if (Array.isArray(v) && v.every((x) => typeof x !== 'object')) return v.join(', ');
  if (typeof v === 'object') return <DataView value={v} />;
  return String(v);
}

/** Definition list for a flat-ish object. */
export function Fields({ data, omit = [], cols = 2 }: { data: Obj; omit?: string[]; cols?: 1 | 2 | 3 }) {
  const { nameOf } = usePeople();
  const entries = Object.entries(data).filter(([k, v]) => !omit.includes(k) && !(isObj(v) || (Array.isArray(v) && v.some(isObj))));
  const nested = Object.entries(data).filter(([k, v]) => !omit.includes(k) && (isObj(v) || (Array.isArray(v) && v.some(isObj))));
  return (
    <div>
      {entries.length > 0 && (
        <dl className={cx('grid gap-x-8 gap-y-3', cols === 1 ? 'grid-cols-1' : cols === 3 ? 'grid-cols-2 lg:grid-cols-3' : 'grid-cols-2')}>
          {entries.map(([k, v]) => (
            <div key={k} className="min-w-0">
              <dt className="text-[0.8125rem] text-ink3">{humanize(k)}</dt>
              <dd className="mt-0.5 break-words text-[0.9875rem] text-ink">{fieldValue(k, v, nameOf)}</dd>
            </div>
          ))}
        </dl>
      )}
      {nested.map(([k, v]) => (
        <div key={k} className="mt-5">
          <div className="mb-2 text-[0.8125rem] font-semibold uppercase tracking-wider text-ink3">{humanize(k)}</div>
          <DataView value={v} />
        </div>
      ))}
    </div>
  );
}

/** Anything else: objects as fields, lists of objects as small tables. */
export function DataView({ value }: { value: unknown }) {
  const { nameOf } = usePeople();
  if (isEmpty(value)) return <span className="text-ink3">None</span>;
  if (Array.isArray(value)) {
    const rows = value.filter(isObj);
    if (!rows.length) return <span>{value.map(String).join(', ')}</span>;
    const keys = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).filter((k) => rows.some((r) => !isEmpty(r[k]) && !isObj(r[k])));
    if (keys.length <= 7) {
      return (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[0.9rem]">
            <thead>
              <tr className="text-[0.75rem] uppercase tracking-wider text-ink3">
                {keys.map((k) => (
                  <th key={k} className="pb-1.5 pr-4 font-semibold">
                    {humanize(k)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-line/70 align-top">
                  {keys.map((k) => (
                    <td key={k} className="py-1.5 pr-4 text-ink">
                      {fieldValue(k, r[k], nameOf)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return (
      <div className="space-y-3">
        {rows.map((r, i) => (
          <div key={i} className="rounded-xl bg-bg px-4 py-3">
            <Fields data={r} />
          </div>
        ))}
      </div>
    );
  }
  if (isObj(value)) return <Fields data={value} />;
  return <span>{fieldValue('', value, nameOf)}</span>;
}

function Card({ title, sub, badge, children, className }: { title: string; sub?: string; badge?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-2xl border border-line bg-surface p-6', className)}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[1.125rem] font-semibold tracking-[-0.01em] text-ink">{title}</h3>
          {sub && <p className="mt-0.5 text-[0.875rem] text-ink3">{sub}</p>}
        </div>
        {badge}
      </header>
      {children}
    </section>
  );
}

const REST = (o: Obj, keys: string[]) => Object.fromEntries(Object.entries(o).filter(([k]) => !keys.includes(k)));

function BillingCard({ data }: { data: Obj }) {
  const patient = isObj(data.patient) ? data.patient : {};
  const account = isObj(data.account) ? data.account : {};
  const known = ['patient', 'account'];
  return (
    <Card title="Billing system" sub="Patient, account and bills, as billing writes them">
      {Object.keys(patient).length > 0 && (
        <div className="mb-5">
          <div className="text-[1.0625rem] font-semibold text-ink">{String(patient.name ?? '')}</div>
          <Fields data={REST(patient, ['name'])} />
        </div>
      )}
      {Object.keys(account).length > 0 && (
        <div className="rounded-xl bg-bg px-4 py-4">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-mono text-[0.9rem] text-ink2">{String(account.account_no ?? '')}</span>
            {account.patient_responsibility != null && (
              <span className="text-[0.9375rem] text-ink2">
                Patient owes <b className="tnum text-[1.25rem] font-semibold text-ink">{dollars(account.patient_responsibility)}</b>
              </span>
            )}
          </div>
          <Fields data={REST(account, ['account_no', 'patient_responsibility'])} />
        </div>
      )}
      <div className="mt-2">
        <Fields data={REST(data, known)} />
      </div>
    </Card>
  );
}

function FaCard({ data }: { data: Obj }) {
  const { nameOf } = usePeople();
  const apps = Array.isArray(data.applications) ? data.applications.filter(isObj) : [];
  const notes = Array.isArray(data.notes) ? data.notes.filter(isObj) : [];
  return (
    <Card title="Financial assistance" sub="Applications as the patient wrote them, and staff notes">
      {apps.length === 0 && <p className="text-ink3">No application on file.</p>}
      <div className="space-y-4">
        {apps.map((a, i) => {
          const status = String(a.status ?? '');
          return (
            <div key={i} className="rounded-xl bg-bg px-4 py-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="font-mono text-[0.9rem] text-ink2">{String(a.application_id ?? 'Application')}</span>
                {status && <Badge tone={status === 'DENIED' ? 'danger' : status === 'APPROVED' ? 'accent' : status === 'NEEDS_INFO' ? 'warn' : 'neutral'}>{humanize(status)}</Badge>}
                {a.decision_date != null && (
                  <span className="text-[0.875rem] text-ink3">
                    {day(String(a.decision_date))}
                    {a.decided_by ? ` by ${nameOf(String(a.decided_by))}` : ''}
                  </span>
                )}
              </div>
              {a.reason != null && a.reason !== '' && (
                <p className="mb-3 text-[1rem] text-ink">
                  <span className="text-ink3">Reason as typed: </span>“{String(a.reason)}”
                </p>
              )}
              <Fields data={REST(a, ['application_id', 'status', 'decision_date', 'decided_by', 'reason'])} cols={3} />
            </div>
          );
        })}
      </div>
      {notes.length > 0 && (
        <div className="mt-5">
          <div className="mb-2 text-[0.8125rem] font-semibold uppercase tracking-wider text-ink3">Notes</div>
          <ul className="space-y-2">
            {notes.map((n, i) => (
              <li key={i} className="border-l-2 border-line pl-3">
                <p className="text-[1rem] text-ink">“{String(n.text ?? '')}”</p>
                <p className="text-[0.8125rem] text-ink3">
                  {n.author ? nameOf(String(n.author)) : 'Staff'} · {n.written_on ? day(String(n.written_on)) : ''}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-3">
        <Fields data={REST(data, ['applications', 'notes'])} />
      </div>
    </Card>
  );
}

const ACTION_WORDS: Record<string, string> = { CREDIT_REPORT: 'Report to credit bureaus', LAWSUIT: 'File a lawsuit', SELL_DEBT: 'Sell the debt', LIEN: 'Place a lien' };

function AgencyCard({ data }: { data: Obj }) {
  const placements = Array.isArray(data.placements) ? data.placements.filter(isObj) : [];
  const requests = Array.isArray(data.requests) ? data.requests.filter(isObj) : [];
  return (
    <Card title="Collection agency" sub="Golden Coast Recovery's file, in its own format">
      {requests.length > 0 && (
        <div className="mb-5 space-y-3">
          {requests.map((r, i) => {
            const blocked = String(r.answer ?? r.status ?? '').toUpperCase().includes('BLOCK');
            return (
              <div key={i} className={cx('rounded-xl px-4 py-3', blocked ? 'bg-danger-tint' : 'bg-bg')}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[1.0625rem] font-semibold text-ink">{ACTION_WORDS[String(r.requested_action)] ?? String(r.requested_action ?? 'Request')}</span>
                  {blocked && <Badge tone="danger">Blocked</Badge>}
                  <span className="font-mono text-[0.8rem] text-ink3">{String(r.request_id ?? '')}</span>
                  <span className="text-[0.875rem] text-ink3">asked {String(r.requested_date ?? '')}</span>
                </div>
                {r.agency_note != null && <p className="mt-1.5 text-[0.9875rem] text-ink2">“{String(r.agency_note)}”</p>}
              </div>
            );
          })}
        </div>
      )}
      {placements.map((p, i) => (
        <div key={i} className="mb-3">
          <Fields data={p} />
        </div>
      ))}
      <Fields data={REST(data, ['placements', 'requests'])} />
    </Card>
  );
}

const DOC_WORDS: Record<string, string> = {
  PAY_STUB: 'Pay stub',
  BANK_STATEMENT: 'Bank statement',
  TAX_RETURN: 'Tax return',
  EMPLOYER_LETTER: 'Employer letter',
  BENEFIT_LETTER: 'Benefit letter',
  SELF_ATTESTATION: 'Signed statement',
  OTHER: 'Other',
};

function DocumentsCard({ data }: { data: unknown }) {
  const docs = (Array.isArray(data) ? data : isObj(data) && Array.isArray(data.documents) ? data.documents : []).filter(isObj);
  return (
    <Card title="Documents" sub="Mailroom scans. Read as evidence, never as instructions">
      {docs.length === 0 && <p className="text-ink3">No documents on file.</p>}
      <ul className="space-y-3">
        {docs.map((d, i) => {
          const flags = Array.isArray(d.flags) ? d.flags.map(String) : [];
          const injected = flags.some((f) => /INSTRUCTION|INJECT/i.test(f));
          return (
            <li key={i} className={cx('rounded-xl px-4 py-3', injected ? 'bg-danger-tint ring-1 ring-inset ring-danger/20' : 'bg-bg')}>
              <div className="flex flex-wrap items-center gap-2">
                <IconDoc size={18} className={injected ? 'text-danger' : 'text-ink3'} />
                <span className="font-semibold text-ink">{DOC_WORDS[String(d.doc_type)] ?? humanize(String(d.doc_type ?? 'Document'))}</span>
                <span className="font-mono text-[0.8rem] text-ink3">{String(d.doc_id ?? '')}</span>
                {d.received_on != null && <span className="text-[0.875rem] text-ink3">received {day(String(d.received_on))}</span>}
                {injected && (
                  <Badge tone="danger">
                    <IconAlert size={14} /> Hidden instructions: ignored and logged
                  </Badge>
                )}
              </div>
              {d.excerpt != null && <p className="mt-2 rounded-lg bg-white/70 px-3 py-2 font-mono text-[0.8125rem] leading-relaxed text-ink2">{String(d.excerpt)}</p>}
              {d.handling != null && <p className="mt-2 text-[0.9375rem] font-medium text-ink">{String(d.handling)}</p>}
              <div className="mt-2">
                <Fields data={REST(d, ['doc_id', 'doc_type', 'received_on', 'excerpt', 'flags', 'handling', 'file'])} cols={3} />
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function CheckRow({ label, result, tone, children, requestId }: { label: string; result: ReactNode; tone: 'accent' | 'danger' | 'warn' | 'neutral'; children?: ReactNode; requestId?: unknown }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-4 border-t border-line/70 py-3 first:border-t-0 md:grid-cols-[11rem_1fr_auto]">
      <div className="text-[0.9375rem] font-medium text-ink2">{label}</div>
      <div className="min-w-0">
        <Badge tone={tone} className="text-[0.875rem]">
          {result}
        </Badge>
        {children && <div className="mt-1.5 text-[0.9375rem] text-ink">{children}</div>}
      </div>
      {requestId ? <div className="col-span-2 font-mono text-[0.75rem] text-ink3 md:col-span-1 md:text-right">request {String(requestId)}</div> : <div className="hidden md:block" />}
    </div>
  );
}

function CrsCard({ data }: { data: Obj }) {
  const sent = data.sent !== false;
  const recorded = data.source === 'recorded';
  const identity = isObj(data.identity) ? data.identity : {};
  const bankruptcy = isObj(data.bankruptcy) ? data.bankruptcy : null;
  const contact = isObj(data.contact) ? data.contact : null;
  const liens = Array.isArray(data.liens_judgments) ? data.liens_judgments : [];
  const live = data.source === 'live';
  const badge = !sent ? (
    <Badge>Not sent</Badge>
  ) : live ? (
    <span className="inline-flex items-center gap-2 rounded-full bg-accent px-3 py-1 text-[0.8125rem] font-semibold text-white">
      <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-white" />
      Live from the CRS sandbox
    </span>
  ) : recorded ? (
    <Badge tone="warn">Recorded CRS sandbox answer</Badge>
  ) : (
    <Badge>CRS sandbox</Badge>
  );
  const idResult = String(identity.result ?? 'NOT_CHECKED');
  return (
    <Card
      title="CRS sandbox"
      sub={
        sent
          ? `${recorded ? 'Recorded' : 'Checked'} ${data.recorded_at || data.checked_at ? new Date(String(data.recorded_at || data.checked_at)).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' }) : ''}${data.persona ? ` · sandbox persona ${String(data.persona)}` : ''}`
          : 'Identity, deceased, bankruptcy and contact checks'
      }
      badge={badge}
    >
      {!sent ? (
        <p className="text-[1rem] leading-relaxed text-ink2">
          Not one of the 20 sandbox personas, so the client refused to send anything to a real bureau. That means no information, not a bad result.
        </p>
      ) : (
        <div>
          <CheckRow label="Identity" result={humanize(idResult)} tone={idResult === 'PASS' ? 'accent' : idResult === 'FAIL' ? 'danger' : 'warn'} requestId={identity.request_id}>
            {Array.isArray(identity.problems) && identity.problems.length > 0 && <div className="text-danger">{identity.problems.map(String).map(humanize).join(', ')}</div>}
            {identity.name_on_file != null && <div>{String(identity.name_on_file)}</div>}
            {identity.address_on_file != null && <div className="text-ink2">{String(identity.address_on_file)}</div>}
          </CheckRow>
          <CheckRow label="Deceased" result={data.deceased ? 'Reported deceased' : data.deceased === false ? 'No' : 'Not checked'} tone={data.deceased ? 'danger' : 'neutral'}>
            {data.deceased ? 'Collections stop; the director handles the estate.' : null}
          </CheckRow>
          <CheckRow
            label="Bankruptcy"
            result={bankruptcy ? (bankruptcy.open ? 'Open bankruptcy' : 'None open') : 'Not checked'}
            tone={bankruptcy?.open ? 'danger' : 'neutral'}
            requestId={bankruptcy?.request_id}
          >
            {bankruptcy &&
              Array.isArray(bankruptcy.records) &&
              bankruptcy.records.filter(isObj).map((r, i) => (
                <div key={i}>
                  <b className="font-semibold">Chapter {String(r.chapter ?? '?')}</b>, {humanize(String(r.status ?? ''))} · filed {r.filed_on ? day(String(r.filed_on)) : '—'}
                  <div className="text-ink2">
                    {String(r.court ?? '')} · case <span className="font-mono text-[0.9em]">{String(r.case_number ?? '')}</span>
                  </div>
                  {bankruptcy.open ? <div className="mt-1 font-medium text-ink">Automatic stay: no collection activity at all.</div> : null}
                </div>
              ))}
          </CheckRow>
          <CheckRow label="Liens & judgments" result={liens.length ? `${liens.length} found` : 'None'} tone="neutral" />
          <CheckRow label="Contact" result={contact ? (contact.found ? 'Found' : 'Not found') : 'Not checked'} tone={contact?.found ? 'accent' : 'neutral'} requestId={contact?.request_id}>
            {contact?.found ? (
              <>
                {contact.address != null && <div>{String(contact.address)}</div>}
                {contact.phone != null && <div className="text-ink2">{String(contact.phone)}</div>}
              </>
            ) : null}
          </CheckRow>
        </div>
      )}
      <p className="mt-4 border-t border-line/70 pt-3 text-[0.8125rem] text-ink3">
        Used only to help a patient or stop a collection, never to deny help. Credit scores are thrown away before anything sees them.
      </p>
    </Card>
  );
}

const SOURCE_ORDER = ['judge_box', 'billing', 'fa', 'financial_assistance', 'documents', 'agency', 'staff', 'crs'];

/** What every system says about the account. Known systems get their own layout; anything else renders generically. */
export function Sources({ sources }: { sources: Record<string, unknown> }) {
  const keys = Object.keys(sources ?? {}).sort((a, b) => {
    const ia = SOURCE_ORDER.indexOf(a);
    const ib = SOURCE_ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
  if (!keys.length) return <p className="text-ink3">No source data yet. Sync fills this in.</p>;
  const crs = isObj(sources.crs) ? sources.crs : null;
  const crsLive = crs && crs.sent !== false; // a sent check (live or recorded) gets the full-width card
  return (
    <div className="space-y-5">
      {crsLive && <CrsCard data={crs} />}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {keys.map((k) => {
          const v = sources[k];
          if (k === 'crs') return crsLive ? null : isObj(v) ? <CrsCard key={k} data={v} /> : null;
          if (k === 'billing' && isObj(v)) return <BillingCard key={k} data={v} />;
          if ((k === 'fa' || k === 'financial_assistance') && isObj(v)) return <FaCard key={k} data={v} />;
          if (k === 'agency' && isObj(v)) return <AgencyCard key={k} data={v} />;
          if (k === 'documents') return <DocumentsCard key={k} data={v} />;
          if (k === 'judge_box' && isObj(v)) {
            return (
              <Card key={k} title="Judge box" sub="What the judge typed, in plain English" className="xl:col-span-2">
                <p className="text-[1.1875rem] leading-relaxed text-ink">“{String(v.text ?? '')}”</p>
              </Card>
            );
          }
          if (k === 'staff' && isObj(v)) {
            return (
              <Card key={k} title="Staff list" sub="HR export" badge={<Badge tone="warn">This patient is staff</Badge>}>
                <Fields data={v} />
              </Card>
            );
          }
          return (
            <Card key={k} title={humanize(k)}>
              {typeof v === 'string' ? <p className="text-ink2">{v}</p> : <DataView value={v} />}
            </Card>
          );
        })}
      </div>
    </div>
  );
}

/** A proposal's evidence. Reader facts show their exact quote and link to the document they came from. */
export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  const facts = evidence.filter(isFact);
  const [open, setOpen] = useState(facts.length > 0);
  return (
    <div className="mt-4">
      <button type="button" onClick={() => setOpen((o) => !o)} className="text-[0.9375rem] font-medium text-accent hover:underline" aria-expanded={open}>
        {open ? 'Hide' : 'Show'} the evidence ({evidence.length})
      </button>
      {open && (
        <ul className="mt-3 space-y-2">
          {evidence.map((e, i) =>
            isFact(e) ? (
              <li key={i} className="rounded-xl bg-bg px-4 py-3">
                <div className="text-[0.9875rem] font-medium text-ink">{e.fact}</div>
                <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <q className="font-mono text-[0.8125rem] text-ink2 [quotes:none]">“{e.quote}”</q>
                  {e.document_id ? (
                    <a href={`#doc-${e.document_id}`} className="font-mono text-[0.78rem] text-accent hover:underline">
                      {e.document_id} ↓
                    </a>
                  ) : (
                    <span className="text-[0.78rem] text-ink3">staff answer</span>
                  )}
                </div>
              </li>
            ) : (
              <li key={i} className="rounded-xl bg-bg px-4 py-3">
                {e.source != null && <div className="mb-1.5 text-[0.75rem] font-semibold uppercase tracking-wider text-ink3">{humanize(String(e.source))}</div>}
                <Fields data={REST(e, ['source'])} cols={3} />
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}
