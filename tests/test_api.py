"""API smoke tests (FastAPI TestClient): every visible control calls an endpoint that works."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def run(sample):
    jid = client.post("/api/analyses", json={"sample_id": sample}).json()["job_id"]
    for _ in range(200):
        s = client.get(f"/api/analyses/{jid}").json()
        if s["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert s["status"] == "done", s
    assert [x["key"] for x in s["stages"]] == ["visual_frame", "visual_text", "audio", "claim_set", "tape", "fill", "knowability",
                                               "data_age", "certificate"]
    return jid, s


def test_health_and_samples():
    h = client.get("/api/health").json()
    assert h["ok"] and h["upload_enabled"] is False          # hosted mode by default
    ids = {x["id"] for x in client.get("/api/samples").json()}
    assert {"tv18_nifty_bank_1301", "synthetic_trade_claims"} <= ids


def test_real_sample_end_to_end_and_exports():
    jid, s = run("tv18_nifty_bank_1301")
    res = client.get(f"/api/analyses/{jid}/result").json()
    assert res["tau"]["status"] == "IDENTIFIED" and res["tau"]["day"] == "2026-10-06"          # time from chart ratchets, no clock
    cert = res["certificate"]
    assert [c["name"] for c in cert["checks"]] == ["FILL CONSERVATION", "KNOWABILITY", "DATA AGE"]
    assert all(c["verdict"] in ("PASS", "FAIL", "ABSTAIN") for c in cert["checks"])
    assert cert["checks"][0]["verdict"] == "ABSTAIN"            # no fill claims in a news broadcast -> honest ABSTAIN
    assert all("input" in v and "output" in v for v in res["stages"].values())
    j = client.get(f"/api/analyses/{jid}/report.json")
    assert j.status_code == 200 and "attachment" in j.headers["content-disposition"]
    h = client.get(f"/api/analyses/{jid}/report.html")
    assert h.status_code == 200 and "Impossibility Certificate" in h.text


def test_synthetic_sample_labelled():
    jid, _ = run("synthetic_trade_claims")
    res = client.get(f"/api/analyses/{jid}/result").json()
    assert res["meta"]["synthetic"] is True
    fill = {i["claim_id"]: i["verdict"] for i in res["branches"]["fill"]["items"]}
    assert fill == {"s1": "PASS", "s2": "FAIL", "s3": "FAIL", "s4": "FAIL", "s5": "PASS", "s6": "PASS", "s7": "ABSTAIN"}


def test_check_claim_and_validation():
    r = client.post("/api/check-claim", json={"instrument": "ITC", "price": 265.5, "date": "2026-10-06", "time": "10:31", "quantity": 1800})
    assert r.status_code == 200 and r.json()["verdict"].startswith("Consistent") and r.json()["user_supplied"]
    assert r.json()["fill_branch"]["verdict"] == "PASS"
    assert client.post("/api/check-claim", json={"instrument": "ITC", "price": -1, "date": "2026-10-06"}).status_code == 422
    assert client.post("/api/check-claim", json={"instrument": "ITC", "price": 1, "date": "06/10/2026"}).status_code == 422


def test_upload_refused_in_hosted_mode_and_media_paths_safe():
    r = client.post("/api/upload", files={"file": ("x.mp4", b"0" * 10, "video/mp4")})
    assert r.status_code == 501
    assert client.get("/media/../backend/app.py").status_code == 404
    assert client.get("/media/tv18_nifty_bank_1301/..%2F..%2Fpackage.json").status_code == 404
    assert client.get("/").status_code == 200 and client.get("/static/app.js").status_code == 200
