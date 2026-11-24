"""API tests: real scans of the engine's fixtures, a fake LLM, no network."""

from __future__ import annotations

import io
import json
import time
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shipshape.llm.client import Completion, FatalLLMError, Message

from shipshape_api.app import create_app
from shipshape_api.jobs import LLMConnection

FIXTURES = Path(__file__).resolve().parents[2] / "engine" / "corpus" / "fixtures"


class FakeClient:
    """Answers every finding with a short explanation and no edits."""

    model = "deepseek-flash"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def complete(self, messages: Sequence[Message]) -> Completion:
        if self.error is not None:
            raise self.error
        answer = {"summary": "s", "what": "w", "why": "y", "how_to_fix": "1. h", "edits": []}
        return Completion(json.dumps(answer), 100, 0, 50, 0.0)


def _client(tmp_path: Path, llm: FakeClient | None = None) -> TestClient:
    fake = llm or FakeClient()
    app = create_app(
        data_dir=tmp_path / "data",
        client_factory=lambda: LLMConnection(fake, "deepseek"),
        web_dist=tmp_path / "no-dist",
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SHIPSHAPE_CACHE_DIR", str(tmp_path / "cache"))
    with _client(tmp_path) as test_client:
        yield test_client


def _wait(client: TestClient, scan_id: str, timeout: float = 60) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        scan = client.get(f"/api/scans/{scan_id}").json()
        if scan["status"] in {"done", "failed"}:
            return scan
        time.sleep(0.1)
    raise AssertionError("scan did not finish in time")


def test_health_reports_versions_and_never_the_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-tests-only-0000")

    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["llm"]["configured"] is True
    assert "fake-key" not in json.dumps(body)


def test_scan_a_folder_and_read_the_report(client: TestClient) -> None:
    response = client.post("/api/scans", json={"path": str(FIXTURES / "leaky_emg")})
    assert response.status_code == 202
    scan = _wait(client, response.json()["id"])

    assert scan["status"] == "done"
    assert scan["name"] == "leaky_emg"
    assert scan["findings"] == 9
    report = client.get(f"/api/scans/{scan['id']}/report").json()
    assert report["graph"]["nodes"]
    assert any(f["check_id"] == "correctness.grouped-split-leakage" for f in report["findings"])


def test_scan_with_explanations_uses_the_llm(client: TestClient) -> None:
    response = client.post(
        "/api/scans", json={"path": str(FIXTURES / "leaky_emg"), "explain": True, "max_findings": 3}
    )
    scan = _wait(client, response.json()["id"])

    report = client.get(f"/api/scans/{scan['id']}/report").json()
    explained = [f for f in report["findings"] if f["explanation"]]
    assert len(explained) == 3
    assert report["explain_stats"]["api_calls"] == 3


def test_fatal_llm_error_keeps_the_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHIPSHAPE_CACHE_DIR", str(tmp_path / "cache"))
    with _client(tmp_path, FakeClient(FatalLLMError("Insufficient balance."))) as client:
        response = client.post(
            "/api/scans", json={"path": str(FIXTURES / "leaky_emg"), "explain": True}
        )
        scan = _wait(client, response.json()["id"])
        report = client.get(f"/api/scans/{scan['id']}/report").json()

    assert scan["status"] == "done"
    assert report["findings"]
    assert any("Insufficient balance" in error for error in report["check_errors"])


def test_unknown_folder_is_rejected(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/scans", json={"path": str(tmp_path / "missing")})

    assert response.status_code == 400


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def test_upload_a_zip(client: TestClient) -> None:
    files = {
        "myproj/train.py": 'DATA = "C:/Users/me/data"\n',
        "myproj/.venv/lib/x.py": "print(1)\n",
    }
    response = client.post(
        "/api/scans/upload", files={"file": ("myproj.zip", _zip(files), "application/zip")}
    )
    assert response.status_code == 202
    scan = _wait(client, response.json()["id"])

    report = client.get(f"/api/scans/{scan['id']}/report").json()
    assert scan["name"] == "myproj"
    assert report["files_scanned"] == ["train.py"]
    assert any(f["check_id"] == "repro.hardcoded-path" for f in report["findings"])


@pytest.mark.parametrize("bad_name", ["../escape.py", "/etc/passwd", "C:/Windows/x.py"])
def test_zip_with_unsafe_paths_is_rejected(client: TestClient, bad_name: str) -> None:
    response = client.post(
        "/api/scans/upload", files={"file": ("bad.zip", _zip({bad_name: "x"}), "application/zip")}
    )

    assert response.status_code == 400
    assert "Unsafe path" in response.json()["detail"]


def test_not_a_zip_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/scans/upload", files={"file": ("x.zip", b"not a zip", "application/zip")}
    )

    assert response.status_code == 400


def test_history_report_conflict_and_delete(client: TestClient) -> None:
    first = client.post("/api/scans", json={"path": str(FIXTURES / "clean_project")}).json()
    _wait(client, first["id"])

    assert [s["id"] for s in client.get("/api/scans").json()] == [first["id"]]
    assert client.get("/api/scans/nope").status_code == 404
    assert client.delete(f"/api/scans/{first['id']}").status_code == 204
    assert client.get(f"/api/scans/{first['id']}").status_code == 404


def test_serves_the_web_app_with_client_side_routes(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "assets" / "main.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    app = create_app(data_dir=tmp_path / "data", web_dist=dist)

    with TestClient(app) as client:
        assert client.get("/").text == "<html>app</html>"
        assert client.get("/scans/abc123").text == "<html>app</html>"
        assert client.get("/assets/main.js").text == "console.log(1)"
        assert client.get("/favicon.svg").text == "<svg/>"
        assert "outside" not in client.get("/../secret.txt").text
        assert client.get("/api/nope").status_code == 404
        assert client.get("/api/health").json()["status"] == "ok"


def test_export_in_every_format(client: TestClient) -> None:
    started = client.post("/api/scans", json={"path": str(FIXTURES / "leaky_emg")}).json()
    url = f"/api/scans/{_wait(client, started['id'])['id']}/export"

    md = client.get(url)
    csv_text = client.get(url, params={"format": "csv"})
    as_json = client.get(url, params={"format": "json"})

    assert md.status_code == 200
    assert md.text.startswith("# Shipshape report: leaky_emg")
    assert 'filename="leaky_emg-shipshape.md"' in md.headers["content-disposition"]
    assert csv_text.text.splitlines()[0].startswith("finding,severity,dimension")
    assert as_json.json()["project_name"] == "leaky_emg"
    assert client.get(url, params={"format": "pdf"}).status_code == 422
    assert client.get("/api/scans/nope/export").status_code == 404
