"""Overview tab: device, session and channel inventory."""
from __future__ import annotations

from ..io.bundle import Bundle


def overview(b: Bundle) -> dict:
    m = b.meta
    dev = m.get("device", {})
    notes = []
    if dev.get("calibration_expired"):
        notes.append(f"Calibration expired {dev.get('calibration_expiry')}. Values are shown as recorded, "
                     "not as calibrated measurements.")
    if m.get("synthetic"):
        notes.append("Synthetic recording generated for testing.")
    if m.get("reduced"):
        notes.append("Long recording: charts, replay and motion use the high-rate channels averaged down to the rates "
                     "shown; peak g, spectra and vibration were measured on every full-rate sample.")
    if not m.get("roles", {}).get("gps"):
        notes.append("No location channel in this recording.")
    return {
        "device": dev,
        "start_utc": m.get("start_utc"),
        "duration_s": m.get("duration_s"),
        "file": m.get("source", {}),
        "channels": [
            {"id": c["id"], "name": c["name"], "rate_hz": c.get("source_rate_hz") or c.get("rate_hz"),
             "samples": c.get("source_n") or c.get("n"),
             "analysis_rate_hz": c.get("rate_hz") if c.get("decimation", 1) > 1 else None,
             "subchannels": c.get("subchannels", [])}
            for c in m.get("channels", [])
        ],
        "roles": m.get("roles", {}),
        "gps_fields": m.get("gps_fields", []),
        "notes": notes,
    }
