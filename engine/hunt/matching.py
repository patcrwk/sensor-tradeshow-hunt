"""Match an uploaded recording to the open run for that sensor."""
from __future__ import annotations

from datetime import datetime, timezone

CLOCK_SKEW_S = 600  # allow the sensor clock to be up to 10 minutes behind the booth


def candidate_runs(serial, start_epoch: float | None, open_runs: list[dict]) -> list[dict]:
    """open_runs: [{id, serial, checkout_epoch}]. Returns best-first candidates.

    The best match is the open run for this serial checked out most recently
    before the recording started.
    """
    out = []
    for r in open_runs:
        if str(r["serial"]) != str(serial):
            continue
        if start_epoch is None:
            out.append({**r, "score": 0.5, "reason": "serial matches; recording has no start time"})
            continue
        lead = start_epoch - r["checkout_epoch"]
        if lead >= -CLOCK_SKEW_S:
            out.append({**r, "score": 1.0, "lead_s": lead,
                        "reason": f"serial matches; checked out {_fmt(lead)} before recording started"})
        else:
            out.append({**r, "score": 0.2, "lead_s": lead,
                        "reason": "serial matches, but recording started before check-out"})
    out.sort(key=lambda r: (-r["score"], abs(r.get("lead_s", 0))))
    return out


def _fmt(s: float) -> str:
    s = abs(s)
    if s < 90:
        return f"{s:.0f} s"
    if s < 5400:
        return f"{s / 60:.0f} min"
    return f"{s / 3600:.1f} h"


def epoch_now() -> float:
    return datetime.now(timezone.utc).timestamp()
