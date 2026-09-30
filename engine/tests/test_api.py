"""API: synthetic run uploaded through the API reaches the leaderboard quickly."""
import os
import time

import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("api")
    os.environ["DATA_DIR"] = str(d)
    os.environ["ENGINE_NO_BACKGROUND"] = "1"
    from engine.api import db
    db.reset_engine()
    from fastapi.testclient import TestClient
    from engine.api.app import app
    with TestClient(app) as c:
        c.tmp = d
        yield c
    db.reset_engine()


def test_phase1_no_course(client):
    """Phase 1: no course published; START/FINISH from first/last rest."""
    from engine.synthetic.cli import generate_set
    files = generate_set(client.tmp / "s1", "outdoor", serial=8100, n_participants=1, survey=False)
    run = client.post("/api/runs/checkout", json={"display_name": "Ada", "serial": "8100"}).json()["run"]
    t = time.time()
    up = client.post("/api/uploads", files={"file": (files[0].name, files[0].read_bytes())}).json()
    assert up["candidates"][0]["id"] == run["id"]
    client.post(f"/api/runs/{run['id']}/attach", json={"upload_id": up["upload"]["id"]})
    for _ in range(100):
        rows = client.get("/api/leaderboard?category=fastest").json()["rows"]
        if rows:
            break
        time.sleep(0.1)
    assert rows and rows[0]["name"] == "Ada"
    assert time.time() - t < 10
    # re-upload is harmless
    again = client.post("/api/uploads", files={"file": (files[0].name, files[0].read_bytes())}).json()
    assert again["upload"]["id"] == up["upload"]["id"] and again["attached_run"] == run["id"]


def test_course_flow_and_override(client):
    from engine.synthetic.cli import generate_set
    files = generate_set(client.tmp / "s2", "outdoor", serial=8200, n_participants=1)
    sv = [f for f in files if "survey" in f.name][0]
    c = client.post("/api/courses/survey", files=[("files", (sv.name, sv.read_bytes()))], data={"name": "T"}).json()
    assert c["status"] == "draft" and len(c["data"]["stations"]) == 6
    c = client.patch(f"/api/courses/{c['id']}", json={"stations": [{"id": "S1", "name": "Coffee"}], "order_rule": "any"}).json()
    assert c["data"]["stations"][0]["name"] == "Coffee"
    assert client.post(f"/api/courses/{c['id']}/publish").json()["status"] == "published"
    p = [f for f in files if "participant" in f.name][0]
    run = client.post("/api/runs/checkout", json={"display_name": "Bo", "serial": "8200"}).json()["run"]
    up = client.post("/api/uploads", files={"file": (p.name, p.read_bytes())}).json()
    client.post(f"/api/runs/{run['id']}/attach", json={"upload_id": up["upload"]["id"]})
    for _ in range(100):
        d = client.get(f"/api/runs/{run['id']}").json()
        if d["run"]["status"] != "processing":
            break
        time.sleep(0.1)
    assert d["run"]["status"] == "published"
    cis = d["result"]["checkins"]
    # staff remove one check-in with a note
    r = client.put(f"/api/runs/{run['id']}/checkins", json={"checkins": cis[1:], "note": "test removal"})
    assert r.status_code == 200
    d = client.get(f"/api/runs/{run['id']}").json()
    assert len(d["result"]["checkins"]) == len(cis) - 1
    assert any(a["action"] == "override" for a in d["audit"])
    exp = client.get(f"/api/courses/{c['id']}/export")
    imp = client.post("/api/courses/import", files={"file": ("c.zip", exp.content)}).json()
    assert len(imp["data"]["stations"]) == 6
