# Halcyon Bay screens

The UI for the billing office. Vite + React + TypeScript + Tailwind. It only talks to the core (`core/INTERFACE.md`), never to CRS or any other third party.

## Run

```bash
cd ui
npm install
npm run dev        # http://localhost:5173
npm run build      # type-checks (zero errors) and builds to ui/dist
```

## Environment

| Variable | Default | What it does |
|---|---|---|
| `VITE_CORE_URL` | `http://localhost:8000` | Where the core runs |
| `VITE_MOCK` | off | `VITE_MOCK=1` runs the whole app on the built-in sample world, no core needed (for recording if the core is down) |

```bash
VITE_CORE_URL=http://localhost:8010 npm run dev   # a core on another port
VITE_MOCK=1 npm run dev                           # no core at all
```

## Live and sample data

- "Live now" endpoints always come from the core. If the core can't be reached, the screen falls back to the sample world.
- "Coming" endpoints (`/sim/advance`, `/discovery`, `/learned`, `/corrections`, `/score`, `/judge-box`) are called too. A 404 falls back to the sample world. Once the core ships one, its screen switches to live data by itself (missing endpoints are re-checked every 15 seconds).
- Any screen showing sample data carries a small dashed **sample data** tag, so a recording stays honest.
- The sample world lives in memory: a full page reload resets it, which is handy between takes. Moving between screens keeps it.

## Screens

| Path | Screen |
|---|---|
| `/` | Today: simulated date, work by state, **Run next day**, what needs the current person |
| `/discovery` | Day one: illegal denials found in history, the law, the dollars, approve all as compliance |
| `/work` | Every account being worked, filter by state, search |
| `/accounts/:id` | The account's story: decisions, what every system says (incl. CRS), ledger, audit trail, corrections. `?live=1` polls every second |
| `/learned` | Patterns from history (learned or flagged), precedents, rules with backtests, never proposed again |
| `/audit` | The append-only log, blocked actions marked, one search box for "why?" |
| `/score` | Precision, share handled automatically, dollars to charity, payment plans, violations prevented |
| `/judge` | A judge types a patient in plain English and watches it get worked live |

## Acting as a person

The header switches person instantly: click, or press `1` counselor, `2` director, `3` compliance, `4` the second counselor (Tomas Brandt, who is also a patient). Each person shows how many things wait for them. Approve and reject buttons are shown to everyone on purpose: the gateway decides, and a refusal (403) appears inline in red with its reason, exactly as the core wrote it.

## Files

```
src/api/        client.ts (every INTERFACE.md endpoint), types.ts, normalize.ts, errors.ts
src/mock/       the sample world: engine.ts (same answers as the core), seed.ts (planted stories), law.ts
src/screens/    one file per screen
src/components/ shell, decisions (proposal / question cards, gateway refusal), sources, audit list
```

Requests for the core are in `NOTES_FOR_CORE.md`.
