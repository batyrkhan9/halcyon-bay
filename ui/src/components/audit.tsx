import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { AuditRow } from '../api/types';
import { clock, dayShort, humanize, money, ROLE_SHORT } from '../lib/format';
import { usePeople } from '../lib/people';
import { IconShield } from './icons';
import { cx } from './ui';

const ACTION_WORDS: Record<string, string> = {
  open_work_item: 'opened',
  move_work_item: 'moved',
  propose: 'proposed',
  ask: 'asked',
  answer: 'answered',
  act_safe: 'acted alone',
  approve: 'approved',
  reject: 'rejected',
  post: 'posted',
  correct: 'corrected',
  crs_check: 'checked CRS',
  flag_document: 'flagged a document',
  read_document: 'read a document',
  learn_pattern: 'learned',
  flag_pattern: 'flagged',
  load_history: 'loaded history',
  discover: 'discovered',
  sync_day: 'synced',
  match_identity: 'matched identity',
  wait: 'waiting',
  read_intake: 'read the intake',
  check_law: 'checked the law',
  route: 'routed',
  apply_rule: 'applied a rule',
};

function actionWord(row: AuditRow): string {
  if (!row.allowed) return `tried to ${humanize(row.action).toLowerCase()}`;
  return ACTION_WORDS[row.action] ?? humanize(row.action).toLowerCase();
}

function detailLine(row: AuditRow): string | null {
  const d = row.detail ?? {};
  if (row.action === 'move_work_item' && d.from && d.to) return `${String(d.from)} → ${String(d.to)}`;
  if ((row.action === 'post' || row.action === 'propose') && typeof d.amount_cents === 'number' && d.amount_cents) return `${humanize(String(d.kind ?? ''))} · ${money(d.amount_cents)}`;
  if (row.action === 'post' && d.kind) return humanize(String(d.kind));
  return null;
}

/** The append-only log. Blocked attempts stand out. New rows flash when they arrive. */
export function AuditList({ rows, showAccount = true, order = 'newest', compact }: { rows: AuditRow[]; showAccount?: boolean; order?: 'newest' | 'oldest'; compact?: boolean }) {
  const { nameOf } = usePeople();
  const seen = useRef<Set<number> | null>(null);
  const [fresh, setFresh] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (seen.current === null) {
      seen.current = new Set(rows.map((r) => r.seq));
      return;
    }
    const added = rows.filter((r) => !seen.current!.has(r.seq)).map((r) => r.seq);
    if (added.length) {
      added.forEach((s) => seen.current!.add(s));
      setFresh(new Set(added));
    }
  }, [rows]);

  const list = order === 'newest' ? rows : [...rows].sort((a, b) => a.seq - b.seq);
  return (
    <ol className="divide-y divide-line/70 overflow-hidden rounded-2xl border border-line bg-surface">
      {list.map((r) => {
        const detail = detailLine(r);
        const isPerson = !['agent', 'gateway', 'sync'].includes(r.actor_role);
        return (
          <li
            key={r.seq}
            className={cx(
              'relative grid grid-cols-[4.5rem_1fr] gap-4 px-5 md:grid-cols-[5.5rem_12rem_1fr]',
              compact ? 'py-3' : 'py-4',
              !r.allowed && 'bg-danger-tint/70',
              fresh.has(r.seq) && 'animate-flash',
            )}
          >
            {!r.allowed && <span className="absolute inset-y-0 left-0 w-1 bg-danger" />}
            <div className="pt-0.5 text-[0.8125rem] text-ink3">
              <div className="tnum font-mono">#{r.seq}</div>
              <div>{dayShort(r.sim_day)}</div>
              <div className="tnum">{clock(r.logged_at)}</div>
            </div>
            <div className="hidden pt-0.5 md:block">
              <div className={cx('font-semibold', isPerson ? 'text-ink' : r.actor_role === 'gateway' ? 'text-accent-strong' : 'text-ink2')}>{nameOf(r.actor_id)}</div>
              <div className="text-[0.8125rem] text-ink3">{isPerson ? (ROLE_SHORT[r.actor_role] ?? r.actor_role) : 'system'}</div>
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.875rem]">
                <span className="font-semibold text-ink md:hidden">{nameOf(r.actor_id)}</span>
                {!r.allowed ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-danger px-1.5 py-0.5 text-[0.75rem] font-bold uppercase tracking-wider text-white">
                    <IconShield size={13} /> Blocked
                  </span>
                ) : null}
                <span className={cx('font-medium', r.allowed ? 'text-ink2' : 'text-danger')}>{actionWord(r)}</span>
                {r.target && <span className="font-mono text-[0.8rem] text-ink3">{r.target}</span>}
                {showAccount && r.account_id && (
                  <Link to={`/accounts/${r.account_id}`} className="font-mono text-[0.8rem] text-accent hover:underline">
                    {r.account_id}
                  </Link>
                )}
              </div>
              <p className={cx('mt-1 leading-relaxed', r.allowed ? 'text-[1rem] text-ink' : 'text-[1.0625rem] font-semibold text-ink')}>{r.reason}</p>
              {detail && <p className="mt-0.5 text-[0.875rem] text-ink3">{detail}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
