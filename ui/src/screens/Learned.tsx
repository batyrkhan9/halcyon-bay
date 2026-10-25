import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Source } from '../api/client';
import type { LearnedRule } from '../api/types';
import { GatewayRefusal, useDecision } from '../components/decisions';
import { IconArrowRight, IconCheck, IconShield, IconX } from '../components/icons';
import { Badge, Button, cx, Empty, ErrorNote, Kbd, Loading, Page, SampleTag, Section } from '../components/ui';
import { count, day, money, titleCase } from '../lib/format';
import { usePeople } from '../lib/people';
import { useResource } from '../lib/useResource';

export default function Learned() {
  const r = useResource(() => api.learned(), [], { intervalMs: 6000 });
  const source: Source = r.source ?? 'core';
  const { nameOf } = usePeople();

  if (!r.data) {
    return <Page eyebrow="Learned">{r.error ? <ErrorNote>{r.error}</ErrorNote> : <Loading />}</Page>;
  }
  const { patterns, precedents, rules, rejected } = r.data;
  const pending = rules.filter((x) => x.status === 'PROPOSED');
  const decided = rules.filter((x) => x.status !== 'PROPOSED' && x.status !== 'REJECTED');
  const maxEvidence = Math.max(1, ...patterns.map((p) => p.evidence_count));
  const learned = patterns.filter((p) => p.legal);
  const flagged = patterns.filter((p) => !p.legal);

  return (
    <Page
      eyebrow="Learned"
      title="What it learned, with the evidence."
      lede="Patterns from 18 months of history, precedents from staff corrections, and rules a person approved. All stored, none of it in a prompt. Anything that breaks the law is flagged instead of learned."
      right={<SampleTag source={r.source} endpoint="/learned" />}
    >
      <Section title={pending.length ? `${pending.length} ${pending.length === 1 ? 'rule is' : 'rules are'} waiting for the director` : 'Rules'} aside="Correction → precedent → rule → backtest → a person approves">
        {pending.length === 0 && decided.length === 0 && <Empty>No rules yet. A staff correction becomes the first one.</Empty>}
        <div className="space-y-6">
          {pending.map((rule) => (
            <RuleCard key={rule.id} rule={rule} source={source} />
          ))}
        </div>
        {decided.length > 0 && (
          <ul className="mt-6 space-y-3">
            {decided.map((rule) => (
              <li key={rule.id} className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-line bg-surface px-6 py-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-[0.8125rem] text-ink3">
                    <span className="font-mono">{rule.id}</span>
                    <Badge tone="accent">
                      <IconCheck size={14} /> In effect
                    </Badge>
                  </div>
                  <div className="mt-1 text-[1.125rem] font-semibold text-ink">{rule.text}</div>
                </div>
                <div className="text-right text-[0.9375rem] text-ink2">
                  Approved by <b className="font-semibold text-ink">{nameOf(rule.decided_by)}</b> on {day(rule.decided_on)}
                  <div className="text-ink3">
                    backtest: {rule.backtest.cases_changed} cases changed{rule.backtest.dollars_moved_cents ? `, ${money(rule.backtest.dollars_moved_cents, { whole: true })} moved` : ''}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section className="mt-16" title="From history" aside={`${learned.length} learned · ${flagged.length} flagged as illegal`}>
        <ul className="divide-y divide-line/70 overflow-hidden rounded-2xl border border-line bg-surface">
          {[...learned, ...flagged].map((p) => (
            <li key={p.id} className={cx('grid grid-cols-1 gap-3 px-6 py-4 md:grid-cols-[1fr_16rem_11rem] md:items-center', !p.legal && 'bg-danger-tint/50')}>
              <div className="min-w-0">
                <div className={cx('text-[1.0625rem] font-medium', p.legal ? 'text-ink' : 'text-ink line-through decoration-danger/50')}>{p.text}</div>
                {!p.legal && (
                  <div className="mt-1 text-[0.9375rem] text-danger">
                    Breaks {p.law}: {p.law_text}
                    {p.note ? <span className="text-ink2"> {p.note}</span> : null}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-3">
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-line/60">
                  <div className={cx('h-full rounded-full', p.legal ? 'bg-accent' : 'bg-danger')} style={{ width: `${Math.max(3, (100 * p.evidence_count) / maxEvidence)}%` }} />
                </div>
                <span className="tnum w-24 text-right text-[0.9375rem] text-ink2">{count(p.evidence_count)} cases</span>
              </div>
              <div className="md:text-right">
                {p.legal ? (
                  <Badge tone="accent">
                    <IconCheck size={14} /> Learned
                  </Badge>
                ) : (
                  <Badge tone="danger">
                    <IconShield size={14} /> Flagged, not learned
                  </Badge>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section className="mt-16" title="From corrections" aside="Every correction becomes a precedent">
        {precedents.length === 0 ? (
          <Empty>No corrections yet.</Empty>
        ) : (
          <ul className="space-y-4">
            {precedents.map((p) => (
              <li key={p.id} className="rounded-2xl border border-line bg-surface px-6 py-5">
                <div className="flex flex-wrap items-center gap-2 text-[0.8125rem] text-ink3">
                  <span className="font-mono">{p.id}</span>
                  <span>
                    {nameOf(p.by)} · {day(p.on)} ·
                  </span>
                  <Link to={`/accounts/${p.account_id}`} className="font-mono text-accent hover:underline">
                    {p.account_id}
                  </Link>
                  {p.patient_name && <span>{titleCase(p.patient_name)}</span>}
                </div>
                <p className="mt-2 text-[1.1875rem] font-medium leading-relaxed text-ink">“{p.correction}”</p>
                {p.note && <p className="mt-1 text-[0.9375rem] text-ink2">{p.note}</p>}
                <p className="mt-2 text-[0.9375rem] text-ink2">
                  Found <b className="font-semibold text-ink">{p.similar_cases} similar past cases</b>
                  {p.rule_id ? (
                    <>
                      {' '}
                      → proposed rule <span className="font-mono">{p.rule_id}</span>
                    </>
                  ) : null}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section className="mt-16" title="Never proposed again" aside="A rejected rule is stored, and the gateway refuses to let it come back">
        {rejected.length === 0 ? (
          <Empty>Nothing rejected yet.</Empty>
        ) : (
          <ul className="space-y-4">
            {rejected.map((x) => (
              <li key={x.pattern} className="flex flex-wrap items-start justify-between gap-6 rounded-2xl border border-line bg-surface px-6 py-5">
                <div className="min-w-0 max-w-3xl">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="danger">
                      <IconX size={14} /> Rejected
                    </Badge>
                    <span className="font-mono text-[0.8125rem] text-ink3">{x.pattern}</span>
                  </div>
                  <div className="mt-2 text-[1.25rem] font-semibold text-ink line-through decoration-ink3/50">{x.text ?? x.pattern}</div>
                  <p className="mt-1 text-[1rem] text-ink2">
                    {nameOf(x.rejected_by)} on {day(x.rejected_on)}
                    {x.note ? `: “${x.note}”` : ''}
                  </p>
                </div>
                <div className="text-right">
                  <div className="tnum text-[2.25rem] font-semibold leading-none tracking-[-0.03em] text-ink">{x.blocked_since ?? 0}</div>
                  <div className="mt-1 text-[0.875rem] text-ink3">times it was stopped since</div>
                  <Link to={`/audit?q=${encodeURIComponent(x.pattern)}`} className="mt-2 inline-flex items-center gap-1 text-[0.9375rem] font-medium text-accent hover:underline">
                    See them <IconArrowRight size={14} />
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Page>
  );
}

function RuleCard({ rule, source }: { rule: LearnedRule; source: Source }) {
  const { current, firstWithRole, setCurrent, people } = usePeople();
  const { decide, busy, refusal, setRefusal, error } = useDecision(source);
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState('');
  const director = firstWithRole('director');
  const p = rule.proposal;
  const bt = rule.backtest;
  return (
    <article className="overflow-hidden rounded-3xl border border-line bg-surface shadow-lift">
      <div className="px-7 pb-6 pt-7">
        <div className="flex flex-wrap items-center gap-2 text-[0.8125rem] text-ink3">
          <span className="font-mono">{rule.id}</span>
          {rule.from_precedent && <span>from precedent {rule.from_precedent}</span>}
          <Badge tone="warn">Waiting for the director</Badge>
        </div>
        <h3 className="mt-2 text-[1.875rem] font-semibold leading-tight tracking-[-0.025em] text-ink">{rule.text}</h3>
        {p?.rationale && <p className="mt-3 max-w-4xl text-[1.0625rem] leading-relaxed text-ink2">{p.rationale}</p>}
      </div>
      <div className="grid grid-cols-3 border-y border-line bg-bg">
        <div className="px-7 py-5">
          <div className="tnum text-[2.75rem] font-semibold leading-none tracking-[-0.04em] text-ink">{bt.cases_changed}</div>
          <div className="mt-2 text-[0.9375rem] text-ink2">past cases change</div>
        </div>
        <div className="border-x border-line px-7 py-5">
          <div className="tnum text-[2.75rem] font-semibold leading-none tracking-[-0.04em] text-accent">{money(bt.dollars_moved_cents, { whole: true })}</div>
          <div className="mt-2 text-[0.9375rem] text-ink2">moves to charity care</div>
        </div>
        <div className="px-7 py-5">
          <div className="tnum text-[2.75rem] font-semibold leading-none tracking-[-0.04em] text-ink">{count(bt.cases_checked)}</div>
          <div className="mt-2 text-[0.9375rem] text-ink2">past cases backtested</div>
        </div>
      </div>
      {bt.examples && bt.examples.length > 0 && (
        <div className="px-7 py-5">
          <div className="mb-2 text-[0.8125rem] font-semibold uppercase tracking-wider text-ink3">What it would have changed</div>
          <table className="w-full text-left text-[0.9875rem]">
            <tbody>
              {bt.examples.map((e) => (
                <tr key={e.application_id} className="border-t border-line/70">
                  <td className="py-2 pr-4 font-medium text-ink">{e.patient_name ?? '—'}</td>
                  <td className="py-2 pr-4 font-mono text-[0.8rem] text-ink3">{e.application_id}</td>
                  <td className="py-2 pr-4 text-ink2">{e.before}</td>
                  <td className="py-2 pr-4 font-medium text-accent-strong">→ {e.after}</td>
                  <td className="tnum py-2 text-right text-ink">{money(e.dollars_cents, { whole: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line px-7 py-5">
        <p className="text-[0.9375rem] text-ink3">A new rule is the director's call. Approve and it applies to every account from now on.</p>
        {p && current && (
          <div className="flex flex-wrap items-center gap-2">
            {current.role !== 'director' && director && (
              <Button tone="quiet" onClick={() => setCurrent(director.id)}>
                Act as {director.name} <Kbd>{people.indexOf(director) + 1}</Kbd>
              </Button>
            )}
            {!rejecting ? (
              <>
                <Button tone="secondary" onClick={() => setRejecting(true)} disabled={busy}>
                  Reject
                </Button>
                <Button tone="primary" onClick={() => void decide(p, true, '')} disabled={busy}>
                  <IconCheck size={18} /> Approve rule as {current.name.split(' ')[0]}
                </Button>
              </>
            ) : (
              <form
                className="flex flex-wrap gap-2"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (await decide(p, false, note.trim())) setRejecting(false);
                }}
              >
                <input autoFocus value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why not? It's stored with the no." className="h-10 w-80 rounded-xl border border-line px-3 outline-none focus:border-accent" />
                <Button tone="quiet" onClick={() => setRejecting(false)}>
                  Cancel
                </Button>
                <Button tone="danger" type="submit" disabled={busy}>
                  Reject rule
                </Button>
              </form>
            )}
          </div>
        )}
      </div>
      {(refusal || error) && (
        <div className="px-7 pb-6">
          {refusal && <GatewayRefusal refusal={refusal} onDismiss={() => setRefusal(null)} />}
          {error && <p className="text-danger">{error}</p>}
        </div>
      )}
    </article>
  );
}
