import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, Denied, errorText, type Source } from '../api/client';
import type { DiscoveryFinding } from '../api/types';
import { GatewayRefusal, useDecision, type Refusal } from '../components/decisions';
import { IconArrowRight, IconCheck, IconX } from '../components/icons';
import { Badge, Button, CountUp, cx, ErrorNote, Kbd, Loading, Page, SampleTag, Section } from '../components/ui';
import { count, day, money, ROLE_LABEL } from '../lib/format';
import { usePeople } from '../lib/people';
import { useResource } from '../lib/useResource';

const CODE_WORDS: Record<string, string> = {
  SAVINGS_OVER_LIMIT: 'Savings',
  LATE_APPLICATION: 'Late application',
  NO_PAY_STUBS: 'No pay stubs',
  INCOME_OVER_LIMIT: 'Over income',
};

export default function Discovery() {
  const r = useResource(() => api.discovery(), [], { intervalMs: 6000 });
  const { current, firstWithRole, setCurrent, people } = usePeople();
  const [bulk, setBulk] = useState<{ done: number; total: number } | null>(null);
  const [bulkRefusal, setBulkRefusal] = useState<Refusal | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const source: Source = r.source ?? 'core';

  if (!r.data) {
    return (
      <Page eyebrow="Day one">
        {r.error ? <ErrorNote>{r.error}</ErrorNote> : <Loading label="Reading 18 months of history" />}
      </Page>
    );
  }
  const d = r.data;
  const denials = d.findings.filter((f) => f.kind === 'ILLEGAL_DENIAL');
  const headline = denials.filter((f) => f.law === d.law.id);
  const otherLaw = denials.filter((f) => f.law !== d.law.id);
  const headlineCents = headline.reduce((s, f) => s + f.adjustment_cents + f.refund_cents, 0);
  const otherCents = otherLaw.reduce((s, f) => s + f.adjustment_cents + f.refund_cents, 0);
  const same = d.findings.filter((f) => f.kind === 'ILLEGAL_REASON_SAME_OUTCOME');
  const open = denials.filter((f) => f.proposal?.status === 'PROPOSED');
  const approved = denials.filter((f) => f.proposal && (f.proposal.status === 'POSTED' || f.proposal.status === 'APPROVED'));
  const movedCents = approved.reduce((s, f) => s + f.adjustment_cents + f.refund_cents, 0);
  const compliance = firstWithRole('compliance');
  const isCompliance = current?.role === 'compliance';
  const complianceKey = compliance ? people.indexOf(compliance) + 1 : 3;

  const approveAll = async () => {
    if (!current) return;
    setBulkRefusal(null);
    setBulkError(null);
    const queue = open.map((f) => f.proposal!).filter(Boolean);
    setBulk({ done: 0, total: queue.length });
    for (let i = 0; i < queue.length; i++) {
      try {
        await api.decide(queue[i].id, current.id, true, 'AB 2297 reversal, approved from the day-one discovery.', source);
        setBulk({ done: i + 1, total: queue.length });
      } catch (e) {
        if (e instanceof Denied) setBulkRefusal({ reason: e.reason, who: current.name, role: ROLE_LABEL[current.role] ?? current.role, at: new Date(), action: 'approve', target: queue[i].id });
        else setBulkError(errorText(e));
        break;
      }
    }
    setBulk(null);
  };

  return (
    <Page eyebrow={`Day one · learned from ${count(d.history.applications)} applications, ${day(d.history.from)} to ${day(d.history.to)}`} right={<SampleTag source={r.source} endpoint="/discovery" />}>
      <h1 className="max-w-5xl text-hero font-semibold text-ink">
        Found <span className="text-accent">{headline.length} patients</span> denied under rules that changed in January 2025.
      </h1>
      <p className="mt-6 max-w-3xl text-[1.25rem] leading-relaxed text-ink2">
        <b className="font-semibold text-ink">{d.law.name}</b>, in effect since {day(d.law.effective)}: {d.law.text.replace(/^From [A-Za-z]+ \d{1,2}, \d{4}, /, '')} Their income qualifies them. The office's habits didn't change in time.
        {otherLaw.length > 0 && (
          <>
            {' '}
            It also found <b className="font-semibold text-ink">{otherLaw.length} more</b> denied as over income although they were at or under 400% of the poverty level ({[...new Set(otherLaw.map((f) => f.law))].join(', ')}, {money(otherCents, { whole: true })}).
          </>
        )}
      </p>

      <div className="mt-14 grid grid-cols-2 gap-x-10 gap-y-10 xl:grid-cols-[0.8fr_1.35fr_1fr_1fr]">
        <Stat value={headline.length} label="patients to make whole" format={(v) => count(Math.round(v))} />
        <Stat value={headlineCents} label="back to patients, as charity care and refunds" format={(v) => money(Math.round(v), { whole: true })} accent />
        <Stat value={approved.length} label={`reversed so far (${money(movedCents, { whole: true })})`} format={(v) => count(Math.round(v))} />
        <Stat value={d.patterns_flagged} label={`patterns flagged, not learned (${d.patterns_learned} learned)`} format={(v) => count(Math.round(v))} link="/learned" />
      </div>

      <div className={cx('mt-14 flex flex-wrap items-center justify-between gap-5 rounded-2xl px-7 py-6', isCompliance ? 'bg-accent-tint' : 'bg-rail ring-1 ring-inset ring-line')}>
        <div className="max-w-2xl">
          <div className="text-[1.25rem] font-semibold text-ink">{open.length ? `${open.length} reversals are waiting for the compliance officer.` : 'Every reversal has been decided.'}</div>
          <p className="mt-1 text-[1rem] text-ink2">
            How the law applies is a legal question, so only the compliance officer decides. The AI proposed each reversal with the dollars and the evidence; it can't approve any of them.
          </p>
        </div>
        {open.length > 0 &&
          (isCompliance ? (
            <Button tone="primary" size="lg" onClick={() => void approveAll()} disabled={!!bulk}>
              <IconCheck size={20} />
              {bulk ? `Approving ${bulk.done} of ${bulk.total}…` : `Approve all ${open.length} as ${current?.name.split(' ')[0]}`}
            </Button>
          ) : (
            compliance && (
              <Button size="lg" onClick={() => setCurrent(compliance.id)}>
                Act as {compliance.name} <Kbd>{complianceKey}</Kbd>
              </Button>
            )
          ))}
      </div>
      {bulkRefusal && <GatewayRefusal refusal={bulkRefusal} onDismiss={() => setBulkRefusal(null)} />}
      {bulkError && (
        <div className="mt-4">
          <ErrorNote>{bulkError}</ErrorNote>
        </div>
      )}

      <Section className="mt-14" title="The denials" aside="Reason as staff typed it, checked against the law in code">
        <div className="overflow-hidden rounded-2xl border border-line bg-surface">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-line text-[0.8125rem] font-semibold uppercase tracking-wider text-ink3">
                <th className="px-6 py-3.5">Patient</th>
                <th className="px-4 py-3.5">Denied</th>
                <th className="hidden px-4 py-3.5 xl:table-cell">Reason as typed</th>
                <th className="px-4 py-3.5 text-right">Poverty level</th>
                <th className="px-4 py-3.5 text-right">Reversal</th>
                <th className="px-6 py-3.5 text-right">Decision</th>
              </tr>
            </thead>
            <tbody>
              {denials.map((f) => (
                <FindingRow key={f.id} f={f} source={source} />
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {same.length > 0 && (
        <Section className="mt-14" title={`${same.length} more had an illegal reason, but the outcome stands`} aside="Income over 400% of the poverty level">
          <ul className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {same.map((f) => (
              <li key={f.id} className="rounded-2xl border border-line bg-surface px-5 py-4">
                <div className="font-semibold text-ink">{f.patient_name}</div>
                <div className="mt-1 text-[0.9375rem] text-ink2">“{f.stated_reason}”</div>
                <div className="mt-2 text-[0.875rem] text-ink3">
                  {f.fpl_pct?.toFixed(0)}% of poverty · {f.law}: {f.law_text}
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Link to="/learned" className="mt-14 inline-flex items-center gap-2 text-[1.125rem] font-semibold text-accent hover:underline">
        See every pattern it learned from the history <IconArrowRight size={18} />
      </Link>
    </Page>
  );
}

function Stat({ value, label, format, accent, link }: { value: number; label: string; format: (n: number) => string; accent?: boolean; link?: string }) {
  const body = (
    <>
      <div className={cx('tnum text-stat font-semibold', accent ? 'text-accent' : 'text-ink')}>
        <CountUp value={value} format={format} fromZero />
      </div>
      <div className="mt-3 text-[1.0625rem] text-ink2">{label}</div>
    </>
  );
  return link ? (
    <Link to={link} className="group block hover:opacity-80">
      {body}
    </Link>
  ) : (
    <div>{body}</div>
  );
}

function FindingRow({ f, source }: { f: DiscoveryFinding; source: Source }) {
  const { nameOf, current } = usePeople();
  const { decide, busy, refusal, setRefusal, error } = useDecision(source);
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState('');
  const p = f.proposal;
  const status = p?.status;
  const account = f.account_ids[0];
  return (
    <>
      <tr className={cx('border-b border-line/60 align-top last:border-b-0', status === 'POSTED' && 'bg-accent-tint/30')}>
        <td className="px-6 py-4">
          {account ? (
            <Link to={`/accounts/${account}`} className="text-[1.0625rem] font-semibold text-ink hover:text-accent">
              {f.patient_name}
            </Link>
          ) : (
            <span className="text-[1.0625rem] font-semibold text-ink">{f.patient_name}</span>
          )}
          <div className="font-mono text-[0.78rem] text-ink3">
            {f.application_id}
            {account ? ` · ${account}` : ''}
          </div>
        </td>
        <td className="px-4 py-4 text-[0.9375rem]">
          <div className="text-ink">{day(f.decision_date)}</div>
          <div className="text-ink3">by {nameOf(f.decided_by)}</div>
        </td>
        <td className="hidden max-w-xs px-4 py-4 xl:table-cell">
          <Badge tone="danger">{CODE_WORDS[f.reason_code] ?? f.reason_code}</Badge>
          <div className="mt-1.5 text-[0.9375rem] text-ink2">“{f.stated_reason}”</div>
        </td>
        <td className="tnum px-4 py-4 text-right">
          <div className="text-[1.0625rem] font-semibold text-ink">{f.fpl_pct != null ? `${f.fpl_pct.toFixed(0)}%` : '—'}</div>
          <div className="text-[0.875rem] text-ink3">{f.correct_outcome === 'FREE' ? 'free care' : f.correct_outcome === 'DISCOUNT' ? 'discount' : f.correct_outcome.toLowerCase()}</div>
        </td>
        <td className="tnum px-4 py-4 text-right">
          <div className="text-[1.125rem] font-semibold text-ink">{money(f.adjustment_cents)}</div>
          {f.refund_cents > 0 && <div className="text-[0.875rem] text-ink3">+ {money(f.refund_cents)} refund</div>}
        </td>
        <td className="px-6 py-4 text-right">
          {!p ? (
            <span className="text-ink3">—</span>
          ) : status === 'PROPOSED' ? (
            rejecting ? (
              <form
                className="flex justify-end gap-2"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (await decide(p, false, note.trim())) setRejecting(false);
                }}
              >
                <input autoFocus value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why not?" className="h-9 w-40 rounded-lg border border-line px-2.5 text-[0.875rem] outline-none focus:border-accent" />
                <Button tone="danger" type="submit" disabled={busy} className="h-9 px-3">
                  Reject
                </Button>
              </form>
            ) : (
              <div className="flex justify-end gap-1.5">
                <Button tone="quiet" className="h-9 px-3" onClick={() => setRejecting(true)} disabled={busy || !current}>
                  <IconX size={16} />
                </Button>
                <Button tone="primary" className="h-9 px-3.5" onClick={() => void decide(p, true, 'AB 2297 reversal.')} disabled={busy || !current}>
                  <IconCheck size={16} /> Approve
                </Button>
              </div>
            )
          ) : (
            <div className="text-[0.9375rem]">
              <div className={cx('inline-flex items-center gap-1.5 font-semibold', status === 'REJECTED' ? 'text-danger' : 'text-accent-strong')}>
                {status === 'REJECTED' ? <IconX size={16} /> : <IconCheck size={16} />}
                {status === 'REJECTED' ? 'Rejected' : 'Reversed'}
              </div>
              <div className="text-ink3">
                {nameOf(p.decided_by)} · {day(p.decided_on)}
              </div>
            </div>
          )}
        </td>
      </tr>
      {(refusal || error) && (
        <tr>
          <td colSpan={6} className="px-6 pb-5">
            {refusal && <GatewayRefusal refusal={refusal} onDismiss={() => setRefusal(null)} />}
            {error && <p className="text-danger">{error}</p>}
          </td>
        </tr>
      )}
    </>
  );
}
