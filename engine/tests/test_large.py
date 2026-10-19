"""Long recordings: pieced upload, slice-by-slice reading, full-rate statistics."""
import json
import os
import time

import numpy as np
import pytest

from engine.config import _load, get_config
from engine.io.reduce import stream_channel

from .conftest import DRONE


class FakeChannel:
    """An idelib EventArray stand-in: 5 kHz, 120 Hz vibration, one 6.5 g spike."""
    fs, n, spike = 5000.0, 3_000_000, 1_234_567

    def __len__(self):
        return self.n

    def arraySlice(self, a, b):
        t = np.arange(a, b) / self.fs
        rng = np.random.default_rng(a)
        v = np.vstack([0.02 * rng.standard_normal(b - a) + 0.05 * np.sin(2 * np.pi * 120 * t),
                       0.02 * rng.standard_normal(b - a), 1 + 0.02 * rng.standard_normal(b - a)])
        if a <= self.spike < b:
            v[2, self.spike - a] = 6.5
        return np.vstack([t * 1e6, v])


def test_stream_channel_keeps_full_rate_peaks(tmp_path):
    cfg = get_config()
    ch = FakeChannel()
    df, n = stream_channel(ch, [(0, "x"), (1, "y"), (2, "z")], 20, 0.0, tmp_path, 8, ch.fs, cfg, True)
    assert n == ch.n and len(df) == ch.n // 20
    fr = json.loads((tmp_path / "full_8.json").read_text())
    top = fr["events"][0]
    assert top["t"] == pytest.approx(ch.spike / ch.fs, abs=1e-6)
    assert top["resultant_g"] == pytest.approx(6.5, abs=0.05)       # averaged data alone would show ~1.3 g
    assert df["z"].max() < 2.0
    f = np.array(fr["psd"]["f"])
    assert f[np.argmax(fr["psd"]["x"])] == pytest.approx(120, abs=1)
    env = __import__("pandas").read_parquet(tmp_path / "env_8.parquet")
    assert env["z__max"].max() == pytest.approx(6.5, abs=1e-3)       # the chart envelope keeps the spike


@pytest.fixture()
def client(tmp_path, monkeypatch):
    os.environ["DATA_DIR"] = str(tmp_path)
    os.environ["ENGINE_NO_BACKGROUND"] = "1"
    from engine.api import db
    db.reset_engine()
    lc = _load()["large_recordings"]
    saved = dict(lc)
    lc.update(full_rows_max=100, max_rows_per_channel=200_000, chunk_mb=4)   # force the long-file path
    from fastapi.testclient import TestClient
    from engine.api.app import app
    with TestClient(app) as c:
        yield c
    lc.clear()
    lc.update(saved)
    db.reset_engine()


def _wait(c, url, busy="processing", timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        st = c.get(url).json()
        if st["status"] != busy:
            return st
        time.sleep(0.3)
    raise AssertionError("timed out")


def test_pieced_upload_of_long_recording(client):
    if not DRONE.exists():
        pytest.skip("fixtures/Drone_Flight.IDE not present")
    from engine.api import services as S, storage
    data = DRONE.read_bytes()
    j = client.post("/api/uploads/chunked", json={"filename": "Flight.IDE", "size": len(data)}).json()
    step, off = j["chunk_bytes"], 0
    assert client.post(f"/api/uploads/chunked/{j['id']}/finish").status_code == 409   # nothing sent yet
    while off < len(data):
        r = client.put(f"/api/uploads/chunked/{j['id']}?offset={off}", content=data[off:off + step])
        assert r.status_code == 200
        assert client.put(f"/api/uploads/chunked/{j['id']}?offset={off}", content=data[off:off + step]).status_code == 200
        off = r.json()["received"]
    assert client.put(f"/api/uploads/chunked/{j['id']}?offset={off + step}", content=b"x").status_code == 409
    client.post(f"/api/uploads/chunked/{j['id']}/finish")
    st = _wait(client, f"/api/uploads/chunked/{j['id']}")
    assert st["status"] == "done", st["error"]
    rec = _wait(client, f"/api/recordings/{st['recording_id']}")
    assert rec["status"] == "ready", rec["error"]
    a = client.get(f"/api/recordings/{rec['id']}/analysis").json()
    assert a["shock"]["summary"]["peak_g"] == pytest.approx(15.187, abs=0.01)   # same as reading it whole
    assert any("Long recording" in n for n in a["overview"]["notes"])
    # a restart wipes the local cache: the stored bundle rebuilds it
    import shutil
    shutil.rmtree(S.dirs()["bundles"])
    S._bundle.cache_clear()
    assert len(client.get(f"/api/recordings/{rec['id']}/timeseries?ch=8").json()["t"]) > 100
    assert not list(S.dirs()["uploads"].glob(".chunked-*"))
    assert storage.exists(f"upload/{a['overview']['file']['sha256'][:16]}.bundle.zip")
