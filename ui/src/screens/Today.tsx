import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, coreReach, errorText, FORCE_MOCK, isPinned, pinSample, unpinSample, type Source } from '../api/client';
import type { CoreState, Inbox, WorkState } from '../api/types';
import { WORK_STATES } from '../api/types';
import { ProposalCard, QuestionCard } from '../components/decisions';
import { IconArrowRight, IconPlay } from '../components/icons';
import { Button, CountUp, cx, Empty, ErrorNote, Loading, Page, SampleTag, Section } from '../components/ui';
import { count, dayLong, dayShort, ROLE_LABEL, STATE_HINT, STATE_LABEL } from '../lib/format';
import { usePeople } from '../lib/people';
import { useResource } from '../lib/useResource';

const LIVE_START = '2026-07-01';
const LIVE_DAYS = 92;

function dayNumber(today: string): number {
  const a = Date.parse(`${LIVE_START}T00:00:00Z`);
  const b = Date.parse(`${today}T00:00:00Z`);
  return Math.round((b - a) / 86_400_000) + 1;
}

const GROUPS: Array<{ label: string; states: WorkState[]; hint: string }> = [
  { label: 'Being worked', states: ['NEW', 'SCREENING'], hint: 'synced in or being screened by the AI' },
  { label: 'Asked a person', states: ['NEEDS_INFO'], hint: 'waiting on an answer' },
  { label: 'Waiting for a decision', states: ['PROPOSED', 'APPROVED'], hint: 'proposed, a person decides' },
  { label: 'Posted', states: ['POSTED'], hint: 'done and in the ledger' },
];

const BAR: Record<WorkState, string> = {
  NEW: 'bg-ink3/40',
  SCREENING: 'bg-ink3/70',
  NEEDS_INFO: 'bg-warn',
  PROPOSED: 'bg-accent',
  APPROVED: 'bg-accent/60',
  REJECTED: 'bg-danger',
  POSTED: 'bg-ink',
};

const DIFF_WORDS: Record<WorkState, string> = {
  NEW: 'new',
  SCREENING: 'screening',
  NEEDS_INFO: 'asked a person',
  PROPOSED: 'proposed for a decision',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  POSTED: 'posted',
};

function diffLine(from: CoreState, to: CoreState): string {
  const parts: string[] = [];
  for (const s of WORK_STATES) {
    const d = (to.work_items_by_state[s] ?? 0) - (from.work_items_by_state[s] ?? 0);
    if (d !== 0) parts.push(`${d > 0 ? '+' : '−'}${Math.abs(d)} ${DIFF_WORDS[s]}`);
  }
  const q = to.open_questions - from.open_questions;
  if (q > 0) parts.push(`${q} new question${q === 1 ? '' : 's'} for people`);
  return parts.length ? parts.join(' · ') : 'Nothing changed.';
}

export default function Today() {
  const { current } = usePeople();
  const [sample, setSample] = useState(isPinned('today'));
  const src: Source = sample ? 'sample' : 'core';
  const st = useResource(() => api.state(src), [src], { intervalMs: 4000 });
  const inbox = useResource<Inbox | null>(
    () => (current ? api.inbox(current.id, src) : Promise.resolve({ data: null, source: src })),
    [current?.id, src],
    { intervalMs: 4000 },
  );
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<{ day: string; line: string; source: Source } | null>(null);

  const runDay = async () => {
    if (!st.data) return;
    setRunning(true);
    setRunError(null);
    const before = st.data;
    const sampleBefore = (await api.state('sample')).data;
    const coreBefore = sample && !FORCE_MOCK ? (await api.state('core')).data : before;
    try {
      const r = await api.advance(1);
      if (r.source === 'sample') {
        // The core answered but has no /sim/advance yet: keep showing the sample world it advanced.
        if (!sample && coreReach() === 'up') {
          pinSample('today');
          setSample(true);
        }
        setLastRun({ day: r.data.today, line: diffLine(sampleBefore, r.data), source: r.source });
      } else {
        if (sample && !FORCE_MOCK) {
          unpinSample('today');
          setSample(false);
        }
        setLastRun({ day: r.data.today, line: diffLine(coreBefore, r.data), source: r.source });
      }
    } catch (e) {
      setRunError(errorText(e));
    } finally {
      setRunning(false);
    }
  };

  const data = st.data;
  const total = data ? WORK_STATES.reduce((s, k) => s + (data.work_items_by_state[k] ?? 0), 0) : 0;
  const items = inbox.data ? [...inbox.data.questions.map((q) => ({ t: 'q' as const, q })), ...inbox.data.proposals.map((p) => ({ t: 'p' as const, p }))] : [];
  const waiting = items.length;
  const firstName = current?.name.split(' ')[0] ?? '';
  const reversals = inbox.data?.proposals.filter((p) => p.kind === 'REVERSAL').length ?? 0;

  return (
    <Page eyebrow={data ? `Today · live day ${dayNumber(data.today)} of ${LIVE_DAYS}` : 'Today'} title={data ? dayLong(data.today) : 'Today'} right={<SampleTag source={st.source} endpoint={sample ? '/sim/advance' : undefined} />}>
      {st.error && !data && <ErrorNote>{st.error}</ErrorNote>}
      {!data && st.loading && <Loading />}
      {data && (
        <>
          <div className="-mt-4 flex flex-wrap items-center gap-x-6 gap-y-4">
            <Button tone="primary" size="lg" onClick={() => void runDay()} disabled={running}>
              <IconPlay size={18} />
              {running ? 'Running the day…' : 'Run next day'}
            </Button>
            <p className="max-w-xl text-[1.0625rem] leading-snug text-ink2">
              {lastRun ? (
                <>
                  <b className="font-semibold text-ink">{dayShort(lastRun.day)}:</b> {lastRun.line}
                </>
              ) : (
                'Sync pulls the day from every system, then the AI works every account. Clear cases go to a decision; unclear ones go to the right person.'
              )}
            </p>
          </div>
          {runError && (
            <div className="mt-4">
              <ErrorNote>{runError}</ErrorNote>
            </div>
          )}

          <Section className="mt-16" title="The work" aside={`${count(total)} accounts being worked · ${count(data.open_proposals)} open proposals · ${count(data.open_questions)} open questions`}>
            <div className="grid grid-cols-2 gap-x-10 gap-y-10 xl:grid-cols-4">
              {GROUPS.map((g) => {
                const n = g.states.reduce((s, k) => s + (data.work_items_by_state[k] ?? 0), 0);
                return (
                  <Link key={g.label} to={`/work?state=${g.states[0]}`} className="group">
                    <div className="tnum text-big font-semibold text-ink transition group-hover:text-accent">
                      <CountUp value={n} format={(v) => count(Math.round(v))} fromZero />
                    </div>
                    <div className="mt-3 text-[1.125rem] font-semibold text-ink">{g.label}</div>
                    <div className="text-[0.9375rem] text-ink3">{g.hint}</div>
                  </Link>
                );
              })}
            </div>
            {total > 0 && (
              <div className="mt-10">
                <div className="flex h-3 w-full overflow-hidden rounded-full bg-line/60">
                  {WORK_STATES.map((s) => {
                    const n = data.work_items_by_state[s] ?? 0;
                    return n ? <div key={s} className={cx('h-full transition-all duration-700', BAR[s])} style={{ width: `${(100 * n) / total}%` }} title={`${STATE_LABEL[s]}: ${n}`} /> : null;
                  })}
                </div>
                <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-[0.875rem] text-ink2">
                  {WORK_STATES.map((s) => (
                    <span key={s} className="inline-flex items-center gap-2" title={STATE_HINT[s]}>
                      <span className={cx('h-2.5 w-2.5 rounded-full', BAR[s])} />
                      {STATE_LABEL[s]} <b className="tnum font-semibold text-ink">{data.work_items_by_state[s] ?? 0}</b>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Section>

          <Section
            className="mt-16"
            title={current && inbox.data ? (waiting ? `${waiting} ${waiting === 1 ? 'thing needs' : 'things need'} ${firstName}` : `Nothing needs ${firstName} right now`) : `What needs ${firstName || 'you'}`}
            aside={current ? `${ROLE_LABEL[current.role] ?? current.role} · switch person with 1, 2, 3` : undefined}
          >
            {inbox.error && <ErrorNote>{inbox.error}</ErrorNote>}
            {inbox.data && waiting === 0 && <Empty>All clear. The AI asks when it needs {firstName}.</Empty>}
            {reversals > 3 && (
              <Link to="/discovery" className="mb-5 flex items-center justify-between gap-4 rounded-2xl bg-ink px-6 py-5 text-white transition hover:bg-ink/90">
                <span className="text-[1.125rem] font-semibold">
                  {reversals} reversals of illegal denials are waiting on the day-one screen
                </span>
                <IconArrowRight size={22} />
              </Link>
            )}
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              {items.slice(0, 4).map((it) =>
                it.t === 'q' ? (
                  <QuestionCard key={it.q.id} question={it.q} source={inbox.source ?? 'core'} showAccount />
                ) : (
                  <ProposalCard key={it.p.id} proposal={it.p} source={inbox.source ?? 'core'} compact showAccount />
                ),
              )}
            </div>
            {waiting > 4 && (
              <Link to="/work?state=PROPOSED" className="mt-5 inline-flex items-center gap-2 text-[1.0625rem] font-semibold text-accent hover:underline">
                See all {waiting} on the Work screen <IconArrowRight size={18} />
              </Link>
            )}
          </Section>
        </>
      )}
    </Page>
  );
}
