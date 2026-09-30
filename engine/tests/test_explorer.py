"""Explorer: every analysis renders for the drone file; the Story reports climb, propeller and peak."""


def test_drone_analysis(drone_bundle):
    from engine.explorer.analyze import analyze
    from engine.explorer.timeseries import window
    a = analyze(drone_bundle, "drone")
    for k in ("frequency", "shock", "environment", "motion"):
        assert a[k].get("available"), k
    assert a["gps"]["available"] is False
    titles = " | ".join(i["title"] for i in a["story"]["timeline"] + a["story"]["facts"])
    assert "Climbed about" in titles
    assert "Propeller signature near" in titles
    assert "Peak event 15.2 g" in titles
    assert "Dark the whole time" in titles
    w = window(drone_bundle, 8, 100, 110, 500)
    assert len(w["t"]) <= 500 and set(w["series"]) == {"x", "y", "z"}


def test_generic_profile(drone_bundle):
    from engine.explorer.analyze import analyze
    a = analyze(drone_bundle, "generic")
    assert a["story"]["profile"] == "generic"
