import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { api, CORE_URL, coreReach, FORCE_MOCK, isPinned, onChanged, onCoreReach } from '../api/client';
import { dayLong, ROLE_SHORT } from '../lib/format';
import { usePeople } from '../lib/people';
import { IconAudit, IconDiscovery, IconJudge, IconLearned, IconScore, IconToday, IconWork } from './icons';
import { cx, Kbd } from './ui';

const NAV = [
  { to: '/', label: 'Today', icon: IconToday, end: true },
  { to: '/discovery', label: 'Day one', icon: IconDiscovery },
  { to: '/work', label: 'Work', icon: IconWork },
  { to: '/learned', label: 'Learned', icon: IconLearned },
  { to: '/audit', label: 'Audit', icon: IconAudit },
  { to: '/score', label: 'Score', icon: IconScore },
  { to: '/judge', label: 'Judge box', icon: IconJudge },
];

function Mark() {
  return (
    <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="rgb(var(--c-accent))" />
      <circle cx="16" cy="12.5" r="3.6" fill="#fff" />
      <path d="M6.5 20.5c3.2-2.6 6.3-2.6 9.5 0s6.3 2.6 9.5 0" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function useSimDay() {
  const [today, setToday] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await api.state(isPinned('today') ? 'sample' : 'core');
        if (alive) setToday(r.data.today);
      } catch {
        /* the screens show the error */
      }
    };
    void load();
    const t = window.setInterval(load, 5000);
    const off = onChanged(() => void load());
    return () => {
      alive = false;
      window.clearInterval(t);
      off();
    };
  }, []);
  return today;
}

function CoreStatus() {
  const [reach, setReach] = useState(coreReach());
  useEffect(() => onCoreReach(setReach), []);
  if (FORCE_MOCK) {
    return (
      <div className="flex items-center gap-2 text-[0.8125rem] text-ink3">
        <span className="h-2 w-2 rounded-full border border-ink3" /> Sample world (VITE_MOCK=1)
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-[0.8125rem] text-ink3" title={CORE_URL}>
      <span className={cx('h-2 w-2 rounded-full', reach === 'up' ? 'bg-accent' : reach === 'down' ? 'bg-danger' : 'bg-ink3')} />
      {reach === 'down' ? 'Core not reachable' : 'Core live'} · {CORE_URL.replace(/^https?:\/\//, '')}
    </div>
  );
}

function RoleSwitcher() {
  const { people, current, setCurrent, inboxCounts } = usePeople();
  if (!people.length) return <div className="h-14" />;
  return (
    <div className="flex min-w-0 max-w-full items-center gap-3">
      <span className="hidden text-[0.8125rem] font-medium uppercase tracking-[0.08em] text-ink3 xl:inline">Acting as</span>
      <div role="radiogroup" aria-label="Act as" className="flex max-w-full overflow-x-auto rounded-2xl bg-rail p-1 ring-1 ring-inset ring-line">
        {people.map((p, i) => {
          const active = current?.id === p.id;
          const n = inboxCounts[p.id] ?? 0;
          return (
            <button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setCurrent(p.id)}
              title={`${p.name}, ${ROLE_SHORT[p.role] ?? p.role} (press ${i + 1})`}
              className={cx(
                'group relative flex items-center gap-3 rounded-xl px-3.5 py-2 text-left transition duration-150',
                active ? 'bg-surface shadow-seg' : 'hover:bg-white/60',
              )}
            >
              <div className="min-w-0">
                <div className={cx('whitespace-nowrap text-[0.9375rem] font-semibold leading-tight', active ? 'text-ink' : 'text-ink2')}>{p.name}</div>
                <div className={cx('whitespace-nowrap text-[0.75rem] leading-tight', active ? 'text-accent-strong' : 'text-ink3')}>{ROLE_SHORT[p.role] ?? p.role}</div>
              </div>
              <span
                className={cx(
                  'tnum flex h-6 min-w-[1.5rem] items-center justify-center rounded-full px-1.5 text-[0.75rem] font-bold',
                  n > 0 ? (active ? 'bg-accent text-white' : 'bg-ink/[0.08] text-ink2') : 'text-ink3/60',
                )}
                aria-label={`${n} waiting`}
              >
                {n}
              </span>
              <span className="pointer-events-none absolute -top-1.5 right-1 opacity-0 transition group-hover:opacity-100">
                <Kbd>{i + 1}</Kbd>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const today = useSimDay();
  const location = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen bg-bg">
      <aside className="sticky top-0 hidden h-screen w-[15.5rem] shrink-0 flex-col border-r border-line bg-rail px-5 py-7 lg:flex">
        <div className="flex items-center gap-3 px-2">
          <Mark />
          <div>
            <div className="text-[1.0625rem] font-semibold leading-tight tracking-[-0.01em] text-ink">Halcyon Bay</div>
            <div className="text-[0.75rem] leading-tight text-ink3">Patient billing office</div>
          </div>
        </div>
        <div className="mx-2 mt-8 rounded-xl border border-line bg-surface px-4 py-3">
          <div className="text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-ink3">Simulated day</div>
          <div className="tnum mt-1 text-[0.9875rem] font-semibold leading-snug text-ink">{today ? dayLong(today) : '…'}</div>
        </div>
        <nav className="mt-8 flex flex-col gap-1" aria-label="Screens">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cx(
                  'flex items-center gap-3 rounded-xl px-3 py-2.5 text-[1rem] font-medium transition',
                  isActive ? 'bg-surface text-ink shadow-seg' : 'text-ink2 hover:bg-white/60 hover:text-ink',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={20} className={isActive ? 'text-accent' : 'text-ink3'} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-3 px-2">
          <p className="text-[0.8125rem] leading-snug text-ink3">The AI proposes. People decide. Only the gateway posts.</p>
          <CoreStatus />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-20 border-b border-line/70 bg-bg/85 backdrop-blur-md">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 md:px-12 lg:flex-nowrap lg:px-14">
            <nav className="flex gap-1 overflow-x-auto lg:hidden" aria-label="Screens">
              {NAV.map(({ to, label, end }) => (
                <NavLink key={to} to={to} end={end} className={({ isActive }) => cx('whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[0.875rem] font-medium', isActive ? 'bg-surface text-ink shadow-seg' : 'text-ink2')}>
                  {label}
                </NavLink>
              ))}
            </nav>
            <div className="hidden lg:block" />
            <RoleSwitcher />
          </div>
        </div>
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
