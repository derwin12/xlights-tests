#!/usr/bin/env python3
"""Render every scenario twice and compare against the committed baselines.

Each scenario is rendered in its own `xLights --headless` process so a crash
fails only that scenario. A scenario passes when it renders, its two renders
are identical (determinism), and the render matches baselines/<name>.fseq.

Usage:
  run_scenarios.py --xlights <binary> --show <show dir> --baselines <dir> --out <dir>
                   [--wrap "xvfb-run -a"] [-k <substring>]

Writes <out>/results.json, <out>/junit.xml and <out>/fseq/<name>.fseq (the
first render, which is what a rebaseline commits).
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from xml.sax.saxutils import quoteattr, escape

RENDER_TIMEOUT = 600
UPDATED_RE = re.compile(r"Updated in\s+([0-9.]+) seconds")


def run(cmd, timeout):
    start = time.monotonic()
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
                           text=True, errors="replace")
        return p.returncode, p.stdout, time.monotonic() - start
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return None, out + f"\n[timed out after {timeout}s]", time.monotonic() - start


def render(args, wrap, xsq, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = wrap + [args.xlights, "--headless", "-s", str(args.show), "--outputdir", str(outdir), str(xsq)]
    code, out, wall = run(cmd, RENDER_TIMEOUT)
    fseq = outdir / (xsq.stem + ".fseq")
    m = UPDATED_RE.search(out)
    secs = float(m.group(1)) if m else None
    return code, out, wall, secs, fseq if fseq.exists() else None


def compare(args, wrap, a, b, with_models):
    cmd = wrap + [args.xlights, "--fseqcmp"]
    if with_models:
        cmd += ["-s", str(args.show)]
    cmd += [str(a), str(b)]
    code, out, _ = run(cmd, RENDER_TIMEOUT)
    lines = [l for l in out.splitlines() if "] [" not in l]  # drop spdlog lines
    if code == 0 and any(l.startswith("IDENTICAL") for l in lines):
        return True, ""
    start = next((i for i, l in enumerate(lines) if l.startswith(("DIFFER", "--fseqcmp"))), 0)
    return False, "\n".join(lines[start:start + 25]).strip() or f"fseqcmp exit {code}"


def tail(text, n=30):
    return "\n".join(text.strip().splitlines()[-n:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlights", required=True)
    ap.add_argument("--show", required=True, type=Path)
    ap.add_argument("--baselines", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--wrap", default="")
    ap.add_argument("-k", default="", help="only scenarios whose name contains this")
    args = ap.parse_args()
    args.show = args.show.resolve()
    args.out = args.out.resolve()
    args.baselines = args.baselines.resolve()
    wrap = shlex.split(args.wrap)

    spec = json.loads((args.show / "scenarios.json").read_text())
    names = [n for n in spec["scenarios"] if args.k in n]
    run1, run2, keep = args.out / "run1", args.out / "run2", args.out / "fseq"
    for d in (run1, run2, keep):
        shutil.rmtree(d, ignore_errors=True)
    keep.mkdir(parents=True)

    results = []
    started = time.time()
    for name in names:
        xsq = args.show / f"{name}.xsq"
        expected = spec["scenarios"][name].get("expected_failure")
        r = {"name": name, "expected_failure": expected, "render_s": None, "wall_s": None,
             "deterministic": None, "baseline": None, "detail": ""}
        problems = []

        code, out, wall, secs, fseq = render(args, wrap, xsq, run1)
        r["render_s"], r["wall_s"] = secs, round(wall, 3)
        if code != 0 or fseq is None:
            problems.append(f"render failed (exit {code})\n{tail(out)}")
        else:
            shutil.copy2(fseq, keep / fseq.name)
            code2, out2, _, _, fseq2 = render(args, wrap, xsq, run2)
            if code2 != 0 or fseq2 is None:
                problems.append(f"second render failed (exit {code2})\n{tail(out2)}")
            else:
                same, diff = compare(args, wrap, fseq, fseq2, False)
                r["deterministic"] = same
                if not same:
                    problems.append("two renders differ:\n" + diff)
            base = args.baselines / f"{name}.fseq"
            if base.exists():
                same, diff = compare(args, wrap, base, fseq, True)
                r["baseline"] = "match" if same else "differ"
                if not same:
                    problems.append("differs from baseline:\n" + diff)
            else:
                r["baseline"] = "missing"

        if problems:
            r["status"] = "xfail" if expected else "fail"
        elif r["baseline"] == "missing":
            r["status"] = "skip"
            r["detail"] = "no baseline yet"
        else:
            r["status"] = "pass"
        if problems:
            r["detail"] = "\n\n".join(problems)
        results.append(r)
        t = f"{secs:.3f}s" if secs is not None else "-"
        print(f"{r['status'].upper():5} {name:32} {t:>9}  {r['detail'].splitlines()[0] if r['detail'] else ''}", flush=True)

    totals = {s: sum(1 for r in results if r["status"] == s) for s in ("pass", "fail", "xfail", "skip")}
    totals["total"] = len(results)
    totals["render_s"] = round(sum(r["render_s"] or 0 for r in results), 3)
    doc = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "duration_s": round(time.time() - started, 1),
        "version": os.environ.get("XL_VERSION", ""),
        "sha": os.environ.get("XL_SHA", ""),
        "repo": os.environ.get("XL_REPO", ""),
        "ref": os.environ.get("XL_REF", ""),
        "channels": spec.get("channels"),
        "totals": totals,
        "scenarios": results,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(doc, indent=1) + "\n")

    junit = [f'<testsuite name="render" tests="{len(results)}" failures="{totals["fail"]}" '
             f'skipped="{totals["skip"] + totals["xfail"]}" time="{totals["render_s"]}">']
    for r in results:
        junit.append(f'  <testcase classname="render" name={quoteattr(r["name"])} time="{r["render_s"] or 0}">')
        if r["status"] == "fail":
            junit.append(f'    <failure message="render mismatch">{escape(r["detail"])}</failure>')
        elif r["status"] in ("skip", "xfail"):
            junit.append(f'    <skipped message={quoteattr(r["expected_failure"] or r["detail"])} />')
        junit.append("  </testcase>")
    junit.append("</testsuite>")
    (args.out / "junit.xml").write_text("\n".join(junit) + "\n")

    print(f"\n{totals['pass']} passed, {totals['fail']} failed, {totals['xfail']} expected failures, "
          f"{totals['skip']} skipped; {totals['render_s']}s rendering")
    sys.exit(1 if totals["fail"] else 0)


if __name__ == "__main__":
    main()
