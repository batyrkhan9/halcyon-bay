import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { CORE_URL, FORCE_MOCK, type Source } from '../api/client';
import type { WorkState } from '../api/types';
import { STATE_LABEL } from '../lib/format';

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export function Page({
  eyebrow,
  title,
  lede,
  right,
  children,
  wide,
}: {
  eyebrow?: ReactNode;
  title?: ReactNode;
  lede?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={cx('mx-auto w-full animate-rise px-4 pb-24 pt-8 sm:px-6 md:px-12 md:pt-10 lg:px-14', wide ? 'max-w-[96rem]' : 'max-w-page')}>
      {(eyebrow || title || right) && (
        <header className="mb-12 flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0 max-w-4xl">
            {eyebrow && <div className="mb-4 text-eyebrow font-semibold uppercase text-ink3">{eyebrow}</div>}
            {title && <h1 className="text-hero font-semibold text-ink">{title}</h1>}
            {lede && <p className="mt-5 max-w-3xl text-xl leading-relaxed text-ink2">{lede}</p>}
          </div>
          {right && <div className="flex shrink-0 items-center gap-3 pt-1">{right}</div>}
        </header>
      )}
      {children}
    </div>
  );
}

export function Section({ title, aside, children, className }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx('mt-14 first:mt-0', className)}>
      {(title || aside) && (
        <div className="mb-5 flex flex-wrap items-baseline justify-between gap-4 border-b border-line pb-3">
          {title && <h2 className="text-[1.375rem] font-semibold tracking-[-0.015em] text-ink">{title}</h2>}
          {aside && <div className="text-[0.9375rem] text-ink3">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/** Small, honest marker: this screen is showing sample data, not the core. */
export function SampleTag({ source, endpoint }: { source: Source | undefined; endpoint?: string }) {
  if (source !== 'sample') return null;
  const why = FORCE_MOCK
    ? 'Sample mode (VITE_MOCK=1): the whole app runs on the built-in sample world.'
    : endpoint
      ? `The core at ${CORE_URL} doesn't serve ${endpoint} yet, so this screen shows the sample world. It switches to live data on its own once it does.`
      : `The core at ${CORE_URL} isn't reachable, so this screen shows the sample world.`;
  return (
    <span
      title={why}
      className="inline-flex select-none items-center gap-1.5 rounded-full border border-dashed border-ink3/50 px-2.5 py-1 text-[0.75rem] font-medium tracking-wide text-ink3"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-ink3/70" />
      sample data
    </span>
  );
}

const STATE_STYLE: Record<WorkState, string> = {
  NEW: 'bg-ink/[0.05] text-ink2',
  SCREENING: 'bg-ink/[0.05] text-ink2',
  NEEDS_INFO: 'bg-warn-tint text-warn',
  PROPOSED: 'bg-accent-tint text-accent-strong',
  APPROVED: 'bg-accent-tint text-accent-strong',
  REJECTED: 'bg-danger-tint text-danger',
  POSTED: 'bg-ink text-white',
};
const STATE_DOT: Record<WorkState, string> = {
  NEW: 'bg-ink3',
  SCREENING: 'bg-ink2 animate-pulse-dot',
  NEEDS_INFO: 'bg-warn',
  PROPOSED: 'bg-accent',
  APPROVED: 'bg-accent',
  REJECTED: 'bg-danger',
  POSTED: 'bg-white',
};

export function StatePill({ state, big }: { state: WorkState; big?: boolean }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-2 whitespace-nowrap rounded-full font-medium',
        big ? 'px-3.5 py-1.5 text-[0.9375rem]' : 'px-2.5 py-0.5 text-[0.8125rem]',
        STATE_STYLE[state] ?? 'bg-ink/[0.05] text-ink2',
      )}
    >
      <span className={cx('h-1.5 w-1.5 rounded-full', STATE_DOT[state] ?? 'bg-ink3')} />
      {STATE_LABEL[state] ?? state}
    </span>
  );
}

export function Badge({ tone = 'neutral', children, className }: { tone?: 'neutral' | 'accent' | 'danger' | 'warn' | 'ink'; children: ReactNode; className?: string }) {
  const tones = {
    neutral: 'bg-ink/[0.05] text-ink2',
    accent: 'bg-accent-tint text-accent-strong',
    danger: 'bg-danger-tint text-danger',
    warn: 'bg-warn-tint text-warn',
    ink: 'bg-ink text-white',
  } as const;
  return <span className={cx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-[0.8125rem] font-medium', tones[tone], className)}>{children}</span>;
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'primary' | 'secondary' | 'quiet' | 'danger'; size?: 'md' | 'lg' };

export function Button({ tone = 'secondary', size = 'md', className, children, ...rest }: BtnProps) {
  const tones = {
    primary: 'bg-accent text-white shadow-[0_1px_0_rgb(255_255_255/0.15)_inset,0_1px_2px_rgb(0_0_0/0.12)] hover:bg-accent-strong',
    secondary: 'bg-surface text-ink ring-1 ring-inset ring-line hover:ring-ink3/60 hover:bg-white',
    quiet: 'text-ink2 hover:text-ink hover:bg-ink/[0.04]',
    danger: 'bg-surface text-danger ring-1 ring-inset ring-danger/30 hover:bg-danger-tint',
  } as const;
  const sizes = { md: 'h-10 px-4 text-[0.9375rem]', lg: 'h-14 px-7 text-[1.0625rem]' } as const;
  return (
    <button
      type="button"
      className={cx(
        'inline-flex select-none items-center justify-center gap-2 rounded-xl font-semibold transition duration-150 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50',
        tones[tone],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-line bg-surface px-1 font-sans text-[0.6875rem] font-semibold text-ink3">{children}</kbd>;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-danger/25 bg-danger-tint px-4 py-3 text-[0.9375rem] text-danger">{children}</div>;
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-16 text-ink3">
      <span className="h-2 w-2 animate-pulse-dot rounded-full bg-accent" />
      {label}…
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-line px-6 py-10 text-center text-lg text-ink3">{children}</div>;
}

/** Counts up to a new value, so a changing number reads as a change. Resumes from what is on screen. */
export function useCountUp(target: number, ms = 700, fromZero = false): number {
  const initial = fromZero ? 0 : target;
  const [v, setV] = useState(initial);
  const shown = useRef(initial);
  useEffect(() => {
    const reduce = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const a = shown.current;
    if (reduce || a === target) {
      shown.current = target;
      setV(target);
      return;
    }
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const val = a + (target - a) * (1 - Math.pow(1 - t, 3));
      shown.current = val;
      setV(val);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

export function CountUp({ value, format, fromZero, ms }: { value: number; format: (n: number) => string; fromZero?: boolean; ms?: number }) {
  const v = useCountUp(value, ms ?? (fromZero ? 1100 : 700), fromZero);
  return <>{format(v)}</>;
}
