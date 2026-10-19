#!/usr/bin/env python3
"""Print a Markdown summary of results.json for $GITHUB_STEP_SUMMARY."""

import json
import sys

ICON = {"pass": "✅", "fail": "❌", "xfail": "⚠️", "skip": "➖"}


def main():
    try:
        res = json.load(open(sys.argv[1]))
    except (OSError, ValueError):
        print("### Render scenarios\n\nNo results: the build or the runner failed before any scenario ran.")
        return
    t = res["totals"]
    print(f"### Render scenarios: xLights {res['version'] or res['ref']}\n")
    print(f"{t['pass']} passed, {t['fail']} failed, {t['xfail']} expected failures, "
          f"{t['skip']} skipped of {t['total']} · {t['render_s']} s rendering\n")
    bad = [s for s in res["scenarios"] if s["status"] != "pass"]
    if bad:
        print("| | Scenario | Detail |\n|---|---|---|")
        for s in bad:
            first = (s["detail"] or s.get("expected_failure") or "").splitlines()
            print(f"| {ICON[s['status']]} | {s['name']} | {first[0] if first else ''} |")
        for s in bad:
            if s["status"] == "fail":
                print(f"\n<details><summary>{s['name']}</summary>\n\n```\n{s['detail']}\n```\n</details>")


if __name__ == "__main__":
    main()
