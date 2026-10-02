"""Synthetic generator, detection, and the full pipeline in every positioning mode."""
import random

import numpy as np
import pytest

from engine.course.survey import derive_course, runtime_course
from engine.detect.stillness import detect_rests
from engine.detect.taps import detect_taps, group_taps
from engine.hunt.evaluate import (checkin_accuracy, passes_stations_in_order, route_deviation,
                                  station_errors, truth_transform)
from engine.hunt.validation import process_run
from engine.io.bundle import open_bundle
from engine.synthetic.generator import Opts, default_course, participant, survey

COURSE = default_course()


def _survey(tmp, profile, holders=False, taps=False, seed=11):
    o = Opts(gps_profile=profile, use_holders=holders, use_taps=taps, seed=seed)
    return open_bundle(survey(COURSE, o).write(tmp / f"sv_{profile}_{holders}_{taps}_{seed}"))


def _runs(tmp, profile, holders=False, taps=False, n=4):
    out = []
    for k in range(n):
        order = [1, 2, 3, 4, 5, 6]
        random.Random(k).shuffle(order)
        o = Opts(gps_profile=profile, use_holders=holders, use_taps=taps, seed=100 + k,
                 speed_mps=1.2 + 0.1 * k, cadence_hz=1.7 + 0.1 * k)
        out.append(open_bundle(participant(COURSE, o, order, strays=1, hand_holds=1)
                               .write(tmp / f"p_{profile}_{holders}_{taps}_{k}")))
    return out


@pytest.mark.parametrize("profile", ["outdoor", "indoor", "dropout", "none"])
def test_generator_ground_truth(tmp_path, profile):
    b = _survey(tmp_path, profile)
    gt = b.ground_truth()
    assert gt["gps_profile"] == profile
    assert len(gt["rests"]) == 8 and gt["visits"] == [1, 2, 3, 4, 5, 6]
    assert b.has_gps == (profile != "none")
    if profile == "dropout":
        assert len(b.gps()) < 0.6 * b.duration_s


def test_rests_and_hand_held(tmp_path):
    b = _runs(tmp_path, "outdoor", n=1)[0]
    gt = b.ground_truth()
    st = detect_rests(b)
    assert len(st.rests) == len(gt["rests"])
    assert any(r.reason == "hand_held" for r in st.rejected)
    for r, t in zip(st.rests, gt["rests"]):
        assert abs(r.start - t["start"]) < 1.0 and abs(r.end - t["end"]) < 1.0


def test_taps(tmp_path):
    b = _survey(tmp_path, "outdoor", taps=True)
    assert [g["count"] for g in group_taps(detect_taps(b))] == [1, 2, 3, 4, 5, 6]


def test_survey_stations_within_accuracy(tmp_path):
    b = _survey(tmp_path, "outdoor")
    c = derive_course([b])
    assert c["quality"]["recommended_mode"] == "gps"
    for e in station_errors(c, b.ground_truth()):
        assert e["error_m"] <= e["accuracy_m"], e


def test_multi_survey_average(tmp_path):
    b1 = _survey(tmp_path, "outdoor", seed=11)
    b2 = _survey(tmp_path, "outdoor", seed=12)
    c = derive_course([b1, b2])
    assert c["survey_count"] == 2
    assert all(s.get("surveys") == 2 for s in c["stations"])


@pytest.mark.parametrize("profile,holders,mode", [
    ("outdoor", False, "gps"),
    ("outdoor", False, "fused"),
    ("dropout", True, "dead_reckoning"),
    ("none", True, "dead_reckoning"),
    ("indoor", True, "dead_reckoning"),
])
def test_pipeline(tmp_path, profile, holders, mode):
    sv = _survey(tmp_path, profile, holders)
    course = derive_course([sv], mode=mode if mode == "fused" else None)
    assert course["positioning_mode"] == mode
    rc = runtime_course(course)
    tot = correct = false = 0
    devs = []
    for b in _runs(tmp_path, profile, holders):
        res = process_run(b, rc)
        gt = b.ground_truth()
        acc = checkin_accuracy(res, gt)
        tot += acc["true_station_rests"]
        correct += acc["correct"]
        false += acc["false"]
        assert res["positioning_mode"] == mode
        assert res["complete"]
        assert passes_stations_in_order(res, gt, 10.0, course)
        devs.append(route_deviation(res, gt, truth_transform(course, gt))["median_m"])
    assert correct / tot >= 0.95
    assert false == 0
    print(f"{profile}/{mode}: check-ins {correct}/{tot}, median route deviation {np.median(devs):.1f} m")


def test_optimal_tour():
    from engine.course.leg_matrix import build_matrix, optimal_tour
    c = {"booth": {"x": 0, "y": 0}, "stations": [{"id": f"S{i}", "x": x, "y": y} for i, (x, y) in
                                                 enumerate([(10, 0), (10, 10), (0, 10), (5, 20), (-5, 20), (-10, 5), (20, 5), (15, 25)], 1)]}
    legs, _ = build_matrix(c, [])
    ids = [s["id"] for s in c["stations"]]
    d_bf, _ = optimal_tour(ids[:6], legs)          # brute force path
    d_hk, tour = optimal_tour(ids, legs)           # Held-Karp path
    assert d_bf > 0 and d_hk > d_bf and tour[0] == tour[-1] == "BOOTH"


def test_image_fit():
    from engine.course.image_fit import apply, fit
    pins = [{"x": 0, "y": 0, "u": 100, "v": 200}, {"x": 10, "y": 0, "u": 150, "v": 200},
            {"x": 0, "y": 10, "u": 100, "v": 150}]
    t = fit(pins[:2])
    assert t["kind"] == "similarity"
    u, v = apply(fit(pins)["matrix"], 10, 10)
    assert abs(u - 150) < 1e-6 and abs(v - 150) < 1e-6


@pytest.mark.parametrize("skew", [0.0, 240.0, -420.0])
def test_qr_checkins_no_gps(tmp_path, skew):
    """No GPS, no holders: phone scans identify stations; the sensor rest proves the stop.
    The sensor clock is off by `skew` seconds and must still line up."""
    import numpy as np
    sv = _survey(tmp_path, "none")
    course = derive_course([sv])
    course["identity_methods"] = ["qr"]
    rc = runtime_course(course)
    rng = np.random.default_rng(3)
    for b in _runs(tmp_path, "none", n=2):
        gt = b.ground_truth()
        start = b.meta["start_epoch"]
        scans = []
        for r in gt["rests"]:
            if r["kind"] == "stray":
                continue                                       # nobody scans at a stray stop
            sid = "BOOTH" if r["label"] in ("START", "FINISH") else f"S{r['label']}"
            # scan a few seconds before setting the sensor down; server clock differs from sensor clock
            scans.append({"station": sid, "at": start + r["start"] - rng.uniform(3, 40) - skew})
        res = process_run(b, rc, scans=scans)
        acc = checkin_accuracy(res, gt)
        assert acc["correct"] == acc["true_station_rests"] and acc["false"] == 0, acc
        assert abs(res["qr"]["offset_s"] - skew) < 45
        assert res["complete"] and not res["needs_review"]
        assert len(res["strays"]) == 1                          # the unscanned stop stays a stray
