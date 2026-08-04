from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from sqlite3 import connect
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.services.trip_compiler import compile_travel_intent


RESTART_TEXT = (
    "周末去杭州玩两天，想去西湖和灵隐寺。"
    "周六下午两点预约了中国茶叶博物馆。周日晚上六点前要到杭州东站。"
)


class PlanningRunProcessRestartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "restart.sqlite3"
        self.port = _free_port()
        self.process: subprocess.Popen[bytes] | None = None

    def tearDown(self) -> None:
        self._stop_server()
        self.temp_dir.cleanup()

    def test_run_and_capability_survive_real_fastapi_process_restart(self) -> None:
        self._start_server()
        intent = compile_travel_intent(RESTART_TEXT).intent.model_dump(mode="json")
        created, headers = self._request("POST", "/trip-compiler/planning-runs", {"intent": intent})
        self.assertEqual(created["status"], "generated")
        planning_cookie = _cookie_value(_header_value(headers, "set-cookie"), "planning_run_capability")
        self.assertIsNotNone(planning_cookie)
        run_id = created["planning_run_id"]
        before_restart = self._request_json("GET", f"/trip-compiler/planning-runs/{run_id}", cookie=planning_cookie)

        self._stop_server()
        self._start_server()
        restored = self._request_json("GET", f"/trip-compiler/planning-runs/{run_id}", cookie=planning_cookie)
        self.assertEqual(
            [(item["id"], item["candidate_hash"]) for item in before_restart["candidates"]],
            [(item["id"], item["candidate_hash"]) for item in restored["candidates"]],
        )

        candidate = restored["candidates"][0]
        selected, _ = self._request(
            "POST",
            f"/trip-compiler/planning-runs/{run_id}/candidates/{candidate['id']}/select",
            {"candidate_hash": candidate["candidate_hash"], "intent_digest": restored["intent_digest"]},
            cookie=planning_cookie,
            extra_headers={"Origin": "http://127.0.0.1:3000", "X-Idempotency-Key": "process-restart-selection"},
        )
        self.assertEqual(selected["current_revision"]["revision_number"], 1)
        with connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trip_revisions").fetchone()[0], 1)

    def _start_server(self) -> None:
        environment = os.environ | {
            "TRIP_STORE_MODE": "sqlite",
            "TRIP_STORE_PATH": str(self.database_path),
            "TRIP_ALLOWED_ORIGINS": "http://127.0.0.1:3000",
            "CORS_ALLOW_ORIGINS": "http://127.0.0.1:3000",
        }
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{self.port}/docs", timeout=0.5):
                    return
            except URLError:
                time.sleep(0.05)
        self.fail("FastAPI test process did not become ready")

    def _stop_server(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None

    def _request_json(self, method: str, path: str, *, cookie: str) -> dict:
        body, _ = self._request(method, path, None, cookie=cookie)
        return body

    def _request(self, method: str, path: str, payload: dict | None, *, cookie: str | None = None, extra_headers: dict[str, str] | None = None) -> tuple[dict, dict[str, str]]:
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = f"planning_run_capability={cookie}"
        headers.update(extra_headers or {})
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers=headers,
            method=method,
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read()), dict(response.headers.items())


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _cookie_value(header: str, cookie_name: str) -> str | None:
    prefix = f"{cookie_name}="
    for part in header.split(";"):
        value = part.strip()
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return None


def _header_value(headers: dict[str, str], name: str) -> str:
    for header_name, value in headers.items():
        if header_name.lower() == name.lower():
            return value
    raise KeyError(name)
