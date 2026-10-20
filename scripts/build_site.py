#!/usr/bin/env python3
"""Build the GitHub Pages dashboard from one run's results and the run history.

Usage: build_site.py <results.json> <site dir> <history.json> <run url>

history.json is the published site's copy (missing on the first run). The new
run is appended, the history is trimmed, and both history.json and index.html
are written to the site dir. If <site dir>/coverage/coverage.json exists (the
coverage job's report, downloaded there first) its totals go into the history
and its details onto the page.
"""

import json
import sys
from pathlib import Path

KEEP_RUNS = 180


def main():
    results_path, site, history_path, run_url = sys.argv[1:5]
    site = Path(site)
    site.mkdir(parents=True, exist_ok=True)
    res = json.loads(Path(results_path).read_text())

    try:
        history = json.loads(Path(history_path).read_text())
    except (OSError, ValueError):
        history = []
    coverage = None
    cov_path = site / "coverage" / "coverage.json"
    if cov_path.exists():
        coverage = json.loads(cov_path.read_text())
        (site / "coverage" / "gcovr-summary.json").unlink(missing_ok=True)
    entry = {
        "started": res["started"], "version": res["version"], "sha": res["sha"], "repo": res["repo"],
        "ref": res["ref"], "cpu": res.get("cpu", ""), "run_url": run_url, "totals": res["totals"],
        "scenarios": {s["name"]: [s["status"], s["render_s"]] for s in res["scenarios"]},
    }
    if coverage:
        entry["coverage"] = {"line": coverage["line_percent"], "function": coverage["function_percent"]}
    history = [h for h in history if h.get("run_url") != run_url] + [entry]
    history = history[-KEEP_RUNS:]
    (site / "history.json").write_text(json.dumps(history, separators=(",", ":")) + "\n")
    (site / "latest.json").write_text(json.dumps(res, indent=1) + "\n")

    template = (Path(__file__).parent / "dashboard.html").read_text()
    data = json.dumps({"latest": res, "history": history, "run_url": run_url, "coverage": coverage}, separators=(",", ":"))
    data = data.replace("</", "<\\/")
    (site / "index.html").write_text(template.replace("/*__DATA__*/null", data))
    print(f"wrote {site / 'index.html'} ({len(history)} runs in history)")


if __name__ == "__main__":
    main()
