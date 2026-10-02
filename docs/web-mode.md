# Web mode (optional)

The same code can run on a server for remote viewing or a follow-up page. The
booth laptop stays the primary system; read the limits below before relying on
a hosted copy.

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
git push heroku main
```

`ENGINE_INTERNAL_URL` and `NEXT_PUBLIC_SAME_ORIGIN_API` must be set **before**
the build: they switch the web app into hosted mode at build time.

### Limits on Heroku

- **Data does not persist.** Heroku's filesystem is wiped on every deploy and
  dyno restart (at least daily). Courses, runs, uploads and settings live in
  `data/` (SQLite and files) and will disappear. Re-import the course package
  and re-upload recordings after a restart, or move storage to Heroku Postgres
  and S3 (not built yet).
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

## Security (read before sharing a URL)

- **There is no login.** Anyone with the URL can use Hunt, Course Setup and
  Admin, including **Reset event** and the **leads CSV** (participant emails).
  Do not share a hosted URL until access control is added (for example a staff
  password on everything except `/display` and the home page).
- Only display names appear on public pages. Reset the event after the show to
  delete GPS tracks.
- Online map tiles (OpenStreetMap) are not included; ask before adding them.
