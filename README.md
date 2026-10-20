# xlights-tests

Nightly render regression tests for [xLights](https://github.com/xLightsSequencer/xLights), with a dashboard on GitHub Pages:
**https://derwin12.github.io/xlights-tests/**

Each night the workflow builds xLights master on Linux (the same build container as xLights' own Ubuntu CI), renders every sequence in `show/` with `xLights --headless`, and checks each scenario three ways:

1. **It renders.** The headless process exits 0 and writes an `.fseq` file. Each scenario runs in its own process, so a crash fails only that scenario.
2. **It repeats.** A second render is byte-identical to the first, compared with `xLights --fseqcmp`.
3. **It matches its baseline.** The render matches `baselines/<scenario>.fseq`. On a mismatch, the failure lists which models changed and by how much.

## Coverage

The nightly run also builds xLights a second time with gcov (`--coverage`) and runs the same scenarios on that build. `gcovr` then measures which lines and functions of `src-core/` they reached. `src-ui-wx/` isn't measured: headless rendering never opens a window, so it would read about 0% and only bury the useful numbers. Only the xLights objects are instrumented; wxWidgets and the other prerequisites are built first without it.

The dashboard shows:

- the line and function totals, and the trend over time
- coverage per directory
- the 40 files with the most unreached lines, which are good targets for new scenarios

The full line-by-line report is at [`coverage/index.html`](https://derwin12.github.io/xlights-tests/coverage/index.html). To measure coverage on a manual run, tick **coverage** when you start it.

## The show

`show/` is generated, not hand-made:

```bash
python3 scripts/gen_show.py <path-to-xlights-source> show
```

The generated show contains:

- 15 models (matrix, tree, arches, single line, star, wreath, icicles, window frame, sphere, cube, custom, candy canes, circle, spinner and poly line), all on one DDP controller.
- Two groups: `All Models`, and `Mixed Group`, which mixes submodels with whole models.
- DMX fixtures, kept out of `All Models` so the generic scenarios don't change: two advanced and two basic moving heads (RGBW and colour wheel, grouped as `Moving Heads`), an RGB floodlight, a general DMX fixture and a two-servo model.
- 22 output variants on small lines and matrices, also kept out of `All Models`:
  - GRB/BRG/RGBWW node order, and every RGBW handling mode
  - single-colour white, red and intensity strings
  - model brightness, gamma and per-colour dimming curves
  - controller-relative, chained (`>`) and offset (`@`) start channels
  - individual start channels
  - a rotated matrix
- 16 more model types and layouts, also kept out of `All Models` and grouped as `New Types`:
  - flat, ribbon and spiral trees
  - a vertical, two-strand, alternating-node matrix and a no-zig-zag matrix
  - a two-layer, two-string 3D custom model
  - a multi-layer star, an inside-out circle, a counter-clockwise window frame, a zig-zag spinner, alternating icicles and reversed candy canes with sticks
  - multi-point, channel block, image and label models
- `SM_Matrix`, a matrix carrying every submodel form: sub-buffer, *Keep XY* and *Stacked Strands* range styles, reversed ranges and a node list with gaps.
- A DMX skull and a 3D servo model.
- On the matrix, two submodels and a node-range singing face. On the tree, a submodel. On the star, a node-range state definition.
- Media written by the generator:
  - `media/beat.wav`, a synthetic 60 s beat with a frequency sweep
  - `media/gradient.png`
  - `media/pattern.fs`, an ISF shader with float, bool, choice, point, colour and event inputs
  - `media/pattern.gled` and `media/pattern.csv`, Glediator raw and CSV frames

  Also `media/testsrc.mp4`, a 3 s ffmpeg `testsrc2` clip, which is committed because the CI container has no ffmpeg.
- An `Effect_<Name>` sequence for each effect, except the ones that need input (listed below). Each one steps through the effect's default settings, every value of each static choice, and every checkbox flipped, one second each, read from xLights' `resources/effectmetadata/*.json`. It then renders the defaults on the group, once with the default buffer and once with *Per Preview*.
- `Effect_SingleStrandFX`: Single Strand's FX mode, which runs the WLED effect library in `FX.cpp`. It covers all its modes and all 71 palettes, read from `FX.h`. The two "Phased" modes are split into `Effect_SingleStrandFX_Phased`, an expected failure: their phase is a function-level `static` shared by every model and render thread, so the output depends on thread timing.
- Hand-written scenarios for the effects that need input:
  - **Faces:** each phoneme in turn, then driven by a lyric track.
  - **State:** each state in turn, then driven by a timing track.
  - **Pictures:** the generated image.
  - **VU Meter** and **Music:** the generated audio.
  - **Duplicate:** copies the matrix's layer onto every other model.
  - **Video:** the test clip, through every option.
  - **Moving Head:** positions, offsets, groupings, all 10 patterns, value curves, a path, colour, wheel, dimmer and shutter. It runs on the group and on a single fixture.
  - **DMX** and **Servo:** levels, ramps, inversion and 8/16-bit output. `Effect_DMXSkullServo3D` does the same for the skull and the 3D servo model.
  - **Piano** and **Guitar:** a timing track of note names, sharps/flats, MIDI numbers, chords and (for Guitar) string/fret positions, through each type and option.
  - **Sketch:** line, quadratic and cubic paths, a closed path and several paths at once, with motion, thickness, a value-curved draw percentage and a background image.
  - **Glediator:** raw frames on the matrix and CSV frames on every model, through each duration treatment.
  - **Shader:** the test shader through each of its inputs, plus speed, offset, zoom and lead-in.
- `Feature_*` sequences covering:
  - in/out transitions
  - all 24 layer blend methods
  - group buffer styles
  - buffer transforms (rotation, blur, sub-buffer, rotozoom)
  - colour adjustments
  - value curve shapes
  - effects fired by timing marks (Ripple, Shockwave, Fireworks, Shape)
  - submodels
  - palette colour curves, layer morph, and sparkles, plain and music-driven
  - every output variant (`Feature_ModelOutput`)
  - the extra model types through a spread of effects and buffer styles (`Feature_ModelTypes`)
  - every submodel form (`Feature_SubModelTypes`)
- `Seq_*` sequences that vary the sequence itself: 25 ms and 100 ms frame timing, and model blending off.

The audio and image are synthetic, so the show can be public.

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
