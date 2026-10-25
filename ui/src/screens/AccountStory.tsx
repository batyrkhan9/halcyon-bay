import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api, canWork, Denied, errorText, type Source } from '../api/client';
import { isFact, type AccountStory as Story, type CaseDocument, type CorrectionResult } from '../api/types';
import { AuditList } from '../components/audit';
import { GatewayRefusal, ProposalCard, QuestionCard, runWork, useWorkRun, WorkOutcome, type Refusal } from '../components/decisions';
import { IconArrowLeft, IconArrowRight } from '../components/icons';
import { Sources } from '../components/sources';
import { Badge, Button, ErrorNote, Loading, Page, SampleTag, Section, StatePill } from '../components/ui';
import { day, dayShort, humanize, kindLabel, money, ROLE_LABEL, titleCase } from '../lib/format';
import { usePeople } from '../lib/people';
import { useResource } from '../lib/useResource';

const CHARITY_KINDS = ['FREE_CARE', 'DISCOUNT', 'REVERSAL'];

export default function AccountStory() {
  const { id = '' } = useParams();
  const [params] = useSearchParams();
  const live = params.get('live') === '1';
  const r = useResource(() => api.account(id), [id], { intervalMs: live ? 1000 : 5000 });

  if (r.error && !r.data) {
    return (
      <Page eyebrow="Account" title={id}>
        <ErrorNote>{r.error}</ErrorNote>
        <BackLink />
      </Page>
    );
  }
  if (!r.data) {
    return (
      <Page eyebrow="Account" title={id}>
        <Loading label={live ? 'Opening the new account' : 'Loading the story'} />
      </Page>
    );
  }
  return <StoryView story={r.data} source={r.source ?? 'core'} live={live} autoWork={params.get('work')} />;
}

function BackLink() {
  return (
    <Link to="/work" className="mb-6 inline-flex items-center gap-2 text-[0.9375rem] font-medium text-ink3 hover:text-ink">
      <IconArrowLeft size={16} /> Work
    </Link>
  );
}

function StoryView({ story, source, live, autoWork }: { story: Story; source: Source; live: boolean; autoWork: string | null }) {
  const { account, work_items, proposals, questions, ledger, audit } = story;
  const documents = story.documents ?? [];
  const agencyRequests = story.agency_requests ?? [];
  const [workable, setWorkable] = useState(false);
  useEffect(() => {
    let alive = true;
    void canWork(source).then((ok) => alive && setWorkable(ok));
    return () => {
      alive = false;
    };
  }, [source]);
  // The judge box opens the account with ?work=<item>: work it once, live.
  const autoStarted = useRef(false);
  useEffect(() => {
    if (autoWork && workable && !autoStarted.current) {
      autoStarted.current = true;
      void runWork(autoWork, source);
    }
  }, [autoWork, workable, source]);
  const item = work_items[work_items.length - 1];
  const open = proposals.filter((p) => p.status === 'PROPOSED');
  const openQ = questions.filter((q) => q.answer === null);
  const decided = proposals.filter((p) => p.status !== 'PROPOSED');
  const answered = questions.filter((q) => q.answer !== null);
  const forgiven = ledger.filter((l) => CHARITY_KINDS.includes(l.kind)).reduce((s, l) => s + l.amount_cents, 0);
  const blocked = audit.filter((a) => !a.allowed).length;
  const done = !!item && ['POSTED', 'PROPOSED', 'NEEDS_INFO', 'REJECTED'].includes(item.state);
  const mrn = account.patient_id;
  const workItemNow = item && (item.state === 'NEW' || item.state === 'SCREENING') ? item : undefined;
  const run = useWorkRun(autoWork ?? item?.id);

  return (
    <Page>
      <BackLink />
      <header className="flex flex-wrap items-end justify-between gap-x-10 gap-y-6">
        <div className="min-w-0 flex-1 basis-[34rem]">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {item && <StatePill state={item.state} big />}
            {account.collections_paused && <Badge tone="accent">Collections paused</Badge>}
            {blocked > 0 && <Badge tone="danger">{blocked} blocked {blocked === 1 ? 'attempt' : 'attempts'}</Badge>}
            <SampleTag source={source} />
            {live && (
              <span className="inline-flex items-center gap-2 rounded-full bg-ink px-3 py-1 text-[0.8125rem] font-semibold text-white">
                <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-white" /> {done ? 'Worked live' : 'Working live'}
              </span>
            )}
          </div>
          <h1 className="text-hero font-semibold text-ink">{titleCase(account.patient_name)}</h1>
          <p className="mt-3 text-[1.0625rem] text-ink2">
            <span className="font-mono text-[0.95em]">{account.id}</span>
            {mrn && (
              <>
                {' '}
                · patient <span className="font-mono text-[0.95em]">{mrn}</span>
              </>
            )}
            {account.first_bill_on && <> · first bill {day(account.first_bill_on)}</>}
            {item && <> · {item.reason}</>}
          </p>
        </div>
        <div className="flex shrink-0 gap-10 text-right">
          <div>
            <div className="text-[0.875rem] text-ink3">Billed</div>
            <div className="tnum text-[2.5rem] font-semibold leading-none tracking-[-0.035em] text-ink">{money(account.billed_cents)}</div>
          </div>
          {forgiven > 0 && (
            <div>
              <div className="text-[0.875rem] text-ink3">Now owes</div>
              <div className="tnum text-[2.5rem] font-semibold leading-none tracking-[-0.035em] text-accent">{money(Math.max(0, account.billed_cents - forgiven))}</div>
            </div>
          )}
        </div>
      </header>

      {(open.length > 0 || openQ.length > 0) && (
        <Section className="mt-12" title="Waiting on a person" aside="Approve, reject or answer as the person picked at the top">
          <div className="space-y-5">
            {openQ.map((q) => (
              <QuestionCard key={q.id} question={q} source={source} showWork={false} />
            ))}
            {open.map((p) => (
              <ProposalCard key={p.id} proposal={p} source={source} />
            ))}
          </div>
        </Section>
      )}

      {(run || (workable && workItemNow)) && (
        <div className="mt-8">
          {workable && workItemNow && run?.state !== 'working' && (
            <div className="flex flex-wrap items-center gap-4">
              <Button tone="primary" onClick={() => void runWork(workItemNow.id, source)}>
                Work it now
              </Button>
              <span className="text-[0.9375rem] text-ink3">
                {workItemNow.id} is {workItemNow.state === 'NEW' ? 'new' : 'being screened'}. The agent reads the documents, then proposes or asks.
              </span>
            </div>
          )}
          {run && <WorkOutcome work={run} />}
        </div>
      )}

      {live && (
        <Section className="mt-12" title="Live steps" aside="Refreshing every second">
          {audit.length === 0 ? <Loading label="The core is picking it up" /> : <AuditList rows={audit} order="oldest" showAccount={false} compact />}
        </Section>
      )}

      {(decided.length > 0 || answered.length > 0) && (
        <Section className="mt-12" title="What was decided, and who decided it">
          <div className="space-y-5">
            {decided.map((p) => (
              <ProposalCard key={p.id} proposal={p} source={source} />
            ))}
            {answered.map((q) => (
              <QuestionCard key={q.id} question={q} source={source} showWork={false} />
            ))}
          </div>
        </Section>
      )}

      {agencyRequests.length > 0 && (
        <Section className="mt-12" title="Agency requests" aside="The agency asks before it acts; illegal requests are blocked">
          <ul className="divide-y divide-line/70 overflow-hidden rounded-2xl border border-line bg-surface">
            {agencyRequests.map((r) => (
              <li key={r.id} className={r.status === 'BLOCKED' ? 'flex flex-wrap items-center justify-between gap-3 bg-danger-tint/60 px-6 py-4' : 'flex flex-wrap items-center justify-between gap-3 px-6 py-4'}>
                <div>
                  <div className="text-[1.0625rem] font-semibold text-ink">{AGENCY_WORDS[r.action] ?? humanize(r.action)}</div>
                  <div className="text-[0.875rem] text-ink3">
                    <span className="font-mono">{r.id}</span> · asked {day(r.requested_on)} · {r.notice_sent_on ? `30-day notice sent ${day(r.notice_sent_on)}` : 'no 30-day notice sent'}
                  </div>
                </div>
                <Badge tone={r.status === 'BLOCKED' ? 'danger' : 'neutral'}>{r.status === 'BLOCKED' ? 'Blocked' : humanize(r.status)}</Badge>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {documents.length > 0 && (
        <Section className="mt-12" title="Documents, as exported" aside="Raw text. Quoted evidence is highlighted; hidden instructions in red">
          <div className="space-y-5">
            {documents.map((d) => (
              <DocumentBlock key={d.id} doc={d} story={story} />
            ))}
          </div>
        </Section>
      )}

      <Section className="mt-12" title="What every system says" aside="Each system keeps its own copy. They don't always agree.">
        <Sources sources={account.sources ?? {}} />
      </Section>

      <Section className="mt-12" title="Ledger" aside="Append-only. Mistakes are fixed with a reversal, never an edit.">
        {ledger.length === 0 ? (
          <p className="text-[1.0625rem] text-ink3">Nothing posted yet. Only the gateway posts, and only what a person approved (or a safe stop).</p>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-line bg-surface">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-line text-[0.8125rem] font-semibold uppercase tracking-wider text-ink3">
                  <th className="px-6 py-3">#</th>
                  <th className="px-4 py-3">Posted</th>
                  <th className="px-4 py-3">What</th>
                  <th className="px-4 py-3">Proposal</th>
                  <th className="px-6 py-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((l) => (
                  <tr key={l.seq} className="border-b border-line/60 last:border-b-0">
                    <td className="tnum px-6 py-3.5 font-mono text-[0.875rem] text-ink3">{l.seq}</td>
                    <td className="tnum px-4 py-3.5 text-ink2">{dayShort(l.posted_on)}</td>
                    <td className="px-4 py-3.5 font-medium text-ink">
                      {kindLabel(l.kind)}
                      {l.reverses && <span className="ml-2 font-mono text-[0.8rem] text-ink3">reverses {l.reverses}</span>}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-[0.875rem] text-ink3">{l.proposal_id}</td>
                    <td className="tnum px-6 py-3.5 text-right text-[1.0625rem] text-ink">{l.amount_cents ? money(l.amount_cents) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Correction accountId={account.id} source={source} />

      {!live && (
        <Section
          className="mt-12"
          title="Audit trail"
          aside={
            <Link to={`/audit?q=${encodeURIComponent(account.id)}${source === 'sample' ? '&sample=1' : ''}`} className="inline-flex items-center gap-1.5 font-medium text-accent hover:underline">
              Ask why in the audit log <IconArrowRight size={16} />
            </Link>
          }
        >
          {audit.length === 0 ? <p className="text-ink3">Nothing logged yet.</p> : <AuditList rows={audit} order="oldest" showAccount={false} />}
        </Section>
      )}
    </Page>
  );
}

/** A staff correction becomes a precedent; the AI looks for similar cases and may propose a rule. */
function Correction({ accountId, source }: { accountId: string; source: Source }) {
  const { current } = usePeople();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ r: CorrectionResult; source: Source } | null>(null);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    if (!current || !text.trim()) return;
    setBusy(true);
    setError(null);
    setRefusal(null);
    try {
      const out = await api.correction({ actor_id: current.id, account_id: accountId, correction: text.trim(), note: note.trim() }, source);
      setResult({ r: out.data, source: out.source });
      setText('');
      setNote('');
    } catch (e) {
      if (e instanceof Denied) setRefusal({ reason: e.reason, who: current.name, role: ROLE_LABEL[current.role] ?? current.role, at: new Date(), action: 'correct', target: accountId });
      else setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section className="mt-12" title="Correct the AI" aside="A correction becomes a precedent, then maybe a rule the director approves">
      {result && (
        <div className="mb-5 rounded-2xl border border-accent/25 bg-accent-tint px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-eyebrow font-bold uppercase text-accent-strong">Saved as precedent {result.r.precedent_id}</div>
              <p className="mt-1.5 text-[1.25rem] font-semibold text-ink">
                {result.r.message ?? `It found ${result.r.similar_cases} similar past cases${result.r.rule_proposal_id ? ' and proposed a rule for the director' : ''}.`}
              </p>
              <Link to="/learned" className="mt-2 inline-flex items-center gap-1.5 font-semibold text-accent hover:underline">
                See it on the Learned screen <IconArrowRight size={16} />
              </Link>
            </div>
            <SampleTag source={result.source} endpoint="/corrections" />
          </div>
        </div>
      )}
      {!open ? (
        <Button onClick={() => setOpen(true)}>Correct this account as {current?.name ?? '…'}</Button>
      ) : (
        <form
          className="space-y-3 rounded-2xl border border-line bg-surface p-6"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <label className="block text-[0.9375rem] font-medium text-ink2" htmlFor="correction">
            What should have happened?
          </label>
          <textarea
            id="correction"
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder="CalFresh enrollment means household income is at or under 200%. Give free care without income documents."
            className="w-full resize-y rounded-xl border border-line bg-white px-4 py-3 text-[1.0625rem] leading-relaxed outline-none focus:border-accent"
          />
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional): why"
            className="h-11 w-full rounded-xl border border-line bg-white px-4 text-[1rem] outline-none focus:border-accent"
          />
          <div className="flex items-center gap-2">
            <Button tone="primary" type="submit" disabled={busy || !text.trim()}>
              {busy ? 'Saving…' : 'Save the correction'}
            </Button>
            <Button tone="quiet" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {refusal && <GatewayRefusal refusal={refusal} onDismiss={() => setRefusal(null)} />}
      {error && <p className="mt-3 text-danger">{error}</p>}
    </Section>
  );
}

const AGENCY_WORDS: Record<string, string> = { CREDIT_REPORT: 'Report to credit bureaus', LAWSUIT: 'File a lawsuit', SELL_DEBT: 'Sell the debt', LIEN: 'Place a lien' };

/** A raw document with every quoted span marked: evidence in the accent, hidden instructions in red. */
function DocumentBlock({ doc, story }: { doc: CaseDocument; story: Story }) {
  const quotes: Array<{ q: string; tone: 'accent' | 'danger' }> = [];
  for (const p of story.proposals) for (const e of p.evidence ?? []) if (isFact(e) && e.document_id === doc.id && e.quote) quotes.push({ q: e.quote, tone: 'accent' });
  for (const a of story.audit) {
    const quote = (a.detail as { quote?: unknown; document_id?: unknown }) ?? {};
    if (a.action === 'follow_hidden_instructions' && a.target === doc.id && typeof quote.quote === 'string') quotes.push({ q: quote.quote, tone: 'danger' });
  }
  const hasHidden = quotes.some((x) => x.tone === 'danger');
  return (
    <article id={`doc-${doc.id}`} className={hasHidden ? 'scroll-mt-24 rounded-2xl border border-danger/30 bg-surface' : 'scroll-mt-24 rounded-2xl border border-line bg-surface'}>
      <header className="flex flex-wrap items-center gap-2 border-b border-line/70 px-5 py-3 text-[0.875rem]">
        <span className="font-mono font-semibold text-ink">{doc.id}</span>
        <Badge>{humanize(doc.kind)}</Badge>
        <span className="text-ink3">
          from {humanize(doc.source).toLowerCase()}
          {doc.dated ? ` · ${day(doc.dated)}` : ''}
        </span>
        {hasHidden && <Badge tone="danger">Hidden instructions ignored</Badge>}
      </header>
      <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words px-5 py-4 font-mono text-[0.8125rem] leading-relaxed text-ink2">{highlight(doc.text, quotes)}</pre>
    </article>
  );
}

function highlight(text: string, quotes: Array<{ q: string; tone: 'accent' | 'danger' }>): ReactNode {
  const marks: Array<{ start: number; end: number; tone: 'accent' | 'danger' }> = [];
  const lower = text.toLowerCase();
  for (const { q, tone } of quotes) {
    const needle = q.trim();
    if (!needle) continue;
    let at = text.indexOf(needle);
    if (at < 0) at = lower.indexOf(needle.toLowerCase());
    if (at >= 0) marks.push({ start: at, end: at + needle.length, tone });
  }
  if (!marks.length) return text;
  marks.sort((a, b) => a.start - b.start);
  const out: ReactNode[] = [];
  let pos = 0;
  marks.forEach((m, i) => {
    if (m.start < pos) return;
    if (m.start > pos) out.push(text.slice(pos, m.start));
    out.push(
      <mark key={i} className={m.tone === 'danger' ? 'rounded bg-danger/15 px-0.5 text-danger' : 'rounded bg-accent/15 px-0.5 text-ink'}>
        {text.slice(m.start, m.end)}
      </mark>,
    );
    pos = m.end;
  });
  if (pos < text.length) out.push(text.slice(pos));
  return out;
}
