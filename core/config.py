"""Settings from the environment. The repo root's .env is loaded first; it is never committed."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Set each KEY=value line that has a value and isn't already in the environment."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if value and key not in os.environ:
            os.environ[key] = value


load_dotenv(ROOT / ".env")

DEFAULT_DB = str(ROOT / "core" / "state" / "halcyon.db")
CLAUDE_MODEL = os.environ.get("HALCYON_CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_EFFORT = os.environ.get("HALCYON_CLAUDE_EFFORT", "medium")
