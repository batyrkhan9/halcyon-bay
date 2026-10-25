import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { AuditList } from '../components/audit';
import { IconAudit } from '../components/icons';
import { cx, Empty, ErrorNote, Loading, Page, SampleTag } from '../components/ui';
import { count } from '../lib/format';
import { usePeople } from '../lib/people';
import { useResource } from '../lib/useResource';

const TRY = ['HB70017007', 'SB 1061', 'CalFresh', 'own account', 'Only the gateway', 'hidden instructions', 'AB 2297', 'Not proposed again'];

export default function Audit() {
  const [params, setParams] = useSearchParams();
  const { source: peopleSource } = usePeople();
  const [q, setQ] = useState(params.get('q') ?? '');
  const [debounced, setDebounced] = useState(q);
  const [blockedOnly, setBlockedOnly] = useState(params.get('blocked') === '1');

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q.trim()), 250);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const next = new URLSearchParams();
    if (debounced) next.set('q', debounced);
    if (blockedOnly) next.set('blocked', '1');
    setParams(next, { replace: true });
  }, [debounced, blockedOnly, setParams]);

  const r = useResource(
    () => api.audit({ q: debounced || undefined, allowed: blockedOnly ? false : undefined, limit: 300 }, peopleSource ?? 'core'),
    [debounced, blockedOnly, peopleSource],
    { intervalMs: 4000 },
  );
  const rows = r.data ?? [];
  const blocked = rows.filter((x) => !x.allowed).length;

  return (
    <Page eyebrow="Audit" title="Why did this happen?" lede="Every action and every attempt, including the ones that were refused. Nothing is ever edited or deleted. Asking why is one search." right={<SampleTag source={r.source} />}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setDebounced(q.trim());
        }}
        className="relative"
      >
        <IconAudit size={28} className="pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 text-ink3" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="An account, a person, a law, a word…"
          aria-label="Search the audit log"
          className="h-[4.5rem] w-full rounded-2xl border border-line bg-surface pl-[4.25rem] pr-6 text-[1.5rem] font-medium tracking-[-0.01em] text-ink shadow-lift outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/10"
        />
      </form>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="mr-1 text-[0.875rem] text-ink3">Try</span>
        {TRY.map((t) => (
          <button key={t} type="button" onClick={() => setQ(t)} className={cx('rounded-full px-3 py-1.5 text-[0.875rem] font-medium transition', q === t ? 'bg-ink text-white' : 'bg-surface text-ink2 ring-1 ring-inset ring-line hover:text-ink')}>
            {t}
          </button>
        ))}
      </div>

      <div className="mt-10 flex flex-wrap items-center justify-between gap-4">
        <p className="text-[1.0625rem] text-ink2">
          <b className="tnum font-semibold text-ink">{count(rows.length)}</b> {rows.length === 1 ? 'entry' : 'entries'}
          {debounced ? (
            <>
              {' '}
              for “<span className="text-ink">{debounced}</span>”
            </>
          ) : null}{' '}
          · <b className="tnum font-semibold text-danger">{count(blocked)}</b> blocked
        </p>
        <div className="flex rounded-xl bg-rail p-1 ring-1 ring-inset ring-line" role="radiogroup" aria-label="Filter">
          {[
            { v: false, label: 'Everything' },
            { v: true, label: 'Blocked only' },
          ].map((o) => (
            <button
              key={o.label}
              type="button"
              role="radio"
              aria-checked={blockedOnly === o.v}
              onClick={() => setBlockedOnly(o.v)}
              className={cx('rounded-lg px-4 py-2 text-[0.9375rem] font-medium transition', blockedOnly === o.v ? 'bg-surface text-ink shadow-seg' : 'text-ink2 hover:text-ink')}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5">
        {r.error && !r.data && <ErrorNote>{r.error}</ErrorNote>}
        {!r.data && r.loading && <Loading />}
        {r.data && rows.length === 0 && <Empty>Nothing in the log matches “{debounced}”.</Empty>}
        {rows.length > 0 && <AuditList key={`${debounced}|${blockedOnly}`} rows={rows} />}
      </div>
    </Page>
  );
}
