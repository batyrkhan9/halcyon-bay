// Typed client for every endpoint in core/INTERFACE.md.
//
// "Live now" endpoints always go to the core. If the core can't be reached they answer from the
// sample world so the screens never go blank, and the screen shows a "sample data" tag.
// "Coming" endpoints are called too; a 404/405/501 or an unreachable core falls back to the
// sample world. Once the core ships an endpoint, the screen lights up with real data on its own.
// VITE_MOCK=1 forces the sample world everywhere (no core needed at all).

import { mock } from '../mock/engine';
import type {
  AccountStory,
  Actor,
  AuditQuery,
  AuditRow,
  CoreState,
  CorrectionIn,
  CorrectionResult,
  Inbox,
  JudgeBoxResult,
  Proposal,
  Question,
  WorkItem,
  WorkState,
} from './types';
import { normalizeDiscovery, normalizeLearned, normalizeScore } from './normalize';
import { Denied, HttpError, Unreachable } from './errors';

export { Denied, HttpError, Unreachable };

export const CORE_URL = String(import.meta.env.VITE_CORE_URL || 'http://localhost:8000').replace(/\/+$/, '');
export const FORCE_MOCK = ['1', 'true', 'yes'].includes(String(import.meta.env.VITE_MOCK || '').toLowerCase());

export type Source = 'core' | 'sample';
export interface Sourced<T> {
  data: T;
  source: Source;
}

// ---- core reachability, for the status line in the rail ----
type Reach = 'unknown' | 'up' | 'down';
let reach: Reach = 'unknown';
const reachListeners = new Set<(r: Reach) => void>();
function setReach(r: Reach) {
  if (r === reach) return;
  reach = r;
  reachListeners.forEach((fn) => fn(r));
}
export function coreReach(): Reach {
  return reach;
}
export function onCoreReach(fn: (r: Reach) => void): () => void {
  reachListeners.add(fn);
  return () => reachListeners.delete(fn);
}

// ---- "something changed" bus: every screen refetches right after an action ----
const changeListeners = new Set<() => void>();
export function onChanged(fn: () => void): () => void {
  changeListeners.add(fn);
  return () => changeListeners.delete(fn);
}
export function announceChange() {
  changeListeners.forEach((fn) => fn());
}
mock.subscribe(() => announceChange());

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(CORE_URL + path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(method === 'GET' ? 8_000 : 180_000),
    });
  } catch (e) {
    setReach('down');
    throw new Unreachable(e instanceof Error ? e.message : String(e));
  }
  setReach('up');
  if (res.status === 403) {
    const j = (await res.json().catch(() => ({}))) as { reason?: string; detail?: string };
    throw new Denied(j.reason || j.detail || 'The gateway refused this action.');
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (j && j.detail !== undefined) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not JSON */
    }
    throw new HttpError(res.status, detail);
  }
  return (await res.json()) as T;
}

const notShipped = (e: unknown) =>
  e instanceof Unreachable ||
  (e instanceof HttpError && ((e.status === 404 && e.message === 'Not Found') || e.status === 405 || e.status === 501));

async function live<T>(core: () => Promise<T>, sample: () => T | Promise<T>): Promise<Sourced<T>> {
  if (FORCE_MOCK) return { data: await sample(), source: 'sample' };
  try {
    return { data: await core(), source: 'core' };
  } catch (e) {
    if (e instanceof Unreachable) return { data: await sample(), source: 'sample' };
    throw e;
  }
}

// A "Coming" endpoint that 404'd is re-probed every 15 s, not on every poll.
const missingUntil = new Map<string, number>();
const REPROBE_MS = 15_000;

async function coming<T>(core: () => Promise<T>, sample: () => T | Promise<T>, key?: string): Promise<Sourced<T>> {
  if (FORCE_MOCK) return { data: await sample(), source: 'sample' };
  if (key && (missingUntil.get(key) ?? 0) > Date.now()) return { data: await sample(), source: 'sample' };
  try {
    const data = await core();
    if (key) missingUntil.delete(key);
    return { data, source: 'core' };
  } catch (e) {
    if (notShipped(e)) {
      if (key) missingUntil.set(key, Date.now() + REPROBE_MS);
      return { data: await sample(), source: 'sample' };
    }
    throw e;
  }
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

const useSample = (source: Source) => FORCE_MOCK || source === 'sample';

const pinned = new Set<string>();
/** A screen whose "Coming" action fell back to the sample world keeps showing that world. */
export function pinSample(screen: string) {
  pinned.add(screen);
}
export function unpinSample(screen: string) {
  pinned.delete(screen);
}
export function isPinned(screen: string): boolean {
  return FORCE_MOCK || pinned.has(screen);
}

export const api = {
  // ---------- Live now ----------
  state: (source: Source = 'core') =>
    useSample(source)
      ? Promise.resolve<Sourced<CoreState>>({ data: mock.state(), source: 'sample' })
      : live(() => call<CoreState>('GET', '/state'), () => mock.state()),

  actors: () =>
    live(
      async () => {
        const people = await call<Actor[]>('GET', '/actors');
        mock.adoptStaff(people);
        return people;
      },
      () => mock.actors(),
    ),

  workItems: (state?: WorkState, limit = 500, source: Source = 'core') =>
    useSample(source)
      ? Promise.resolve<Sourced<WorkItem[]>>({ data: mock.workItems(state, limit), source: 'sample' })
      : live(
      () => call<WorkItem[]>('GET', `/work-items${qs({ state, limit })}`),
      () => mock.workItems(state, limit),
    ),

  inbox: (actorId: string, source: Source = 'core') =>
    useSample(source)
      ? Promise.resolve<Sourced<Inbox>>({ data: mock.inbox(actorId), source: 'sample' })
      : live(() => call<Inbox>('GET', `/inbox/${encodeURIComponent(actorId)}`), () => mock.inbox(actorId)),

  /** An account's whole story. A 404 from the core falls back to the sample world if it knows the account. */
  account: async (accountId: string): Promise<Sourced<AccountStory>> => {
    if (FORCE_MOCK) return { data: mock.account(accountId), source: 'sample' };
    try {
      return { data: await call<AccountStory>('GET', `/accounts/${encodeURIComponent(accountId)}`), source: 'core' };
    } catch (e) {
      if ((e instanceof Unreachable || (e instanceof HttpError && e.status === 404)) && mock.hasAccount(accountId)) {
        return { data: mock.account(accountId), source: 'sample' };
      }
      throw e;
    }
  },

  audit: (query: AuditQuery, source: Source = 'core') =>
    useSample(source)
      ? Promise.resolve<Sourced<AuditRow[]>>({ data: mock.audit(query), source: 'sample' })
      : live(
          () =>
            call<AuditRow[]>(
              'GET',
              `/audit${qs({ account_id: query.account_id, actor_id: query.actor_id, allowed: query.allowed, q: query.q, limit: query.limit ?? 200 })}`,
            ),
          () => mock.audit(query),
        ),

  /** Approve or reject. Throws Denied with the gateway's reason on 403. */
  decide: async (proposalId: string, actorId: string, approve: boolean, note: string, source: Source): Promise<Proposal> => {
    try {
      return useSample(source)
        ? mock.decide(proposalId, actorId, approve, note)
        : await call<Proposal>('POST', `/proposals/${encodeURIComponent(proposalId)}/decision`, {
            actor_id: actorId,
            approve,
            note,
          });
    } finally {
      announceChange();
    }
  },

  answer: async (questionId: string, actorId: string, answer: string, source: Source): Promise<Question> => {
    try {
      return useSample(source)
        ? mock.answer(questionId, actorId, answer)
        : await call<Question>('POST', `/questions/${encodeURIComponent(questionId)}/answer`, { actor_id: actorId, answer });
    } finally {
      announceChange();
    }
  },

  // ---------- Coming ----------
  advance: async (days = 1): Promise<Sourced<CoreState>> => {
    const out = await coming(() => call<CoreState>('POST', '/sim/advance', { days }), () => mock.advance(days));
    announceChange();
    return out;
  },

  discovery: () =>
    coming(
      async () => normalizeDiscovery(await call<unknown>('GET', '/discovery')),
      () => mock.discovery(),
      'discovery',
    ),

  learned: () =>
    coming(
      async () => normalizeLearned(await call<unknown>('GET', '/learned')),
      () => mock.learned(),
      'learned',
    ),

  correction: async (body: CorrectionIn, source: Source): Promise<Sourced<CorrectionResult>> => {
    try {
      return useSample(source)
        ? { data: mock.correction(body), source: 'sample' as const }
        : await coming(() => call<CorrectionResult>('POST', '/corrections', body), () => mock.correction(body));
    } finally {
      announceChange();
    }
  },

  score: () =>
    coming(
      async () => normalizeScore(await call<unknown>('GET', '/score')),
      () => mock.score(),
      'score',
    ),

  judgeBox: async (text: string): Promise<Sourced<JudgeBoxResult>> => {
    const out = await coming(() => call<JudgeBoxResult>('POST', '/judge-box', { text }), () => mock.judgeBox(text));
    announceChange();
    return out;
  },
};

export function errorText(e: unknown): string {
  if (e instanceof Denied) return e.reason;
  if (e instanceof Unreachable) return `The core isn't reachable at ${CORE_URL}.`;
  if (e instanceof HttpError) return e.status === 404 ? `Not found: ${e.message}` : `${e.status}: ${e.message}`;
  if (e instanceof Error) return e.message;
  return String(e);
}
