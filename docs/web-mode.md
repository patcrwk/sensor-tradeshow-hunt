# Web mode (Heroku)

The hunt can run entirely on Heroku: staff use it from the booth over the show
Wi-Fi, and participants' phones reach it for QR check-ins and their results.
The same code still runs offline on a booth laptop (no `DATABASE_URL`, no
`STAFF_PASSWORD`).

## Heroku

The repo is set up for a single Heroku app running both services in one dyno:

- `package.json` (root): the Node buildpack builds `web/` as a standalone Next
  server, then `bin/heroku-slim` removes build-only dependencies.
- `requirements.txt` and `.python-version` (root): the Python buildpack installs
  the engine.
- `Procfile` runs `bin/heroku-start`: the engine listens on 127.0.0.1:8000
  inside the dyno, and Next serves `$PORT` and forwards `/api/*` to it, so the
  browser only talks to one origin.

One-time setup (both buildpacks, Node first):

```bash
heroku buildpacks:clear
heroku buildpacks:add heroku/nodejs
heroku buildpacks:add heroku/python
heroku config:set ENGINE_INTERNAL_URL=http://127.0.0.1:8000 NEXT_PUBLIC_SAME_ORIGIN_API=1 MALLOC_ARENA_MAX=2
heroku addons:create heroku-postgresql:essential-0
heroku config:set STAFF_PASSWORD='choose-a-long-password'
git push heroku main
```

`ENGINE_INTERNAL_URL` and `NEXT_PUBLIC_SAME_ORIGIN_API` must be set **before**
the build: they switch the web app into hosted mode at build time.

### Data

With the Postgres add-on (`DATABASE_URL`), everything persists across deploys
and restarts: courses, participants, runs, QR scans, settings, the original
uploaded recordings, run results, Explorer analyses and background images.
Parsed recordings are cached on the dyno disk and rebuilt automatically from
the stored original after a restart (the first view of each recording after a
restart takes a few seconds).

Storage size: each participant recording is a few MB. Essential-0 holds 1 GB,
roughly 150 to 250 participants plus a course; use Essential-1 (10 GB) for a
busy show or if you keep large Explorer files such as the 37 MB drone flight.
Admin > Reset event deletes participant recordings and frees the space.

### Staff login

`STAFF_PASSWORD` locks Hunt, Course Setup, Admin and every staff API call
(including the leads CSV and event reset). Staff log in once per browser
("Staff login" in the top bar); the login lasts two weeks. Public without a
login: the home page, `/display`, Recording Explorer (view only), participant
pages (`/p/...`) and station scan pages (`/s/...`). The start script warns in
`heroku logs` if the password or database is missing.

### Limits on Heroku

- **Memory.** Parsing and analyzing a large recording (the 37 MB drone file)
  uses about 1.1 GB in the engine. Use a Standard-2X dyno at minimum, or
  Performance-M for large Explorer files. Hunt participant files are small.
  `MALLOC_ARENA_MAX=2` reduces memory fragmentation.
- **The drone demo is not in git** (`fixtures/*.IDE` is ignored), so the Demo
  Library starts empty. Upload it through Recording Explorer.
- **30 second request limit.** Heroku's router ends requests after 30 s. Uploads
  of normal recordings finish well within that.

## Other hosts

- **Engine:** any host with Python 3.12+. Run
  `uvicorn engine.api.app:app --host 0.0.0.0 --port 8000` behind a reverse proxy
  with TLS. Set `DATA_DIR` to a persistent volume. Server-sent events need
  proxy buffering off for `/api/stream` (the engine already sends
  `X-Accel-Buffering: no` for nginx).
- **Web:** `cd web && npm run build && npm run start`. Either set
  `NEXT_PUBLIC_API_URL` to the engine's public URL at build time, or use the
  same-origin setup above (`ENGINE_INTERNAL_URL` + `NEXT_PUBLIC_SAME_ORIGIN_API=1`).

## Security

- Set `STAFF_PASSWORD` before sharing the URL (see Staff login above). Without
  it, anyone with the URL can reach Admin, the leads CSV and event reset.
- Participant pages are reached only through the personal link in the
  check-out QR code. Station QR codes are random per course and are not shown
  on any public page; a scan only counts if it lines up with a real 10 second
  sensor rest.
- Only display names appear on public pages. Reset the event after the show to
  delete GPS tracks and QR scans.
- Online map tiles (OpenStreetMap) are not included; ask before adding them.
