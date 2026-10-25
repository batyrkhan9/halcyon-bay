import type { ReactNode } from 'react';
import { api } from '../api/client';
import { CountUp, ErrorNote, Loading, Page, SampleTag } from '../components/ui';
import { count, day, money, percent } from '../lib/format';
import { useResource } from '../lib/useResource';

export default function Score() {
  const r = useResource(() => api.score(), [], { intervalMs: 5000 });
  if (!r.data) return <Page eyebrow="Score">{r.error ? <ErrorNote>{r.error}</ErrorNote> : <Loading />}</Page>;
  const s = r.data;
  const byLaw = Object.entries(s.violations_prevented.by_law ?? {}).filter(([, n]) => n > 0);

  return (
    <Page eyebrow={`Score · against the answer key${s.as_of ? ` · as of ${day(s.as_of)}` : ''}`} right={<SampleTag source={r.source} endpoint="/score" />} wide>
      <div className="grid grid-cols-1 gap-x-16 gap-y-14 lg:grid-cols-2">
        <Big
          value={s.precision.value}
          format={(v) => percent(v, 1)}
          label="Precision on what it does alone"
          sub={s.precision.total ? `${count(s.precision.correct)} of ${count(s.precision.total)} right. Everything else went to a person.` : 'Everything else went to a person.'}
          accent
        />
        <Big
          value={s.auto_share.value}
          format={(v) => percent(v, 0)}
          label="Handled automatically"
          sub={s.auto_share.total ? `${count(s.auto_share.auto)} of ${count(s.auto_share.total)} accounts without asking anyone.` : undefined}
        />
      </div>
      <div className="mt-16 grid grid-cols-1 gap-x-12 gap-y-14 border-t border-line pt-14 lg:grid-cols-[1.25fr_1fr_1fr]">
        <Big value={s.charity_cents} format={(v) => money(Math.round(v), { whole: true })} label="Charity care proposed" sub="For patients who qualify under the law, checked against the answer key" small />
        <Big value={s.payment_plan_collected_cents} format={(v) => money(Math.round(v), { whole: true })} label="Payment plans proposed" sub="For patients who can pay, instead of written off" small />
        <Big value={s.violations_prevented.count} format={(v) => count(Math.round(v))} label="Violations prevented" small>
          {byLaw.length > 0 && (
            <ul className="mt-4 space-y-1.5 text-[1rem] text-ink2">
              {byLaw.map(([law, n]) => (
                <li key={law} className="flex justify-between gap-6 border-b border-line/60 pb-1.5">
                  <span>{law}</span>
                  <span className="tnum font-semibold text-ink">{n}</span>
                </li>
              ))}
            </ul>
          )}
        </Big>
      </div>
      {s.answer_key && (
        <p className="mt-16 border-t border-line pt-6 text-[1.125rem] text-ink2">
          Scored against the answer key: <b className="font-semibold text-ink">{count(s.answer_key.matched)}</b> of {count(s.answer_key.accounts_scored)} accounts end where the key says they should. The core never reads the key; only the score script does.
        </p>
      )}
    </Page>
  );
}

function Big({ value, format, label, sub, accent, small, children }: { value: number; format: (n: number) => string; label: string; sub?: string; accent?: boolean; small?: boolean; children?: ReactNode }) {
  return (
    <div>
      <div className={`tnum font-semibold ${small ? 'text-stat' : 'text-giant'} ${accent ? 'text-accent' : 'text-ink'}`}>
        <CountUp value={value} format={format} fromZero />
      </div>
      <div className={`mt-4 font-semibold text-ink ${small ? 'text-[1.25rem]' : 'text-[1.625rem] tracking-[-0.015em]'}`}>{label}</div>
      {sub && <div className="mt-1 text-[1.0625rem] text-ink2">{sub}</div>}
      {children}
    </div>
  );
}
