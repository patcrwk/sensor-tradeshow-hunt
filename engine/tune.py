"""Print everything needed to re-tune thresholds on a real recording.

    python -m engine.tune path/to/file.IDE [--course course_package.zip | --survey]

Shows channel discovery, GPS quality, detected rests (with the hand-tremor
measure), identity results, step counts and, for surveys, station coordinates.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np

from .config import get_config
from .course.package import read_package
from .course.survey import derive_course, runtime_course
from .detect.stillness import detect_rests
from .detect.taps import detect_taps, group_taps
from .hunt.validation import process_run
from .io.bundle import open_bundle
from .io.channel_discovery import describe
from .io.ide_reader import discover, ide_to_bundle, open_doc
from .io.channel_discovery import assign_roles
from .position.dead_reckoning import detect_steps
from .position.gps_filter import availability, fix_sigma, valid_mask


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--survey", action="store_true", help="treat the file as a survey walk")
    ap.add_argument("--course", help="course package zip to identify stations against")
    a = ap.parse_args()
    cfg = get_config()
    src = Path(a.file)
    with tempfile.TemporaryDirectory() as tmp:
        if src.suffix.lower() == ".ide":
            doc = open_doc(src)
            chans = discover(doc)
            print("== Channel discovery")
            print(describe(chans, assign_roles(chans)))
            b = ide_to_bundle(src, Path(tmp) / "b")
        else:
            b = open_bundle(src)
        print(f"\n== Recording: serial {b.meta['device'].get('serial')}, {b.duration_s:.0f} s, start {b.meta.get('start_utc')}")

        print("\n== GPS quality")
        if b.has_gps:
            g = b.gps()
            ok = valid_mask(g, cfg)
            print(f"  fixes {len(g)}, accepted {ok.sum()} ({ok.mean():.0%}); availability {availability(g, 0, b.duration_s, cfg):.0%}")
            print(f"  median sigma {np.median(fix_sigma(g[ok], cfg)) if ok.any() else float('nan'):.1f} m; fields {b.meta.get('gps_fields')}")
            for c in ("sats", "hdop", "acc", "fix"):
                if c in g:
                    print(f"  {c}: median {g[c].median():.2f}, min {g[c].min():.2f}, max {g[c].max():.2f}")
        else:
            print("  no location channel")

        print("\n== Rests (thresholds: std < %.4f g, |a|-1 < %.3f g, gyro < %.1f dps, tremor < %.4f g)" % (
            cfg.stillness.accel_std_g, cfg.stillness.mag_band_g, cfg.stillness.gyro_max_dps, cfg.stillness.tremor_rms_max_g))
        st = detect_rests(b, cfg)
        for r in sorted(st.rests + st.rejected, key=lambda r: r.start):
            g = ", ".join(f"{v:+.2f}" for v in r.gravity_unit)
            print(f"  {r.start:8.1f} to {r.end:8.1f} s  {r.duration:5.1f} s  {r.reason:10s} tremor {r.tremor_rms_g:.4f} g"
                  f"  std {r.accel_std_g:.4f} g  gyro {r.gyro_mean_dps or 0:.2f} dps  gravity [{g}]")
        taps = group_taps(detect_taps(b, cfg), cfg)
        print(f"\n== Tap groups: {[(round(t['start'], 1), t['count']) for t in taps]}")
        steps = detect_steps(b, cfg, exclude=[(r.start, r.end) for r in st.rests])
        print(f"\n== Steps: {steps.count}, cadence {steps.cadence_spm:.0f} spm, walking {steps.walking_s:.0f} s")

        if a.survey:
            c = derive_course([b], cfg)
            print("\n== Survey result")
            print(json.dumps(c["quality"], indent=2))
            for s in c["stations"]:
                print(f"  {s['id']}: x {s['x']:7.1f} y {s['y']:7.1f}  lat {s['lat']} lon {s['lon']}  acc {s['accuracy_m']} m  "
                      f"fixes {s['gps_fixes']}  taps {s['tap_count']}  reserved pose {s['reserved_pose']}")
            print(f"  methods {c['identity_methods']}; radius {c['match_radius_m']} m; par {c['par']['par_time_s']} s")
            for w in c["warnings"]:
                print("  WARNING:", w)
        if a.course:
            pkg = read_package(Path(a.course).read_bytes())
            res = process_run(b, runtime_course(pkg["course"]), cfg)
            print("\n== Identity results against course")
            for ci in res["checkins"] + res["strays"]:
                print(f"  {ci['rest_start']:8.1f} s  {ci.get('station') or '-':6s} {ci['status']:9s} "
                      + "; ".join(f"{m['method']}: {m.get('detail')}" for m in ci["methods"]))
            print(f"  elapsed {res['elapsed_s']} s, complete {res['complete']}, notes {res['notes']}")


if __name__ == "__main__":
    main()
