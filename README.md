# xlights-tests

Nightly render regression tests for [xLights](https://github.com/xLightsSequencer/xLights), with a dashboard on GitHub Pages:
**https://derwin12.github.io/xlights-tests/**

Each night the workflow builds xLights master on Linux (the same build container as xLights' own Ubuntu CI), renders every sequence in `show/` with `xLights --headless`, and checks each scenario three ways:

1. **It renders.** The headless process exits 0 and writes an `.fseq` file. Each scenario runs in its own process, so a crash fails only that scenario.
2. **It repeats.** A second render is byte-identical to the first, compared with `xLights --fseqcmp`.
3. **It matches its baseline.** The render matches `baselines/<scenario>.fseq`. On a mismatch, the failure lists which models changed and by how much.

## The show

`show/` is generated, not hand-made:

```bash
python3 scripts/gen_show.py <path-to-xlights-source> show
```

The generated show contains:

- 11 models (matrix, tree, arches, single line, star, wreath, icicles, window frame, sphere, cube and custom) plus an `All Models` group, all on one DDP controller.
- An `Effect_<Name>` animation sequence for each effect that needs no external media, timing track or DMX fixture. Each one steps through the effect's default settings, every value of each static choice, and every checkbox flipped, one second each, read from xLights' `resources/effectmetadata/*.json`. It then renders the defaults on the group, once with the default buffer and once with *Per Preview*.
- `Feature_*` sequences covering in/out transitions, all 24 layer blend methods, group buffer styles, buffer transforms (rotation, blur, sub-buffer, rotozoom), colour adjustments and value curve shapes.

There's no audio, so the show can be public.

## Running it locally

```bash
python3 scripts/run_scenarios.py --xlights <path-to>/xLights --show show --baselines baselines --out out
python3 scripts/run_scenarios.py ... -k Effect_Bars   # one scenario
```

Results go to `out/results.json` and `out/junit.xml`, and the first render of each scenario to `out/fseq/`.

On Linux, run it under a virtual display (`xvfb-run -a`, or start `Xvfb` and set `DISPLAY`), because xLights initialises GTK even in headless mode.

## Updating baselines

Baselines are rendered on the CI runner. Don't commit renders from another platform: floating-point results differ between compilers and CPUs.

1. Open **Actions → Render scenarios → Run workflow** and tick **rebaseline**.
2. The run commits its renders to `baselines/`.

Do this after an xLights change that is meant to alter rendering, after changing `gen_show.py`, or after adding a scenario.

## Expected failures

A scenario listed in `EXPECTED` in `scripts/gen_show.py` is reported as an *expected failure* instead of a failure when it doesn't match. Use this for effects that aren't deterministic by design, such as Liquid's physics simulation.

## Running it by hand

**Run workflow** takes these inputs:

| Input | Effect |
|---|---|
| `xlights_repo` / `xlights_ref` | Test a fork or branch instead of master, for example a PR branch. |
| `filter` | Run only the scenarios whose name contains this text. |
| `rebaseline` | Commit this run's renders as the new baselines. |
| `publish` | Add this run to the dashboard. The nightly run always publishes. |
