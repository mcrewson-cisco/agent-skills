from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "pagerduty.py"


def load_module():
    spec = importlib.util.spec_from_file_location("pagerduty_skill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class PagerDutySkillTest(unittest.TestCase):
    def test_load_service_map_reads_json_file(self) -> None:
        module = load_module()
        payload = {
            "PTEST01": {
                "name": "Test Service",
                "team": "RouteX",
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            service_map_path = Path(temp_dir) / "services.json"
            service_map_path.write_text(json.dumps(payload), encoding="utf-8")

            result = module.load_service_map(service_map_path)

        self.assertEqual(result, payload)

    def test_resolve_api_key_falls_back_to_refresh_after_no_refresh_miss(self) -> None:
        module = load_module()
        no_refresh_error = subprocess.CalledProcessError(
            1,
            ["auth-runtime", "resolve", "pagerduty", "--no-refresh", "--format", "value"],
            stderr="cached PagerDuty API key was not found in Keychain\n",
        )
        refresh_result = subprocess.CompletedProcess(
            ["auth-runtime", "resolve", "pagerduty", "--format", "value"],
            0,
            stdout="pd-token\n",
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(
                module.subprocess,
                "run",
                side_effect=[no_refresh_error, refresh_result],
            ) as run:
                token = module.resolve_api_key()

        self.assertEqual(token, "pd-token")
        self.assertEqual(run.call_count, 2)
        first_args = run.call_args_list[0].args[0]
        second_args = run.call_args_list[1].args[0]
        self.assertIn("--no-refresh", first_args)
        self.assertNotIn("--no-refresh", second_args)

    def test_run_auth_runtime_resolve_honors_auth_runtime_bin_override(self) -> None:
        module = load_module()
        refresh_result = subprocess.CompletedProcess(
            ["auth-runtime", "resolve", "pagerduty", "--no-refresh", "--format", "value"],
            0,
            stdout="pd-token\n",
        )

        with mock.patch.dict(
            os.environ,
            {"AUTH_RUNTIME_BIN": "/opt/homebrew/bin/auth-runtime"},
            clear=True,
        ):
            with mock.patch.object(
                module.subprocess,
                "run",
                return_value=refresh_result,
            ) as run:
                token = module.run_auth_runtime_resolve(no_refresh=True)

        self.assertEqual(token, "pd-token")
        self.assertEqual(run.call_args.args[0][0], "/opt/homebrew/bin/auth-runtime")

    def test_request_retries_after_rate_limit(self) -> None:
        module = load_module()
        service_map = {"PTEST01": {"name": "Test Service", "team": "RouteX"}}
        client = module.PagerDutyClient(
            api_key="pd-token",
            service_map=service_map,
            base_url="https://api.pagerduty.test",
        )
        rate_limited = urllib.error.HTTPError(
            "https://api.pagerduty.test/services",
            429,
            "Too Many Requests",
            {"Retry-After": "2"},
            io.BytesIO(b'{"error":"rate_limited"}'),
        )
        self.addCleanup(rate_limited.close)

        with mock.patch.object(
            module.urllib.request,
            "urlopen",
            side_effect=[rate_limited, FakeResponse({"services": []})],
        ) as urlopen:
            with mock.patch.object(module.time, "sleep") as sleep:
                payload = client.request_json("GET", "/services")

        self.assertEqual(payload, {"services": []})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_build_analysis_reports_team_counts_and_noisy_titles(self) -> None:
        module = load_module()
        service_map = {
            "PTEST01": {"name": "Svc 1", "team": "RouteX"},
            "PTEST02": {"name": "Svc 2", "team": "Athena"},
        }
        incidents = [
            {
                "id": "A",
                "incident_number": 1,
                "title": "Flappy Alert",
                "status": "resolved",
                "urgency": "high",
                "created_at": "2026-04-01T10:00:00Z",
                "last_status_change_at": "2026-04-01T10:30:00Z",
                "service": {"id": "PTEST01", "summary": "Svc 1"},
            },
            {
                "id": "B",
                "incident_number": 2,
                "title": "Flappy Alert",
                "status": "resolved",
                "urgency": "high",
                "created_at": "2026-04-02T10:00:00Z",
                "last_status_change_at": "2026-04-02T10:15:00Z",
                "service": {"id": "PTEST01", "summary": "Svc 1"},
            },
            {
                "id": "C",
                "incident_number": 3,
                "title": "Flappy Alert",
                "status": "triggered",
                "urgency": "low",
                "created_at": "2026-04-03T11:00:00Z",
                "last_status_change_at": "2026-04-03T11:00:00Z",
                "service": {"id": "PTEST02", "summary": "Svc 2"},
            },
            {
                "id": "D",
                "incident_number": 4,
                "title": "Different Alert",
                "status": "resolved",
                "urgency": "low",
                "created_at": "2026-04-03T12:00:00Z",
                "last_status_change_at": "2026-04-03T13:00:00Z",
                "service": {"id": "PTEST02", "summary": "Svc 2"},
            },
        ]

        analysis = module.build_analysis(
            incidents=incidents,
            service_map=service_map,
            since="2026-04-01",
            until="2026-04-03",
        )

        self.assertEqual(analysis["total_incidents"], 4)
        self.assertEqual(analysis["by_team"]["RouteX"], 2)
        self.assertEqual(analysis["by_team"]["Athena"], 2)
        self.assertEqual(analysis["noisy_incidents"], {"Flappy Alert": 3})
        self.assertEqual(analysis["mttr"]["sample_size"], 3)


if __name__ == "__main__":
    unittest.main()
