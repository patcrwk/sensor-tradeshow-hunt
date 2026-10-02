# BDAS Sensor Demo Suite

Big Duck Applied Sciences (BDAS) trade show demo software for enDAQ sensors: a GPS scavenger hunt with a live
leaderboard, course mapping from a crew survey walk, and a Recording Explorer
for any `.IDE` file (starting with a drone flight).

Every number on screen traces back to sensor data. Derived values carry their
source (channel, time window, method), and the UI shows it.

## Quick start (booth laptop, no internet needed)

```bash
make setup      # Python venv + web dependencies (needs internet once)
make dev        # engine on :8000, web on :3000
```

Open http://localhost:3000. Put http://localhost:3000/display on the big monitor
(`make kiosk` opens Chrome in kiosk mode on macOS). At the show, use `make show`
(production build of the web app) instead of `make dev`.

Requirements: Python 3.12 or newer (developed and tested on 3.14), Node 20+.

## Areas

| Area | Route | What it does |
|---|---|---|
| Display | `/display` | Kiosk rotation: leaderboards, course map, crowd stats, heat map, show-floor environment map, recording stories. A new finisher interrupts the rotation. |
| Hunt | `/hunt` | Check-out, returns (drag and drop or watch folder, one-click match confirmation), runs list, leaderboards. `/hunt/runs/<id>`: replay, splits, ghost race, check-in review and override, "how the sensor saw it". |
| Course Setup | `/course` | Survey upload, GPS quality report and mode recommendation, review and adjust (drag stations, rename, required or bonus, order rule, radius, identity methods), leg matrix, background image georeferencing, publish, versions, export and import. |
| Recording Explorer | `/explorer` | Demo Library and upload; Overview, Time Series, Frequency, Shock and Events, Environment, Motion and Location, Story. |
| Admin | `/admin` | Branding, kiosk rotation, active course, watch folder, auto-publish, lead export, event reset, synthetic test data, audit log. |
| Beacon | `/beacon/<station>` | Plays a station's vibration beacon tone (optional identity method). |
| Participant | `/p/<token>`, `/s/<code>` | Phone pages: the personal link from the check-out QR (progress and results), and what a station's QR sign opens (records a check-in). |
| Login | `/login` | Staff login, when `STAFF_PASSWORD` is set (hosted mode). |

## Repository layout

```
engine/          Python package (FastAPI + idelib + endaq)
  config.yaml    every threshold, in one place
  io/            IDE reader, runtime channel discovery, normalized bundle format
  detect/        stillness (with hand-tremor rejection), orientation, taps, beacons, identity
  position/      projection, GPS filter, fusion (EKF), dead reckoning, loop closure, routes
  course/        survey derivation, quality report, leg matrix, image fit, package
  hunt/          matching, validation, route comparison, metrics, scoring, crowd stats
  explorer/      overview, time series, frequency, shock, environment, location, story, profiles/
  api/           FastAPI app, SQLite models, services, SSE bus, watch folder
  synthetic/     synthetic generator with ground truth, CLI
  tests/         parser, synthetic pipeline in every mode, API, explorer
  tune.py        threshold tuning report for real recordings
web/             Next.js (App Router), TypeScript, Tailwind, uPlot, SVG maps
fixtures/        Drone_Flight.IDE (not in git), sample_course_package.zip, synthetic/
docs/            booth runbook, sensor configuration, web mode
```

## How processing works

1. Each `.IDE` is hashed (re-uploading is harmless) and parsed once into a
   normalized bundle: `meta.json` plus one Parquet file per channel, plus
   `gps.parquet` when a location channel exists. Channels are found by
   measurement type (`endaq.ide.measurement`), never by channel number. GPS
   fields beyond latitude and longitude are optional.
2. Detection, course derivation, scoring and Explorer analysis all read the
   bundle. Results are cached as JSON (run results, Explorer analyses) and
   summary numbers in SQLite, so the UI never touches raw data.
3. If processing fails, the run or course is marked "needs review" and staff
   fix it by hand. The booth never blocks.

Positioning is layered per course: GPS, GPS fused with steps and heading
(extended Kalman filter), or dead reckoning anchored to stations. The survey's
GPS quality report recommends the mode and matching radius. Every route is
labeled measured or reconstructed.

## Tests

```bash
make test
```

- Parser tests assert the drone file's reference values (device, channels,
  pressure, temperature, humidity, 0 lux, 1.75 g mean and 15.2 g peak, gyro
  peaks, ~35 m climb) and that it has no location channel.
- The synthetic pipeline runs survey, course derivation, participant runs,
  matching, validation, routes and scoring in GPS, fused and dead-reckoning
  modes (outdoor, indoor, dropout and no-GPS profiles). Current results: 24/24
  correct check-ins with no false stations in every mode tested; survey
  stations within their reported accuracy outdoors; median route deviation
  1.2 to 3.0 m depending on mode.
- API test: a synthetic run uploaded through the API reaches the leaderboard in
  well under 10 seconds.
- Explorer: every analysis renders for the drone file and the Story reports the
  climb, the propeller band and the 15.2 g peak.

Synthetic results are optimistic: the generator's walking model is clean. Real
recordings are required before the show (see below).

## Synthetic data

```bash
make synth
```

writes survey and participant files (`*.synth.zip`, the normalized bundle
format plus `ground_truth.json`) to `fixtures/synthetic/`. They upload through
the UI like `.IDE` files. Admin > Synthetic test data does the same from the
browser; participant serials start at the number you choose, so check those
serials out first.

## Before the show

1. Record one real survey walk and two participant walks with a show sensor,
   ideally at the venue or a similar building.
2. Run `make tune FILE=path/to/survey.IDE ARGS=--survey` and
   `make tune FILE=path/to/walk.IDE ARGS="--course fixtures/<exported course>.zip"`.
   The report prints channel discovery, GPS quality, every rest with its
   tremor measure, identity results, step counts and station coordinates.
3. Re-tune `engine/config.yaml` (stillness, tremor, GPS thresholds, step band)
   on those recordings.

## Notes and decisions

- **GPS channel discovery is untested on real hardware.** The sample file has
  no GPS. Discovery looks for LOCATION/SPEED/DIRECTION subchannels or GPS/GNSS
  channel names and maps names like latitude, longitude, altitude, HDOP,
  satellites and fix. Check `make tune` output on the first real GPS file.
- **Propeller frequency.** The spec lists "near 193 Hz". In this file the
  resultant 40g PSD peaks at about 202 Hz within a 187 to 211 Hz band (mostly
  Z), and the strongest narrow tone overall is 88 Hz on X and Y. The Story
  reports the measured value; the test asserts 185 to 215 Hz.
- **Peak event** is 15.2 g at 5:34 in this file.
- **Data model.** Tables hold identity, status and summary numbers (Event,
  Setting, Upload, Sensor, Participant, Course, SurveyFile, Run, AuditLog,
  Recording). Course geometry (stations, reference route, leg matrix, quality
  report, background image and pins) is one JSON document per course version;
  check-ins, strays, route, leg comparisons and metrics are one JSON result per
  run, with staff overrides stored on the run and logged in the audit table.
- **Projection** is a local equirectangular frame (no pyproj).
- No map tiles, no three.js (not needed; ask before adding).
