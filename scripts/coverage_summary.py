#!/usr/bin/env python3
"""Condense a gcovr --json-summary into what the dashboard shows.

Usage: coverage_summary.py <gcovr-summary.json> <out coverage.json>

Writes line and function totals, coverage per source directory (two path
levels, e.g. src-core/effects), and the files with the most unreached lines.
"""

import json
import sys
from collections import defaultdict

TOP_FILES = 40


def pct(covered, total):
    return round(100.0 * covered / total, 2) if total else 0.0


def main():
    raw = json.load(open(sys.argv[1]))
    files = raw.get("files", [])
    dirs = defaultdict(lambda: {"line_total": 0, "line_covered": 0, "function_total": 0, "function_covered": 0, "files": 0})
    rows = []
    for f in files:
        name = f["filename"].replace("\\", "/")
        parts = name.split("/")
        d = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
        agg = dirs[d]
        for k in ("line_total", "line_covered", "function_total", "function_covered"):
            agg[k] += f.get(k, 0)
        agg["files"] += 1
        rows.append({"file": name, "line_total": f.get("line_total", 0), "line_covered": f.get("line_covered", 0),
                     "missed": f.get("line_total", 0) - f.get("line_covered", 0)})

    out = {
        "line_total": raw.get("line_total", 0),
        "line_covered": raw.get("line_covered", 0),
        "line_percent": pct(raw.get("line_covered", 0), raw.get("line_total", 0)),
        "function_total": raw.get("function_total", 0),
        "function_covered": raw.get("function_covered", 0),
        "function_percent": pct(raw.get("function_covered", 0), raw.get("function_total", 0)),
        "files": len(files),
        "dirs": sorted(({"dir": d, **v, "line_percent": pct(v["line_covered"], v["line_total"]),
                         "function_percent": pct(v["function_covered"], v["function_total"])}
                        for d, v in dirs.items()), key=lambda r: -r["line_total"]),
        "least_covered": sorted(rows, key=lambda r: -r["missed"])[:TOP_FILES],
    }
    for r in out["least_covered"]:
        r["line_percent"] = pct(r["line_covered"], r["line_total"])
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    print(f"lines {out['line_percent']}% ({out['line_covered']}/{out['line_total']}), "
          f"functions {out['function_percent']}% over {out['files']} files")


if __name__ == "__main__":
    main()
