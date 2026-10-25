import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, isPinned } from '../api/client';
import type { WorkState } from '../api/types';
import { WORK_STATES } from '../api/types';
import { Empty, ErrorNote, Loading, Page, SampleTag, StatePill, cx } from '../components/ui';
import { count, dayShort, money, STATE_LABEL, titleCase } from '../lib/format';
import { useResource } from '../lib/useResource';

export default function Work() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const raw = params.get('state');
  const filter = raw && (WORK_STATES as readonly string[]).includes(raw) ? (raw as WorkState) : null;
  const [q, setQ] = useState('');
  const r = useResource(() => api.workItems(undefined, 500, isPinned('today') ? 'sample' : 'core'), [], { intervalMs: 5000 });

  const counts = useMemo(() => {
    const c = Object.fromEntries(WORK_STATES.map((s) => [s, 0])) as Record<WorkState, number>;
    for (const w of r.data ?? []) c[w.state] = (c[w.state] ?? 0) + 1;
    return c;
  }, [r.data]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (r.data ?? []).filter(
      (w) =>
        (!filter || w.state === filter) &&
        (!needle || `${w.account_id} ${w.patient_name ?? ''} ${w.reason} ${w.id}`.toLowerCase().includes(needle)),
    );
  }, [r.data, filter, q]);

  const setFilter = (s: WorkState | null) => {
    const next = new URLSearchParams(params);
    if (s) next.set('state', s);
    else next.delete('state');
    setParams(next, { replace: true });
  };

  return (
    <Page
      eyebrow="Work"
      title="Every account being worked, and where it stands."
      right={
        <div className="flex flex-col items-end gap-3">
          <SampleTag source={r.source} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Find a patient or account"
            aria-label="Find a patient or account"
            className="h-11 w-72 rounded-xl border border-line bg-surface px-4 text-[1rem] outline-none focus:border-accent"
          />
        </div>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <Chip active={!filter} onClick={() => setFilter(null)} label="All" n={r.data?.length ?? 0} />
        {WORK_STATES.map((s) => (
          <Chip key={s} active={filter === s} onClick={() => setFilter(s)} label={STATE_LABEL[s]} n={counts[s]} />
        ))}
      </div>

      <div className="mt-8">
        {r.error && !r.data && <ErrorNote>{r.error}</ErrorNote>}
        {!r.data && r.loading && <Loading />}
        {r.data && rows.length === 0 && <Empty>No accounts {filter ? `in ${STATE_LABEL[filter].toLowerCase()}` : ''} match.</Empty>}
        {rows.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-line bg-surface">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-line text-[0.8125rem] font-semibold uppercase tracking-wider text-ink3">
                  <th className="px-6 py-3.5">Patient</th>
                  <th className="px-4 py-3.5 text-right">Billed</th>
                  <th className="px-4 py-3.5">Where it stands</th>
                  <th className="hidden px-4 py-3.5 lg:table-cell">Why it's open</th>
                  <th className="px-6 py-3.5 text-right">Updated</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((w) => (
                  <tr
                    key={w.id}
                    onClick={() => navigate(`/accounts/${w.account_id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate(`/accounts/${w.account_id}`);
                    }}
                    tabIndex={0}
                    className="cursor-pointer border-b border-line/60 transition last:border-b-0 hover:bg-accent-tint/40 focus:bg-accent-tint/40 focus:outline-none"
                  >
                    <td className="px-6 py-4">
                      <div className="text-[1.0625rem] font-semibold text-ink">{titleCase(w.patient_name)}</div>
                      <div className="font-mono text-[0.8rem] text-ink3">
                        {w.account_id} · {w.id}
                      </div>
                    </td>
                    <td className="tnum px-4 py-4 text-right text-[1.0625rem] text-ink">{money(w.billed_cents ?? null)}</td>
                    <td className="px-4 py-4">
                      <StatePill state={w.state} />
                    </td>
                    <td className="hidden max-w-md px-4 py-4 text-[0.9875rem] text-ink2 lg:table-cell">{w.reason}</td>
                    <td className="tnum px-6 py-4 text-right text-[0.9375rem] text-ink3">{dayShort(w.updated_on)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {r.data && <p className="mt-4 text-[0.875rem] text-ink3">Showing {count(rows.length)} of {count(r.data.length)}. Newest first.</p>}
      </div>
    </Page>
  );
}

function Chip({ active, onClick, label, n }: { active: boolean; onClick: () => void; label: string; n: number }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        'inline-flex h-10 items-center gap-2 rounded-full px-4 text-[0.9375rem] font-medium transition',
        active ? 'bg-ink text-white' : 'bg-surface text-ink2 ring-1 ring-inset ring-line hover:text-ink hover:ring-ink3/50',
      )}
    >
      {label}
      <span className={cx('tnum text-[0.8125rem]', active ? 'text-white/70' : 'text-ink3')}>{n}</span>
    </button>
  );
}
