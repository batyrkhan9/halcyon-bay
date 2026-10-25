"""Regenerate the simulated hospital and its answer key.

    python3 data/generate/generate.py            writes data/world/ and data/answer_key/
    python3 data/generate/generate.py --out DIR  writes DIR/world/ and DIR/answer_key/ instead

Same seed, same output, byte for byte. Standard library only. Everything is synthetic.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build import Builder  # noqa: E402
import output  # noqa: E402
import scenarios  # noqa: E402

try:
    import planted  # noqa: E402
except ImportError:  # planted cases arrive in the second batch
    planted = None


def build_world():
    b = Builder(random.Random(13))
    pools = scenarios.build_base(b)
    if planted is not None:
        planted.build_planted(b, pools)
    b.finalize_statements(random.Random(13 * 7))
    b.w.assign_ids()
    scenarios.patterns(b, pools)
    return b


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE.parent, help="folder that gets world/ and answer_key/")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    b = build_world()
    counts = output.write_all(b.w, args.out)
    if not args.quiet:
        for k in sorted(counts):
            print(f"{counts[k]:>7}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
