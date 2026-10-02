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


def test_staff_login(client, monkeypatch):
    monkeypatch.setenv("STAFF_PASSWORD", "duck-pond")
    client.cookies.clear()
    assert client.get("/api/auth/me").json() == {"staff": False, "required": True}
    assert client.get("/api/runs").status_code == 401                 # staff data locked
    assert client.get("/api/admin/leads.csv").status_code == 401
    assert client.post("/api/admin/reset", json={"confirm": "RESET"}).status_code == 401
    assert client.get("/api/leaderboards").status_code == 200          # big screen stays public
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "duck-pond"}).status_code == 200
    assert client.get("/api/runs").status_code == 200
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/runs").status_code == 401


def test_qr_checkins(client, monkeypatch):
    """No GPS: participant phone scans station codes; sensor rests prove the stops."""
    monkeypatch.setenv("STAFF_PASSWORD", "duck-pond")
    client.post("/api/auth/login", json={"password": "duck-pond"})
    import numpy as np
    from engine.api.db import Scan, session
    from engine.synthetic.cli import generate_set
    files = generate_set(client.tmp / "s3", "none", serial=8300, n_participants=1)
    sv = [f for f in files if "survey" in f.name][0]
    c = client.post("/api/courses/survey", files=[("files", (sv.name, sv.read_bytes()))], data={"name": "QR"}).json()
    c = client.patch(f"/api/courses/{c['id']}", json={"identity_methods": ["qr"]}).json()
    codes = c["data"]["qr_codes"]
    assert set(codes) == {"BOOTH", *[s["id"] for s in c["data"]["stations"]]}
    client.post(f"/api/courses/{c['id']}/publish")
    # the public course view must not leak the codes; staff still see them
    assert "qr_codes" in client.get("/api/courses/active").json()["data"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert "qr_codes" not in client.get("/api/courses/active").json()["data"]

    client.post("/api/auth/login", json={"password": "duck-pond"})
    run = client.post("/api/runs/checkout", json={"display_name": "Cy", "serial": "8300"}).json()["run"]
    tok = run["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()                           # a participant's phone is not logged in
    assert client.get(f"/api/qr/station/{codes['S1']}").json()["station"]["id"] == "S1"
    assert client.get("/api/qr/station/not-a-code").status_code == 404
    r = client.post("/api/qr/scan", json={"token": tok, "code": codes["S1"]}).json()
    assert r["station"]["id"] == "S1" and not r["duplicate"]
    assert client.post("/api/qr/scan", json={"token": tok, "code": codes["S1"]}).json()["duplicate"]
    assert client.post("/api/qr/scan", json={"token": "bogus", "code": codes["S1"]}).status_code == 404
    client.post("/api/auth/login", json={"password": "duck-pond"})

    # Replace the live scans with ones timed against the synthetic recording's rests
    p = [f for f in files if "participant" in f.name][0]
    import json, zipfile
    with zipfile.ZipFile(p) as z:
        gt = json.loads(z.read("ground_truth.json"))
        start = json.loads(z.read("meta.json"))["start_epoch"]
    with session() as s:
        for sc in s.exec(__import__("sqlmodel").select(Scan).where(Scan.run_id == run["id"])).all():
            s.delete(sc)
        for rr in gt["rests"]:
            if rr["kind"] == "stray":
                continue
            sid = "BOOTH" if rr["label"] in ("START", "FINISH") else f"S{rr['label']}"
            s.add(Scan(run_id=run["id"], station=sid, at=start + rr["start"] - 10 + 180))   # clock off by 3 min
        s.commit()
    up = client.post("/api/uploads", files={"file": (p.name, p.read_bytes())}).json()
    client.post(f"/api/runs/{run['id']}/attach", json={"upload_id": up["upload"]["id"]})
    for _ in range(100):
        d = client.get(f"/api/runs/{run['id']}").json()
        if d["run"]["status"] != "processing":
            break
        time.sleep(0.1)
    res = d["result"]
    visited = [f"S{v}" for v in gt["visits"]]
    assert [ci["station"] for ci in res["checkins"]] == visited
    assert d["run"]["status"] == "published" and res["complete"]
    me = client.get(f"/api/p/{tok}").json()
    assert me["name"] == "Cy" and me["result"]["rank"] >= 1 and len(me["scans"]) == len(visited) + 2
    assert "company" not in json.dumps(client.get(f"/api/runs/{run['id']}/public").json())
