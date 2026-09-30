"""Generate synthetic survey and participant files.

    python -m engine.synthetic.cli --out fixtures/synthetic --gps outdoor --participants 3
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

from .generator import Opts, default_course, participant, survey, zip_bundle


def generate_set(out: Path, gps_profile: str = "outdoor", use_holders: bool = False, use_taps: bool = False,
                 serial: int = 90001, seed: int = 1, n_participants: int = 3, survey: bool = True,
                 start_epoch: float | None = None, stations: int = 6) -> list[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    course = default_course(stations)
    t0 = start_epoch or time.time() + 60
    files = []
    tag = f"{gps_profile}{'_holders' if use_holders else ''}{'_taps' if use_taps else ''}"
    if survey:
        o = Opts(gps_profile=gps_profile, use_holders=use_holders, use_taps=use_taps, serial=serial + 900,
                 seed=seed, start_epoch=t0 - 3600)
        g = _survey(course, o)
        b = g.write(out / f"survey_{tag}_s{seed}")
        files.append(zip_bundle(b))
    rng = random.Random(seed)
    for k in range(n_participants):
        order = [s["number"] for s in course.stations]
        rng.shuffle(order)
        if k == 2:
            order = order[:-1]          # one participant skips a station
        o = Opts(gps_profile=gps_profile, use_holders=use_holders, use_taps=use_taps, serial=serial + k,
                 seed=seed * 100 + k, start_epoch=t0 + k * 5,
                 speed_mps=rng.uniform(1.1, 1.6), cadence_hz=rng.uniform(1.7, 2.1))
        g = participant(course, o, order, strays=1, hand_holds=1)
        b = g.write(out / f"participant_{tag}_{serial + k}_s{seed}")
        files.append(zip_bundle(b))
    return files


def _survey(course, o):
    return survey(course, o)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="fixtures/synthetic")
    ap.add_argument("--gps", default="outdoor", choices=["outdoor", "indoor", "dropout", "none"])
    ap.add_argument("--holders", action="store_true")
    ap.add_argument("--taps", action="store_true")
    ap.add_argument("--participants", type=int, default=3)
    ap.add_argument("--serial", type=int, default=90001)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-survey", action="store_true")
    a = ap.parse_args()
    files = generate_set(Path(a.out), a.gps, a.holders, a.taps, a.serial, a.seed, a.participants, not a.no_survey)
    for f in files:
        print(f)


if __name__ == "__main__":
    main()
