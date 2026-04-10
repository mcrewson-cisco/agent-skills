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
SCRIPT = ROOT / "scripts" / "chim.py"


def load_module():
    spec = importlib.util.spec_from_file_location("chim_skill", SCRIPT)
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


class ChimSkillTest(unittest.TestCase):
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
            ["auth-runtime", "resolve", "chim", "--no-refresh", "--format", "value"],
            stderr="cached CHIM API key was not found in Keychain\n",
        )
        refresh_result = subprocess.CompletedProcess(
            ["auth-runtime", "resolve", "chim", "--format", "value"],
            0,
            stdout="chim-token\n",
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(
                module.subprocess,
                "run",
                side_effect=[no_refresh_error, refresh_result],
            ) as run:
                token = module.resolve_api_key()

        self.assertEqual(token, "chim-token")
        self.assertEqual(run.call_count, 2)
        first_args = run.call_args_list[0].args[0]
        second_args = run.call_args_list[1].args[0]
        self.assertIn("--no-refresh", first_args)
        self.assertNotIn("--no-refresh", second_args)

    def test_resolve_api_key_stops_early_on_sandbox_auth_block(self) -> None:
        module = load_module()
        sandbox_error = subprocess.CalledProcessError(
            5,
            ["auth-runtime", "resolve", "chim", "--no-refresh", "--format", "value"],
            stderr=json.dumps(
                {
                    "code": "cache_unavailable",
                    "service": "chim",
                    "message": "macOS Keychain access appears unavailable from this environment",
                }
            ),
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(
                module.subprocess,
                "run",
                side_effect=[sandbox_error],
            ) as run:
                with self.assertRaises(module.ChimAuthError) as excinfo:
                    module.resolve_api_key()

        self.assertIn("rerun this same CHIM command with narrow escalation", str(excinfo.exception))
        self.assertEqual(run.call_count, 1)

    def test_run_auth_runtime_resolve_honors_auth_runtime_bin_override(self) -> None:
        module = load_module()
        refresh_result = subprocess.CompletedProcess(
            ["auth-runtime", "resolve", "chim", "--no-refresh", "--format", "value"],
            0,
            stdout="chim-token\n",
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

        self.assertEqual(token, "chim-token")
        self.assertEqual(run.call_args.args[0][0], "/opt/homebrew/bin/auth-runtime")

    def test_request_retries_after_rate_limit(self) -> None:
        module = load_module()
        service_map = {"PTEST01": {"name": "Test Service", "team": "RouteX"}}
        client = module.ChimClient(
            api_key="chim-token",
            service_map=service_map,
            base_url="https://api.chim.test/api/v1",
        )
        rate_limited = urllib.error.HTTPError(
            "https://api.chim.test/api/v1/outages/",
            429,
            "Too Many Requests",
            {"Retry-After": "2"},
            io.BytesIO(b'{"error":"rate_limited"}'),
        )
        self.addCleanup(rate_limited.close)

        with mock.patch.object(
            module.urllib.request,
            "urlopen",
            side_effect=[rate_limited, FakeResponse({"results": []})],
        ) as urlopen:
            with mock.patch.object(module.time, "sleep") as sleep:
                payload = client.request_json("GET", "/outages/")

        self.assertEqual(payload, {"results": []})
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
                "outage_id": "OTG-1",
                "title": "Flappy Alert",
                "severity": 2,
                "status": "resolved",
                "created_at": "2026-04-01T10:00:00Z",
                "updated_at": "2026-04-01T10:30:00Z",
                "external_customer_impact": True,
                "internal_customer_impact": False,
                "pagerduty": {"service": {"id": "PTEST01", "summary": "Svc 1"}},
            },
            {
                "outage_id": "OTG-2",
                "title": "Flappy Alert",
                "severity": 2,
                "status": "resolved",
                "created_at": "2026-04-02T10:00:00Z",
                "updated_at": "2026-04-02T10:15:00Z",
                "external_customer_impact": False,
                "internal_customer_impact": True,
                "pagerduty": {"service": {"id": "PTEST01", "summary": "Svc 1"}},
            },
            {
                "outage_id": "OTG-3",
                "title": "Different Alert",
                "severity": 4,
                "status": "open",
                "created_at": "2026-04-03T11:00:00Z",
                "updated_at": "2026-04-03T11:00:00Z",
                "external_customer_impact": False,
                "internal_customer_impact": False,
                "pagerduty": {"service": {"id": "PTEST02", "summary": "Svc 2"}},
            },
        ]

        analysis = module.build_analysis(
            incidents=incidents,
            service_map=service_map,
            since="2026-04-01",
            until="2026-04-03",
        )

        self.assertEqual(analysis["total_incidents"], 3)
        self.assertEqual(analysis["by_team"]["RouteX"], 2)
        self.assertEqual(analysis["by_team"]["Athena"], 1)
        self.assertEqual(analysis["noisy_incidents"], {"Flappy Alert": 2})
        self.assertEqual(analysis["customer_impact"]["external"], 1)
        self.assertEqual(analysis["customer_impact"]["internal"], 1)

    def test_filter_changes_by_services_keeps_only_selected_service_ids(self) -> None:
        module = load_module()
        changes = [
            {"change_id": "CR-1", "service": {"id": "PTEST01", "name": "Svc 1"}},
            {"change_id": "CR-2", "service": {"id": "PTEST02", "name": "Svc 2"}},
            {"change_id": "CR-3", "service": {"id": "PTEST03", "name": "Svc 3"}},
        ]

        filtered = module.filter_changes_by_services(changes, ["PTEST02"])

        self.assertEqual([change["change_id"] for change in filtered], ["CR-2"])


if __name__ == "__main__":
    unittest.main()
