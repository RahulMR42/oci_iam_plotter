"""Tenant selection must scope every snapshot-backed API view."""

from dataclasses import replace

from fastapi.testclient import TestClient

from oci_iam_plotter import api
from oci_iam_plotter.store import SnapshotStore


def test_selected_tenancy_uses_its_latest_snapshot_and_history(snapshot, tmp_path, monkeypatch) -> None:
    store = SnapshotStore(tmp_path, max_history=5)
    first = replace(snapshot, tenancy_id="tenancy-one", collected_at="2026-08-01T10:00:00+00:00")
    newest = replace(snapshot, tenancy_id="tenancy-one", collected_at="2026-08-03T10:00:00+00:00")
    second = replace(snapshot, tenancy_id="tenancy-two", collected_at="2026-08-02T10:00:00+00:00")
    store.save(first)
    store.save(newest)
    store.save(second)
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "credentials_match", lambda _username, _password: True)

    with TestClient(api.app) as client:
        assert client.post("/api/login", json={"username": "oci", "password": "test"}).status_code == 200
        listed = client.get("/api/tenancies").json()
        assert listed["active_tenancy_id"] == "tenancy-one"
        assert {item["id"]: item["snapshot_count"] for item in listed["tenancies"]} == {
            "tenancy-one": 2, "tenancy-two": 1,
        }
        assert client.post("/api/tenancies/select", json={"tenancy_id": "tenancy-two"}).status_code == 200
        assert client.get("/api/snapshot").json()["tenancy_id"] == "tenancy-two"
        history = client.get("/api/history").json()["records"]
        assert len(history) == 1
        assert history[0]["tenancy_id"] == "tenancy-two"
