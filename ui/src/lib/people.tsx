import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, FORCE_MOCK, onChanged, type Source } from '../api/client';
import type { Actor, Role } from '../api/types';

const SYSTEM_NAMES: Record<string, string> = { agent: 'AI agent', gateway: 'Gateway', sync: 'Sync job' };
const STORAGE_KEY = 'halcyon.actor';

interface People {
  ready: boolean;
  source: Source | undefined;
  /** Ordered for the switcher: the first counselor, the director, the compliance officer, then everyone else. */
  people: Actor[];
  current: Actor | null;
  setCurrent: (id: string) => void;
  inboxCounts: Record<string, number>;
  nameOf: (id: string | null | undefined) => string;
  roleOf: (id: string | null | undefined) => Role | undefined;
  firstWithRole: (role: Role) => Actor | undefined;
}

const Ctx = createContext<People | null>(null);

function order(actors: Actor[]): Actor[] {
  const byId = [...actors].sort((a, b) => a.id.localeCompare(b.id));
  const primaries: Actor[] = [];
  for (const role of ['counselor', 'director', 'compliance'] as const) {
    const a = byId.find((x) => x.role === role);
    if (a) primaries.push(a);
  }
  return [...primaries, ...byId.filter((a) => !primaries.includes(a))];
}

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function store(id: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* private window: fine */
  }
}

export function PeopleProvider({ children }: { children: ReactNode }) {
  const [actors, setActors] = useState<Actor[]>([]);
  const [source, setSource] = useState<Source | undefined>();
  const [currentId, setCurrentId] = useState<string | null>(readStored());
  const [inboxCounts, setInboxCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const load = async () => {
      try {
        const r = await api.actors();
        if (!alive) return;
        setActors((prev) => (JSON.stringify(prev) === JSON.stringify(r.data) ? prev : r.data));
        setSource(r.source);
        // On the sample world because the core was down: keep checking until it is back.
        if (r.source === 'sample' && !FORCE_MOCK) timer = window.setTimeout(load, 5000);
      } catch {
        timer = window.setTimeout(load, 3000);
      }
    };
    void load();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, []);

  const people = useMemo(() => order(actors), [actors]);
  const current = useMemo(() => people.find((p) => p.id === currentId) ?? people[0] ?? null, [people, currentId]);

  const setCurrent = useCallback((id: string) => {
    setCurrentId(id);
    store(id);
  }, []);

  // Inbox counts for every person, so the switcher shows who has work waiting.
  useEffect(() => {
    if (!people.length) return;
    let alive = true;
    let sent = 0;
    let applied = 0;
    const refresh = async () => {
      const id = ++sent;
      const entries = await Promise.all(
        people.map(async (p) => {
          try {
            const r = await api.inbox(p.id);
            return [p.id, r.data.proposals.length + r.data.questions.length] as const;
          } catch {
            return [p.id, 0] as const;
          }
        }),
      );
      if (!alive || id < applied) return;
      applied = id;
      setInboxCounts(Object.fromEntries(entries));
    };
    void refresh();
    const t = window.setInterval(refresh, 4000);
    const off = onChanged(() => void refresh());
    return () => {
      alive = false;
      window.clearInterval(t);
      off();
    };
  }, [people]);

  // Keyboard 1..9 switches person instantly (not while typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))) return;
      const n = Number(e.key);
      if (Number.isInteger(n) && n >= 1 && n <= people.length) {
        setCurrent(people[n - 1].id);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [people, setCurrent]);

  const nameOf = useCallback(
    (id: string | null | undefined) => {
      if (!id) return '—';
      return SYSTEM_NAMES[id] ?? actors.find((a) => a.id === id)?.name ?? id;
    },
    [actors],
  );
  const roleOf = useCallback(
    (id: string | null | undefined) => {
      if (!id) return undefined;
      if (SYSTEM_NAMES[id]) return id as Role;
      return actors.find((a) => a.id === id)?.role;
    },
    [actors],
  );
  const firstWithRole = useCallback((role: Role) => people.find((p) => p.role === role), [people]);

  const value = useMemo<People>(
    () => ({ ready: actors.length > 0, source, people, current, setCurrent, inboxCounts, nameOf, roleOf, firstWithRole }),
    [actors.length, source, people, current, setCurrent, inboxCounts, nameOf, roleOf, firstWithRole],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePeople(): People {
  const v = useContext(Ctx);
  if (!v) throw new Error('usePeople outside PeopleProvider');
  return v;
}
