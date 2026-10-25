import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, Denied, errorText, type Source } from '../api/client';
import type { Proposal, Question } from '../api/types';
import { amountMeaning, day, deciderRole, kindLabel, money, ROLE_LABEL, SAFE_KINDS, titleCase } from '../lib/format';
import { usePeople } from '../lib/people';
import { IconCheck, IconQuestion, IconShield, IconX } from './icons';
import { Badge, Button, cx } from './ui';
import { EvidenceList } from './sources';

export interface Refusal {
  reason: string;
  who: string;
  role: string;
  at: Date;
  action: string;
  target: string;
}

/** The gateway said no. Big, plain and already in the audit log. */
export function GatewayRefusal({ refusal, onDismiss }: { refusal: Refusal; onDismiss?: () => void }) {
  return (
    <div role="alert" className="animate-shake mt-5 overflow-hidden rounded-2xl border border-danger/25 bg-danger-tint">
      <div className="flex items-start gap-4 px-5 py-4">
        <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-danger text-white">
          <IconShield size={22} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-eyebrow font-bold uppercase text-danger">Gateway refused · logged to the audit trail</div>
          <p className="mt-1.5 text-[1.375rem] font-semibold leading-snug tracking-[-0.01em] text-ink">{refusal.reason}</p>
          <p className="mt-1.5 text-[0.9375rem] text-ink2">
            {refusal.who} ({refusal.role}) tried to {refusal.action} {refusal.target} ·{' '}
            {refusal.at.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' })}
          </p>
        </div>
        {onDismiss && (
          <button type="button" onClick={onDismiss} className="rounded-lg p-1.5 text-ink3 hover:bg-white/60 hover:text-ink" aria-label="Dismiss">
            <IconX size={18} />
          </button>
        )}
      </div>
    </div>
  );
}

function DecidedLine({ p }: { p: Proposal }) {
  const { nameOf } = usePeople();
  if (SAFE_KINDS.includes(p.kind) && p.proposed_by === 'agent' && p.status !== 'PROPOSED') {
    return (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.9375rem] text-ink2">
        <IconCheck size={18} className="text-accent" />
        <span>
          <b className="font-semibold text-ink">Done by the AI alone</b>: stopping a collection is always safe.
        </span>
        {p.status === 'POSTED' && <span className="text-ink3">Posted by the gateway {day(p.decided_on)}.</span>}
      </div>
    );
  }
  if (p.status === 'POSTED' || p.status === 'APPROVED') {
    return (
      <div className="text-[0.9375rem] text-ink2">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <IconCheck size={18} className="text-accent" />
          <span>
            Approved by <b className="font-semibold text-ink">{nameOf(p.decided_by)}</b> on {day(p.decided_on)}
          </span>
          {p.status === 'POSTED' && <span className="text-ink3">· posted by the gateway</span>}
        </div>
        {p.decision_note && <p className="ml-[26px] mt-1 text-ink2">“{p.decision_note}”</p>}
      </div>
    );
  }
  if (p.status === 'REJECTED') {
    return (
      <div className="text-[0.9375rem] text-ink2">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <IconX size={18} className="text-danger" />
          <span>
            Rejected by <b className="font-semibold text-ink">{nameOf(p.decided_by)}</b> on {day(p.decided_on)}
          </span>
        </div>
        {p.decision_note && <p className="ml-[26px] mt-1 text-ink2">“{p.decision_note}”</p>}
        {p.pattern && <p className="ml-[26px] mt-1 font-medium text-ink">Stored. It will never be proposed again.</p>}
      </div>
    );
  }
  return null;
}

/** One proposal: what, how much, why, the evidence, and approve / reject for the current person. */
export function ProposalCard({ proposal: p, source, compact, showAccount }: { proposal: Proposal; source: Source; compact?: boolean; showAccount?: boolean }) {
  const { current, nameOf } = usePeople();
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState('');
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const decider = deciderRole(p);
  const meaning = amountMeaning(p);
  const open = p.status === 'PROPOSED';

  const decide = async (approve: boolean) => {
    if (!current) return;
    setBusy(true);
    setError(null);
    setRefusal(null);
    try {
      await api.decide(p.id, current.id, approve, approve ? '' : note.trim(), source);
      setRejecting(false);
      setNote('');
    } catch (e) {
      if (e instanceof Denied) {
        setRefusal({ reason: e.reason, who: current.name, role: ROLE_LABEL[current.role] ?? current.role, at: new Date(), action: approve ? 'approve' : 'reject', target: p.id });
      } else setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className={cx('rounded-2xl border bg-surface transition-shadow', open ? 'border-line shadow-lift' : 'border-line/70', compact ? 'p-5' : 'p-6')}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[0.8125rem] font-medium text-ink3">
            <span className="font-mono text-[0.78rem]">{p.id}</span>
            {p.legal_question && <Badge tone="warn">How the law applies</Badge>}
            {p.pattern && p.kind === 'NEW_RULE' && <Badge>pattern {p.pattern}</Badge>}
            {showAccount && p.account_id && (
              <Link to={`/accounts/${p.account_id}`} className="font-mono text-[0.78rem] text-accent hover:underline">
                {p.account_id}
              </Link>
            )}
          </div>
          <h3 className={cx('mt-1.5 font-semibold tracking-[-0.015em] text-ink', compact ? 'text-xl' : 'text-[1.5rem]')}>{kindLabel(p.kind)}</h3>
        </div>
        {meaning && (
          <div className="text-right">
            <div className={cx('tnum font-semibold tracking-[-0.03em] text-ink', compact ? 'text-2xl' : 'text-[2rem] leading-none')}>{money(p.amount_cents)}</div>
            <div className="mt-1 text-[0.8125rem] text-ink3">{meaning}</div>
          </div>
        )}
      </div>

      <p className={cx('mt-4 leading-relaxed text-ink', compact ? 'line-clamp-3 text-[1rem]' : 'text-[1.0625rem]')}>{p.rationale}</p>

      {!compact && p.evidence?.length > 0 && <EvidenceList evidence={p.evidence} />}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-line/70 pt-4">
        {open ? (
          <div className="text-[0.9375rem] text-ink3">
            Proposed by {nameOf(p.proposed_by)} on {day(p.proposed_on)}
            {decider && (
              <>
                {' '}
                · <span className="text-ink2">the {ROLE_LABEL[decider]?.toLowerCase()} decides</span>
              </>
            )}
          </div>
        ) : (
          <DecidedLine p={p} />
        )}
        {open && current && (
          <div className="flex flex-wrap items-center gap-2">
            {!rejecting ? (
              <>
                <Button tone="quiet" onClick={() => setRejecting(true)} disabled={busy}>
                  Reject
                </Button>
                <Button tone="primary" onClick={() => void decide(true)} disabled={busy}>
                  <IconCheck size={18} />
                  Approve as {current.name.split(' ')[0]}
                </Button>
              </>
            ) : (
              <form
                className="flex flex-wrap items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void decide(false);
                }}
              >
                <input
                  autoFocus
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Why not? (stored with the decision)"
                  className="h-10 w-72 rounded-xl border border-line bg-white px-3 text-[0.9375rem] outline-none focus:border-accent"
                />
                <Button tone="quiet" onClick={() => setRejecting(false)} disabled={busy}>
                  Cancel
                </Button>
                <Button tone="danger" type="submit" disabled={busy}>
                  Reject as {current.name.split(' ')[0]}
                </Button>
              </form>
            )}
          </div>
        )}
      </div>
      {refusal && <GatewayRefusal refusal={refusal} onDismiss={() => setRefusal(null)} />}
      {error && <p className="mt-3 text-[0.9375rem] text-danger">{error}</p>}
    </article>
  );
}

export function QuestionCard({ question: q, source, showAccount }: { question: Question; source: Source; showAccount?: boolean }) {
  const { current, nameOf } = usePeople();
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = q.answer === null;

  const send = async () => {
    if (!current || !answer.trim()) return;
    setBusy(true);
    setRefusal(null);
    setError(null);
    try {
      await api.answer(q.id, current.id, answer.trim(), source);
      setAnswer('');
    } catch (e) {
      if (e instanceof Denied) setRefusal({ reason: e.reason, who: current.name, role: ROLE_LABEL[current.role] ?? current.role, at: new Date(), action: 'answer', target: q.id });
      else setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className={cx('rounded-2xl border p-6', open ? 'border-warn/30 bg-warn-tint/50' : 'border-line/70 bg-surface')}>
      <div className="flex flex-wrap items-center gap-2 text-[0.8125rem] font-medium text-ink3">
        <IconQuestion size={16} className={open ? 'text-warn' : 'text-ink3'} />
        <span className="font-mono text-[0.78rem]">{q.id}</span>
        <span>
          asked by {nameOf(q.asked_by)} on {day(q.asked_on)}, for the {ROLE_LABEL[q.to_role]?.toLowerCase() ?? q.to_role}
        </span>
        {showAccount && (
          <Link to={`/accounts/${q.account_id}`} className="font-mono text-[0.78rem] text-accent hover:underline">
            {q.account_id}
          </Link>
        )}
      </div>
      <p className="mt-2.5 text-[1.1875rem] font-medium leading-relaxed text-ink">{q.question}</p>
      {open ? (
        <form
          className="mt-4 flex flex-wrap items-start gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <input
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder={current ? `Answer as ${current.name}` : 'Answer'}
            className="h-11 min-w-[16rem] flex-1 rounded-xl border border-line bg-white px-4 text-[1rem] outline-none focus:border-accent"
          />
          <Button tone="primary" type="submit" disabled={busy || !answer.trim()} className="h-11">
            Send answer
          </Button>
        </form>
      ) : (
        <div className="mt-3 border-l-2 border-accent pl-4">
          <p className="text-[1.0625rem] text-ink">“{q.answer}”</p>
          <p className="mt-1 text-[0.875rem] text-ink3">
            {nameOf(q.answered_by)}, {day(q.answered_on)}
          </p>
        </div>
      )}
      {refusal && <GatewayRefusal refusal={refusal} onDismiss={() => setRefusal(null)} />}
      {error && <p className="mt-3 text-[0.9375rem] text-danger">{error}</p>}
    </article>
  );
}

export function PatientLink({ id, name }: { id: string | null; name?: string | null }) {
  if (!id) return <span className="text-ink3">—</span>;
  return (
    <Link to={`/accounts/${id}`} className="group inline-flex flex-col">
      <span className="font-semibold text-ink group-hover:text-accent">{titleCase(name)}</span>
      <span className="font-mono text-[0.78rem] text-ink3">{id}</span>
    </Link>
  );
}

/** Approve / reject plumbing shared by rows that aren't full cards (day-one list, rules). */
export function useDecision(source: Source) {
  const { current } = usePeople();
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const decide = async (p: Proposal, approve: boolean, note = ''): Promise<boolean> => {
    if (!current) return false;
    setBusy(true);
    setError(null);
    setRefusal(null);
    try {
      await api.decide(p.id, current.id, approve, note, source);
      return true;
    } catch (e) {
      if (e instanceof Denied) setRefusal({ reason: e.reason, who: current.name, role: ROLE_LABEL[current.role] ?? current.role, at: new Date(), action: approve ? 'approve' : 'reject', target: p.id });
      else setError(errorText(e));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { decide, busy, refusal, setRefusal, error };
}
