"""Token usage per model and purpose, computed from the LLM cache (one file per paid call).

Usage: python scripts/cost_report.py
"""

import collections
import json
import sys
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "cache" / "llm"


def main() -> int:
    by_model: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    by_purpose: collections.Counter = collections.Counter()
    for f in CACHE.glob("*/*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        u, model = d["usage"], d["request"]["model"]
        by_model[model].update(
            {"calls": 1, **{k: u.get(k, 0) for k in ("prompt", "output", "thoughts", "total")}}
        )
        by_purpose[f.parent.name] += 1
    print(f"{'model':24} {'calls':>5} {'prompt':>9} {'output':>8} {'thinking':>9} {'total':>9}")
    for m, c in sorted(by_model.items()):
        print(
            f"{m:24} {c['calls']:5} {c['prompt']:9} {c['output']:8} {c['thoughts']:9} "
            f"{c['total']:9}"
        )
    print("total tokens:", sum(c["total"] for c in by_model.values()))
    print("calls by purpose:", dict(by_purpose))
    return 0


if __name__ == "__main__":
    sys.exit(main())
