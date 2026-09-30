"""Parser tests against Drone_Flight.IDE (reference values from the build spec)."""
import numpy as np
import pytest


def test_device_and_session(drone_bundle):
    m = drone_bundle.meta
    assert m["device"]["serial"] == 14201
    assert m["device"]["model"] == "S4-E100D40"
    assert m["device"]["firmware"] == "03.0.17"
    assert m["device"]["recorder_name"] == "Configured for Calibration"
    assert m["device"]["calibration_expired"] is True
    assert m["start_utc"].startswith("2024-04-28T18:45:42")
    assert m["duration_s"] == pytest.approx(495, abs=3)


def test_channel_inventory(drone_bundle):
    chans = {c["id"]: c for c in drone_bundle.meta["channels"]}
    expect = {8: 5000, 80: 1984, 84: 3317, 47: 100, 20: 10, 59: 3.3, 76: 4}
    assert set(expect) <= set(chans)
    for cid, rate in expect.items():
        assert chans[cid]["rate_hz"] == pytest.approx(rate, rel=0.1), cid
    assert [s["units"] for s in chans[8]["subchannels"]] == ["g", "g", "g"]
    assert [s["column"] for s in chans[20]["subchannels"]] == ["pressure", "temperature", "humidity"]


def test_roles_and_no_location(drone_bundle):
    r = drone_bundle.roles
    assert r["accel"] == 80 and r["hf_accel"] == 8 and r["gyro"] == 47 and r["env"] == 20 and r["light"] == 76
    assert not r["gps"]
    assert drone_bundle.has_gps is False


def test_reference_values(drone_bundle):
    env = drone_bundle.channel(20)
    assert env["pressure"].min() == pytest.approx(100815, abs=30)
    assert env["pressure"].max() == pytest.approx(101234, abs=30)
    assert env["temperature"].min() == pytest.approx(22.5, abs=0.3)
    assert env["temperature"].max() == pytest.approx(28.1, abs=0.3)
    assert 35 <= env["humidity"].min() <= 37 and 44 <= env["humidity"].max() <= 46
    assert drone_bundle.channel(76)["lux"].max() == 0
    a = drone_bundle.channel(80)
    mag = np.linalg.norm(a[["x", "y", "z"]].to_numpy(float), axis=1)
    assert mag.mean() == pytest.approx(1.75, abs=0.05)
    assert mag.max() == pytest.approx(15.2, abs=0.3)
    g = drone_bundle.channel(47)
    for ax, pk in zip("xyz", (227, 319, 66)):
        assert g[ax].abs().max() == pytest.approx(pk, rel=0.03)


def test_climb(drone_bundle):
    from engine.explorer.environment import environment
    e = environment(drone_bundle)
    assert e["altitude"]["max_m"] == pytest.approx(35, abs=4)


def test_propeller_band(drone_bundle):
    """The spec lists ~193 Hz; the recording's resultant PSD peaks in the 185-215 Hz propeller band."""
    from engine.explorer.frequency import frequency
    f = frequency(drone_bundle, "accel")
    res = [p for p in f["peaks"] if p["axis"] == "resultant" and 150 <= p["f_hz"] <= 400]
    assert res and 185 <= min(res, key=lambda p: p["rank"])["f_hz"] <= 215
