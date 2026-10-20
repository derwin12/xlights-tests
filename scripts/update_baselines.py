#!/usr/bin/env python3
"""Copy a run's renders into its CPU vendor's baseline set.

Usage: update_baselines.py <results.json> <renders dir> <baselines dir> (--all | --missing)

--all      rebaseline: every scenario that rendered the same twice replaces
           baselines/<set>/<name>.fseq. Where that changes a baseline, the
           other sets' copies are deleted, since they came from the old
           render; the next run on that vendor fills them back in.
--missing  only add baselines this set doesn't have yet.

Prints what it changed.
"""

import json
import shutil
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 5 or sys.argv[4] not in ("--all", "--missing"):
        sys.exit(__doc__)
    res = json.loads(Path(sys.argv[1]).read_text())
    renders, root, mode = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
    bset = res.get("baseline_set")
    if not bset or bset == "other":
        sys.exit(f"unknown CPU vendor ({res.get('cpu')!r}); not updating baselines")
    dest = root / bset
    dest.mkdir(parents=True, exist_ok=True)
    others = [d for d in root.iterdir() if d.is_dir() and d.name != bset]

    for s in res["scenarios"]:
        name, src = s["name"], renders / f"{s['name']}.fseq"
        if not src.exists() or s.get("deterministic") is False and not s.get("expected_failure"):
            continue
        if mode == "--missing" and s.get("baseline") != "missing":
            continue
        if mode == "--all" and s.get("baseline") == "match":
            continue
        shutil.copy2(src, dest / src.name)
        print(f"{bset}: {'added' if s.get('baseline') == 'missing' else 'updated'} {name}")
        if mode == "--all" and s.get("baseline") == "differ":
            for d in others:
                stale = d / src.name
                if stale.exists():
                    stale.unlink()
                    print(f"{d.name}: removed stale {name}")


if __name__ == "__main__":
    main()
