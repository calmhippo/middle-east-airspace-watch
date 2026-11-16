# CLAUDE.md: Middle East Airspace Watch

## What this is
A public static website that draws **one line per civil flight** crossing the Middle East
(Egypt → Pakistan, Yemen → Caucasus), start to finish, over the last ~90 days. It refreshes
daily. Goal: see which airspace airlines avoid and how routes shift after regional events
(Houthi launches from Yemen, Iran/Israel strikes, airspace closures). The project began as
"flights to/from Doha", so the DOH filter matters.

- Live site: https://calmhippo.github.io/middle-east-airspace-watch/
- Owner: Jean-Alexandre (new to GitHub: explain git/GitHub steps in plain words and do them yourself where possible).
- Demo preview (synthetic data): https://claude.ai/artifact/LesXPA9iqtxpYQQms5V12Q
- A local copy also exists on his Mac: ~/Documents/Claude Projects/middle-east-airspace-watch (older first version).

## Data source
adsb.lol `globe_history` (https://github.com/adsblol/globe_history_2026): ODbL 1.0, free, one
GitHub release per day with the previous day's traces of every aircraft, ~3.6 GB as a split tar
(`.tar.aa` + `.tar.ab`). `PREFERRED_RELEASES.txt` in that repo lists the download URLs per day.
Trace format: https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons
(points `[dt, lat, lon, alt|"ground", gs, track, flags, ...]`; `flags & 2` = new leg; `dbFlags & 1` = military).

**Caveat to keep in the UI:** coverage relies on volunteer receivers and is thin over Iran, Iraq
and the Saudi interior. An empty area can mean "avoided" or "unobserved". Compare periods.

## Layout
```
pipeline/grid.py          analysis box 25–65°E, 10–42°N, 0.1° grid (400×320)
pipeline/process_day.py   stdin tar stream → out/days/<date>.json (density) + out/lines/<date>.s0-3.bin (paths)
pipeline/airports.py      airport list for origin/dest tagging. APPEND-ONLY (indices are stored in data)
pipeline/fetch.sh         download a day's split tar to disk, resuming + size-checking each part
pipeline/update.py        `plan` (missing days as JSON for the Actions matrix) / `manifest` (+ prunes line files >180 days)
pipeline/build_basemap.py Natural Earth 1:50m → data/basemap.json (whole world, simplified)
pipeline/make_demo_data.py synthetic data, manifest demo=true (banner in UI). Never commit its output
site/index.html           the whole viewer: one file, no build step, no external libs
data/                     committed by the workflow: manifest.json, days/*.json, lines/*.bin, basemap.json, events.json
.github/workflows/update.yml  daily 09:17 UTC + manual dispatch (input `days`, default 90)
```

## Pipeline details
- A leg is kept if any airborne point is inside the box. Its **entire** path is stored (worldwide),
  Douglas-Peucker simplified at 0.03°, coords as int16 lat*100/lon*100.
- Gaps > 5 min or > 100 km between reports → gap flag 1 (drawn as pale straight joins; "Mark unheard stretches" greys them).
  |Δlon| > 180 → flag 2 (never drawn). Positions are never estimated by adsb.lol (ADS-B/MLAT/TIS-B only);
  straight stretches come from these joins. Measured Nov 5: in-box distance was 56% reports <1 min apart,
  15% 2–20 min joins, 29% >20 min joins.
- `PIPELINE_VERSION` (grid.py) is written into each day JSON as "v"; `plan` reprocesses days with an older v.
  Bump it whenever process_day.py output changes meaning.
- tar is read with `ignore_zeros=True` (the 2026-09-01 release has a damaged block; that day has ~5.9k legs).
- Origin/dest = airport within 40 km of the leg's first/last point if below 10,000 ft.
- Each day is shuffled into 4 shards so the viewer can load a random sample for long ranges.
- Density grid: each leg adds +1 to every 0.1° cell it crosses (≥1,000 ft, observed segments only), once per leg.
- Binary shard layout is documented in the `process_day.py` docstring and parsed by `parseShard()` in the viewer. Change both together.
- Real numbers (Oct 28 2026): ~79k traces/day, ~3,700 aircraft / ~8,100 legs in box, ~128k path points,
  ~650 KB of line files/day. Processing ≈ 2–3 min/day on a GitHub runner.

## Workflow
`plan` → `process` (matrix, one job per day, max-parallel 5)
(`fetch.sh` to disk, then `cat | process_day.py`; never stream curl straight in: a dropped
connection plus ignore_zeros silently saved partial days on Nov 8) → `publish` (reset to the newest origin/main, copy
artifacts into data/, `update.py manifest`, commit, push; up to 4 attempts, so a push by someone else mid-run no longer
fails with a manifest.json rebase conflict as on Nov 16; then deploy to Pages).
A day counts as done when both `data/days/<d>.json` and `data/lines/<d>.s0.bin` exist.
GitHub Pages source = "GitHub Actions" (already set).

## Viewer (site/index.html)
- Three stacked canvases: `#base` (2D: water, land, borders, heatmap), `#gl` (WebGL2 lines), `#top`
  (labels, airports, events, analysis box).
- Lines (float path, EXT_color_buffer_float), all in device pixels:
  1. each segment is an instanced quad (point i -> i+1, per-segment flag buffer: 0 observed, 1 gap, 2 skip)
     drawn as a 1 px tent into RGBA16F: R = observed weight, G = gap weight, BA = weighted offset to the
     nearest point on the segment (sub-pixel line position). Pixels belong to the segment with t in [0,1).
  2. jump flooding (init + steps 8,4,2,1,1 at dpr 2) picks per pixel the seed maximising halfWidth - distance;
     half-width = w·(0.45 + 2·level) CSS px (max R_MAX=4), level = log(flights/week ÷ WEEK_LO) / log(WEEK_HI ÷ WEEK_LO)
     clamped 0–1 (WEEK_LO=5, WEEK_HI=500); paths under 5/week also fade to 25% opacity (user: 1/week was noise).
     Density = line weight within ~1 CSS px.
  3. shade: smooth coverage, colour mid blue→deep navy with density. No analysis-box outline or dimming (user asked).
  Distance fade (user's design, Nov 8): full strength within FADE_KM[0]=1800 km of the airport of interest
  (Doha, or the airport picked in "Flights"), then width (to 35%) and opacity taper to 0 at FADE_KM[1]=3200 km.
  Computed per pixel (unproject + haversine); segments wholly beyond FADE_KM[1] are culled in the vertex shader.
  Unheard joins (gap flag 1) are drawn by default so routes look continuous (e.g. Arabian Sea crossings,
  typically 1,300-2,300 km joins), but count JOIN_WEIGHT=0.35 towards width and are paler; "Mark unheard
  stretches" (S.gaps) turns them grey. The paler style ramps in over JOIN_RAMP_KM=250 km from each end of a join
  (user found the abrupt dark->light switch at coverage edges odd). Checked Nov 1-7: N Saudi 26-31N 39-46E is 1%
  observed / 99% joins (no receivers) vs 89% observed in the Gulf: the faintness there is coverage, not a data error. Measured Nov 1-3 within 3200 km: joins are 57% of drawn distance,
  69% of it from joins >1000 km, so they must stay visually secondary or they swamp avoided airspace.
  Coverage hatching (Nov 9): coverage() bins the loaded lines into a 0.5° grid (observed vs join km); cells with
  observed share <~30% and real traffic are hatched on #base (lines mode), faded at the box edges. The grid is also
  a texture in segP (JOIN_WEIGHT_LOWCOV). Tried counting joins in full there: coverage is ~0% over Saudi, Iraq, Iran,
  Egypt south of Cairo, Yemen, Caucasus, Arabian Sea (only Levant, W Turkey, Gulf coast covered), so full-weight
  straight joins swamped the map (e.g. Turkey->UAE across Iran). Kept at 0.35; hatching + legend explain faintness.
  Saudi joins median 1,100 km, Iraq 1,460 km, so a join-length cutoff doesn't help either.
  Nov 9 (user: flights still seemed to disappear without data): in low-coverage areas joins now count
  JOIN_WEIGHT_LOWCOV=0.5 and get JOIN_PALE_LOWCOV=0.5 of the usual paling (0.6/no paling was a mess of straight lines:
  joins never overlap, so they don't stack into corridors like heard paths do).
  "Line width" slider scales w. Without float targets: premultiplied additive LINE_STRIPs (no width encoding).
  Never go back to plain alpha blending at tiny alpha: the 8-bit canvas alpha rounds to 0 and the layer vanishes.
  The old CSS-pixel dilation looked beaded/pixelated (user, Nov 8); don't return to it.
- Equirectangular projection with cos(28°) x-scaling; zoom 0.2–16 (zoom out to world).
- One view only: flight paths (Nov 16: user removed Heatmap and Compare periods as redundant; focus is ▶ Play weekly
  showing corridors change over time). days/*.json density grids are still produced by the pipeline but unused by the viewer.
- Always one week on screen (S.frames = 7-day windows ending on the last day; S.fi = index). The daily-totals chart is
  the player (Nov 16, user agreed): ▶ Play / ❚❚ Pause beside it; tap or drag the chart to pick a week (pauses play,
  map reloads 200 ms after the finger stops); outlined playhead on the chart. #frame on the map always shows the week,
  "week N of M · flights" (all flights: from manifest totals; airport filter: loaded lines, ≈ scaled while playing),
  the week's Gulf–Europe corridor split, and that week's events with source links. Only other control: the airport
  filter, cut to 13 hubs (HUBS in the viewer, looked up by code), now in the header.
- Design (Nov 16 redesign, user: "eyesore", wants minimal, beautiful, readable from visuals alone): "quiet atlas".
  Tokens in :root (paper/ink neutrals, --more blue, --less red; single light theme, system UI font, no deps). Header =
  name + period, then airport select, Changes|Traffic segmented control, About (a <dialog> holding all explanation:
  line meaning, colours, events, corridors, coverage caveat, data). Map: sea #fbfbf9, land #ecebe6, faint borders,
  small letter-spaced country names, only HUBS labelled. One floating week card (#frame: date, week/flights, colour key,
  Gulf<->Europe mini stacked bar, events with the date linking to the source). Dock: text tabs, round ink play button,
  bars ink for the selected week. No hatching any more (removed for clutter; caveat lives in About). On screens <700 px
  base() fits the box below a 150 px band reserved for the card.
- Change map (Nov 16, user: effects too hard to see; wanted deltas, baseline traffic still visible, colour for routes
  added/removed). Changes mode (S.deltaOn, default): lines in quiet greys (GREY_LO/HI via u_lo/u_hi); the comp shader
  samples an RG8 texture (S.deltaTex, R = more, G = fewer, 0..1 per 0.1° cell, faded over the outer 1.5° of the box) and
  tints the lines blue (MORE) or red (LESS); unchanged lines recede (alpha 0.7). Routes largely gone get a faint blurred
  red trace on #base (ghostCv). The first try (a multiply-blended colour wash over everything) was rejected as an eyesore.
  lowCoverage() now clamps to the box edge outside it (outside used to count as covered, which showed the box as a rectangle). Baseline = first BASE_WEEKS=4 week frames (fixed, so a new corridor stays blue;
  rolling would flash then fade), loaded once as a ~120k-flight sample. flowField(): each flight once per cell, unheard
  joins included (so receiver changes don't read as route changes), per day, 1-2-1 blur x2. Coloured only if
  |d|/max >= ~0.2-0.7 and |d| >= ~0.6-4 flights/day (smoothstep ramps); fades with FADE_KM and over 1.5° at the box edge.
  ~270 ms per field. Hover shows this week vs baseline flights/day. Diverging pair = dataviz blue<->red.
- Events: ink diamonds with a white ring and an ink date pill, because red means "fewer" (they were red for a few hours
  on Nov 16 at the user's request; the switch was explained to the user).
- Corridor colours (chart + card): west of Iraq grey #b3b0a8, Iraq orange #e07a2c, Iran teal #1f9a86, so blue/red keep
  one meaning site-wide.
- Chart tabs: "Flights per day" / "Gulf–Europe routes" (100% stacked daily bars from manifest days[].corr = [west, iraq,
  iran]). Both share the playhead.
- Gulf–Europe corridors: pipeline/corridors.py, called by `update.py manifest` (~2 s for 97 days; keeps the old value
  once line files are pruned). Leg = one end in Gulf box (22–30.5N, 46–57.5E), other in Europe (36–72N, 15W–30E);
  corridor = where it first crosses 34N: west <40.5E, Iraq 40.5–46E, Iran ≥46E. Joins count (crossings over Iraq/Iran
  are often estimated). Result Nov 16: Iraq 3–13% Aug–early Oct, jumps to ~35–43% from ~Oct 17-19 (Kuwait reopened
  to overflights Oct 15); Iran ~0–4%; ~450–500 Gulf–Europe legs/day.
  Removed Nov 16 (user agreed): range presets (1 day / 7 / 30 / All), Line width slider, "Mark unheard stretches"
  (shader u_gaps is now always 0; the code path is still there).
- Touch: one finger pans, two fingers pinch-zoom. (The on-map legend panel was removed; About replaces it.)
- Play: from the week after the one shown (from week 1 if on the last), FRAME_MS=1500 per week, PLAY_MAX_LINES=30k
  sample, preloads the next week. Pause/end = that week, reloaded in full.
- `MAX_LINES = 150000`: above it, fewer shards per day are loaded (random sample, stated in the UI).
- `manifest.bundle` (optional) lets a host that can't serve .bin (the claude.ai artifact preview) use one base64 JSON.
- Light theme (user, Nov 8): white sea, beige land #e8e4d8, darker country outlines, page surface #f7f6f2.
  Line colour = the same level (redundant with width): LINE_LO mid blue -> LINE_HI deep navy;
  the legend samples use the same formulas. Unheard joins at 30% opacity (more made a grey fog over Iran/Saudi).

## Testing
- Pipeline: build a tiny tar of `traces/xx/trace_full_<hex>.json` (gzip JSON), `split` it, pipe through `process_day.py`.
- Viewer: `python3 pipeline/make_demo_data.py --days 14` into a scratch copy (NOT the repo's data/),
  serve with `python3 -m http.server`, screenshot with Playwright/Chrome (`--use-angle=swiftshader --enable-unsafe-swiftshader` for WebGL2).

## Status (2026-11-08)
- Backfill done (Aug 10 – Nov 6). Run 42457890600 + a re-run for 2026-09-01.
- Fixed: lines invisible at high counts (8-bit alpha), damaged-tar early exit.
- Look agreed with the user: firm lines, thickness = density, less blown-out, gaps hidden by default.
  Nov 8: dashed box + outside dimming removed; renderer rewritten for smooth sub-pixel lines.
  Dark Arabian Sea = no receivers over open ocean (Show gaps reveals the crossings). A free source won't fix
  that; only satellite ADS-B (commercial) would.
- All 89 days (Aug 10 – Nov 6) are pipeline v2 with 4 shards (verified after run 42470754478).
  Legs/day median ~8,650; low but complete days: Sep 1 (5,927, damaged tar) and Aug 13 (6,931, full 74k traces).
  The 09:17 UTC schedule did not fire on Nov 8; trigger update.yml manually if a day is missing.
- data/events.json: 7 events Aug 30 – Oct 25 (researched Nov 16 from search results; the session could not open
  news sites directly, so each date was cross-checked across search results). Fields: date, lat, lon, type, title, url.

## Next steps (agreed or proposed)
1. Done Nov 8: backfill verified (all days v2, 4 shards), DOH filter works, look iterated with the user
   (light map, smooth lines, Doha distance fade, per-week scale, gradual unheard joins). Ask for feedback on the live site.
2. Offered, not decided: finer path precision (DP 0.01°, int16 lat/lon*180; ~+70% data, reprocess all days ~3-4 h);
   great-circle joins; tuning WEEK_LO/WEEK_HI, FADE_KM, JOIN_WEIGHT.
3. Done Nov 16: first 7 events. Keep adding as the period moves (sourced facts only; stay neutral).
4. Done Nov 16: Gulf–Europe routes chart, hub-only airport filter, red events. Not yet checked: whether a receiver
   change over Kuwait/Iraq contributes to the mid-Oct Iraq jump. Ideas: colour by recent vs earlier days, hover a line → callsign
   (needs callsign in shards), filter by airline, altitude band filter.
5. Check the daily schedule actually fires (it didn't on Nov 8); otherwise run update.yml by hand.

## Conventions
- Commit as the user; end commit messages with the Co-Authored-By line Claude Code adds.
- Don't commit synthetic demo data or the raw tar downloads (.gitignore covers `downloads/`, `*.tar.*`).
- Keep the site dependency-free (single HTML file) unless there's a strong reason.
