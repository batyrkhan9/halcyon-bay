"""Start the demo on any machine in one command, no API key needed.

Loads Claude's saved replies (core/fixtures/), onboards the history with the day-one
discovery, replays the live days up to the one you choose with the agent working them,
builds the screens the first time (Node.js needed for that), then serves the screens and
the API together at http://localhost:8000. Every reading the demo needs is replayed from the saved
replies, so nothing calls Claude and nothing is spent. Without CRS credentials, CRS
answers come from Noriaki's recorded sandbox answers.

Only the truly live moments need ANTHROPIC_API_KEY in .env: the judge's own patient and
a new staff correction, since those are new readings.

From the repo root:
  core/.venv/bin/python -m core.demo                     # demo at 2026-07-14, open http://localhost:8000
  core/.venv/bin/python -m core.demo --day 2026-09-30    # the end of the run, where the score is final
  core/.venv/bin/python -m core.demo --api-only          # the API alone on port 8000, for UI development
  core/.venv/bin/python -m core.demo --no-serve          # build the database only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

from .agent import Agent
from .config import ROOT
from .discovery import discover
from .reader import Reader, ReadFailed, ReplyCache, import_replies
from .store import Store
from .sync import Sync

FIXTURES = ROOT / "core" / "fixtures"
UI = ROOT / "ui"
BUILT_MARK = UI / "dist" / ".built-for-core"
DEMO_DB = ROOT / "core" / "state" / "demo.db"
DEFAULT_DAY = date(2026, 7, 14)
FIRST_LIVE_DAY = date(2026, 7, 1)
LAST_LIVE_DAY = date(2026, 9, 30)


def build(day: date, path: Path = DEMO_DB) -> Store:
    cache = ReplyCache()
    loaded = sum(import_replies(cache, f) for f in sorted(FIXTURES.glob("*_replies.json")))
    print(f"Loaded {loaded} saved Claude replies.")
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    store = Store(path)
    sync = Sync(store)
    sync.onboard()
    found = discover(store, cache=cache)
    print(f"Onboarded the history. Day one: {len(found['findings'])} findings, ${found['total_cents'] / 100:,.2f}.")
    agent = Agent(store, sync.gateway, Reader(store, cache=cache))
    current = FIRST_LIVE_DAY
    while current <= day:
        sync.day(current)
        agent.work_open_items()
        current += timedelta(days=1)
    counts = {r["state"]: r["n"] for r in store.all("SELECT state, COUNT(*) AS n FROM work_items GROUP BY state")}
    print(f"Replayed to {day}: {counts}")
    return store


def build_ui() -> Path:
    """Build the screens to call this API at /api. Only when they changed since the last build."""
    sources = [p for p in [*(UI / "src").rglob("*"), UI / "index.html", UI / "package.json", UI / "package-lock.json"]
               if p.is_file()]
    if BUILT_MARK.is_file() and BUILT_MARK.stat().st_mtime >= max(p.stat().st_mtime for p in sources):
        return UI / "dist"
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("Building the screens needs Node.js once: install it from nodejs.org, then run this again.")
    if not (UI / "node_modules").is_dir():
        print("Installing the screens' packages (once)...")
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=UI, check=True)
    print("Building the screens...")
    subprocess.run([npm, "run", "build"], cwd=UI, check=True, env={**os.environ, "VITE_CORE_URL": "/api"})
    BUILT_MARK.write_text("Built by core.demo to call the API at /api.\n")
    return UI / "dist"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", type=date.fromisoformat, default=DEFAULT_DAY,
                    help=f"the live day the demo starts on (default {DEFAULT_DAY})")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-serve", action="store_true", help="build the demo database and stop")
    ap.add_argument("--api-only", action="store_true", help="serve the API alone, for UI development")
    args = ap.parse_args()
    if not FIRST_LIVE_DAY <= args.day <= LAST_LIVE_DAY:
        raise SystemExit(f"--day must be between {FIRST_LIVE_DAY} and {LAST_LIVE_DAY}.")
    try:
        build(args.day)
    except ReadFailed as e:
        raise SystemExit(f"Stopped: a reading the demo needs isn't saved, and Claude isn't reachable ({e}).\n"
                         "Pick an earlier --day, or put ANTHROPIC_API_KEY in .env.") from None
    if args.no_serve:
        print(f"Demo database ready: {DEMO_DB}")
        return
    import uvicorn

    from .api import create_app, with_ui

    os.environ["HALCYON_DB"] = str(DEMO_DB)
    api = create_app(Store(DEMO_DB))
    if args.api_only:
        print(f"Core API on http://localhost:{args.port}. Start the UI with: npm --prefix ui run dev")
        uvicorn.run(api, port=args.port)
        return
    app = with_ui(api, build_ui())
    print(f"\nThe demo is ready: open http://localhost:{args.port}\n")
    uvicorn.run(app, port=args.port)


if __name__ == "__main__":
    main()
