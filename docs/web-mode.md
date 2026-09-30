# Web mode (optional)

The same code can run on a server for remote viewing or a follow-up page.

- **Engine:** any host with Python 3.12+. Run
  `uvicorn engine.api.app:app --host 0.0.0.0 --port 8000` behind a reverse proxy
  with TLS. Set `DATA_DIR` to a persistent volume. Server-sent events need
  proxy buffering off for `/api/stream` (the engine already sends
  `X-Accel-Buffering: no` for nginx).
- **Web:** `cd web && npm run build && npm run start`, or deploy to any Next.js
  host. Set `NEXT_PUBLIC_API_URL` to the engine's public URL at build time
  (by default the browser uses the same hostname on port 8000).
- **Moving data:** export the course package from the booth and import it on
  the server. Participant runs can be re-uploaded (file hashing makes it safe).
- **Access control:** there is none. Staff pages (Hunt, Course Setup, Admin)
  must not be exposed publicly without adding authentication at the proxy.
  Lead data is served only by `/api/admin/leads.csv`; block `/api/admin/*`
  publicly.
- **Privacy:** only display names appear on public pages. Reset the event after
  the show to delete GPS tracks.
- Online map tiles (OpenStreetMap) are not included; ask before adding them.
