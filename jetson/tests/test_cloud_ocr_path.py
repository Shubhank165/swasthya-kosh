"""Local capture consent/ownership tests. Hospital transfer stays blocked, even with its flag on.

Non-idempotent upload/receipt tests remain in test_document_outbox and test_intake_api;
a device flag must never reactivate the old unconsented patient upload path.
"""

import io
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_offline_workflow import Driver
from test_offline_workflow import settings as _settings  # noqa: F401

from medikiosk.app import create_app


@pytest.fixture
def capture(monkeypatch):
    reads = []

    class OCR:
        def __init__(self, *args):
            pass

        def load(self):
            pass

        def read(self, path):
            reads.append(path)
            return "Tab Paracetamol 500mg", [0.3]

    monkeypatch.setitem(sys.modules, "ocr.models.adapters", types.SimpleNamespace(PPOcrOnnx=OCR))
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(image, format="PNG")
    return image.getvalue(), reads, OCR


def documents(driver):
    driver.reach_service()
    driver.act("choose", "yes")
    driver.act("choose", "yes")
    assert driver.screen["stage"] == "documents"


@pytest.mark.parametrize("enabled", [False, True])
def test_local_document_permission_never_authorizes_cloud(settings, capture, monkeypatch, enabled):
    image, reads, _ = capture
    requests = []

    def no_network(*args, **kwargs):
        requests.append(args)
        raise AssertionError("Patient journey attempted network transfer")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    settings.handwritten_cloud_ocr = enabled
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        documents(driver)
        result = client.post(
            "/api/ocr", headers=driver.scan_headers, files={"image": ("synthetic.png", image)}
        )
        assert result.status_code == 200
        assert result.json()["outbox_handle"] is None
        driver.act("preview", {**result.json(), "lines": ["forged tablet text"]})
        assert driver.screen["capture_preview"]["lines"] == ["Tab Paracetamol 500mg"]
        driver.act("keep")
        driver.act("done")
        driver.act("confirm")
        assert driver.report["completion"] == "saved_local"
        assert driver.report["cloud_status"] == "not_requested"
        assert driver.report["documents"][0]["lines"] == ["Tab Paracetamol 500mg"]
        assert not any(
            d["purpose"].startswith("cloud") and d["decision"] == "granted"
            for d in driver.report["consent"]["decisions"]
        )
    assert requests == []
    assert reads and all(not path.exists() for path in reads)
    assert not (settings.session_store_path.parent / "outbox").exists()


def test_forged_or_foreign_capture_cannot_be_kept(settings, capture):
    image, _, _ = capture
    with (
        TestClient(create_app(settings)) as client,
        client.websocket_connect("/ws/session") as first_ws,
        client.websocket_connect("/ws/session") as second_ws,
    ):
        first, second = Driver(first_ws), Driver(second_ws)
        documents(first)
        documents(second)
        assert client.post("/api/ocr", files={"image": ("synthetic.png", image)}).status_code == 401
        captured = client.post(
            "/api/ocr", headers=first.scan_headers, files={"image": ("synthetic.png", image)}
        ).json()
        for value in ({"capture_id": "../../etc/passwd"}, captured):
            second_ws.send_json(second.envelope("preview", value))
            assert second.until("error")["stage"] == "flow"
        second.act("done")
        second.act("confirm")
        assert second.report["documents"] == []
        first.act("preview", captured)
        first.act("keep")
        # The handle is single use; replay with a new action ID cannot duplicate a document.
        first_ws.send_json(first.envelope("preview", captured))
        assert first.until("error")["stage"] == "flow"


@pytest.mark.parametrize("resolution", ["keep", "discard", "retake"])
def test_empty_preview_requires_explicit_resolution(settings, capture, monkeypatch, resolution):
    image, reads, OCR = capture

    def empty(self, path):
        reads.append(path)
        return "", []

    monkeypatch.setattr(OCR, "read", empty)
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        documents(driver)
        captured = client.post(
            "/api/ocr", headers=driver.scan_headers, files={"image": ("synthetic.png", image)}
        ).json()
        driver.act("preview", captured)
        assert driver.screen["capture_preview"]["lines"] == []
        ws.send_json(driver.envelope("done"))
        assert driver.until("error")["stage"] == "flow"
        driver.act(resolution)
        assert "capture_preview" not in driver.screen
        if resolution == "retake":
            assert any(
                e["type"] == "device.action" and e["action"] == "scan" for e in driver.events
            )
        driver.act("done")
        driver.act("confirm")
        assert len(driver.report["documents"]) == (1 if resolution == "keep" else 0)
    assert all(not path.exists() for path in reads)


def test_withdrawal_while_ocr_runs_rejects_stale_result(settings, capture, monkeypatch):
    image, reads, OCR = capture
    started, release = threading.Event(), threading.Event()

    def slow(self, path):
        reads.append(path)
        started.set()
        assert release.wait(3), "Test did not release synthetic OCR"
        return "Synthetic private text", [0.5]

    monkeypatch.setattr(OCR, "read", slow)
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        documents(driver)
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(
                client.post,
                "/api/ocr",
                headers=driver.scan_headers,
                files={"image": ("synthetic.png", image)},
            )
            try:
                assert started.wait(3)
                driver.act("withdraw")
                driver.act("confirm")
                assert driver.screen["stage"] == "declined"
            finally:
                release.set()
            assert response.result(timeout=4).status_code == 409
    assert all(not path.exists() for path in reads)


def test_bad_image_with_valid_permission_is_recoverable(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        documents(driver)
        assert (
            client.post(
                "/api/ocr",
                headers=driver.scan_headers,
                files={"image": ("bad.jpg", b"not an image")},
            ).status_code
            == 422
        )
        driver.act("done")
        assert driver.screen["stage"] == "review"
