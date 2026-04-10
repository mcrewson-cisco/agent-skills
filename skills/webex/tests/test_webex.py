from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import subprocess
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "webex.py"


def load_module():
    spec = importlib.util.spec_from_file_location("webex_skill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class WebexSkillTest(unittest.TestCase):
    def test_auth_check_falls_back_to_room_probe_on_scope_error(self) -> None:
        module = load_module()
        calls: list[str] = []

        class FakeClient:
            def api(self, method: str, path: str, **kwargs):
                calls.append(path)
                if path == "/people/me":
                    raise module.WebexApiError(
                        "Webex API error 403 on GET /people/me: missing scope"
                    )
                if path == "/rooms":
                    return {"items": [{"id": "room-1"}]}
                raise AssertionError(path)

        with mock.patch.object(module, "build_client", return_value=FakeClient()):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                module.cmd_auth_check(argparse.Namespace(pretty=True))

        payload = json.loads(stdout.getvalue())
        self.assertEqual(calls, ["/people/me", "/rooms"])
        self.assertEqual(payload["status"], "authenticated")
        self.assertTrue(payload["verified"])

    def test_auth_check_does_not_hide_network_errors(self) -> None:
        module = load_module()
        calls: list[str] = []

        class FakeClient:
            def api(self, method: str, path: str, **kwargs):
                calls.append(path)
                raise module.WebexApiError(
                    "Webex API request failed on GET /people/me: [Errno 8] nodename nor servname provided, or not known"
                )

        with mock.patch.object(module, "build_client", return_value=FakeClient()):
            with self.assertRaises(module.WebexApiError):
                module.cmd_auth_check(argparse.Namespace(pretty=True))

        self.assertEqual(calls, ["/people/me"])

    def test_resolve_access_token_falls_back_to_refresh_after_no_refresh_miss(self) -> None:
        module = load_module()
        no_refresh_error = subprocess.CalledProcessError(
            1,
            ["auth-runtime", "resolve", "webex", "--no-refresh", "--format", "value"],
            stderr="no Webex token cache or PAT cache is configured\n",
        )
        refresh_result = subprocess.CompletedProcess(
            ["auth-runtime", "resolve", "webex", "--format", "value"],
            0,
            stdout="webex-token\n",
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(
                module.subprocess,
                "run",
                side_effect=[no_refresh_error, refresh_result],
            ) as run:
                token = module.resolve_access_token()

        self.assertEqual(token, "webex-token")
        self.assertEqual(run.call_count, 2)
        self.assertIn("--no-refresh", run.call_args_list[0].args[0])
        self.assertNotIn("--no-refresh", run.call_args_list[1].args[0])

    def test_resolve_access_token_stops_early_on_sandbox_auth_block(self) -> None:
        module = load_module()
        sandbox_error = subprocess.CalledProcessError(
            5,
            ["auth-runtime", "resolve", "webex", "--no-refresh", "--format", "value"],
            stderr=json.dumps(
                {
                    "code": "desktop_app_unreachable",
                    "service": "webex",
                    "message": "1Password desktop app is not reachable from this environment",
                }
            ),
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(module.subprocess, "run", side_effect=[sandbox_error]) as run:
                with self.assertRaises(module.WebexAuthError) as excinfo:
                    module.resolve_access_token()

        self.assertIn("rerun this same Webex command with narrow escalation", str(excinfo.exception))
        self.assertEqual(run.call_count, 1)

    def test_run_auth_runtime_resolve_honors_auth_runtime_bin_override(self) -> None:
        module = load_module()
        refresh_result = subprocess.CompletedProcess(
            ["auth-runtime", "resolve", "webex", "--no-refresh", "--format", "value"],
            0,
            stdout="webex-token\n",
        )

        with mock.patch.dict(
            os.environ,
            {"AUTH_RUNTIME_BIN": "/opt/homebrew/bin/auth-runtime"},
            clear=True,
        ):
            with mock.patch.object(module.subprocess, "run", return_value=refresh_result) as run:
                token = module.run_auth_runtime_resolve(no_refresh=True)

        self.assertEqual(token, "webex-token")
        self.assertEqual(run.call_args.args[0][0], "/opt/homebrew/bin/auth-runtime")

    def test_request_json_retries_after_rate_limit(self) -> None:
        module = load_module()
        client = module.WebexClient(access_token="webex-token", base_url="https://webexapis.example/v1")
        rate_limited = urllib.error.HTTPError(
            "https://webexapis.example/v1/rooms",
            429,
            "Too Many Requests",
            {"Retry-After": "3"},
            io.BytesIO(b'{"message":"rate limited"}'),
        )
        self.addCleanup(rate_limited.close)

        with mock.patch.object(
            module.urllib.request,
            "urlopen",
            side_effect=[rate_limited, FakeResponse({"items": []})],
        ) as urlopen:
            with mock.patch.object(module.time, "sleep") as sleep:
                payload = client.request_json("GET", "/rooms")

        self.assertEqual(payload, {"items": []})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(3)

    def test_send_preview_does_not_post_without_confirm(self) -> None:
        module = load_module()
        args = argparse.Namespace(
            room_id="room-123",
            person_email=None,
            person_id=None,
            text="hello world",
            markdown=None,
            parent_id=None,
            confirm=False,
        )

        with mock.patch.object(module, "resolve_access_token", return_value="webex-token"):
            with mock.patch.object(module.WebexClient, "api", side_effect=AssertionError("should not post")):
                with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                    with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                        module.cmd_send(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "preview")
        self.assertIn("Re-run with --confirm", stderr.getvalue())

    def test_summarize_orders_messages_chronologically(self) -> None:
        module = load_module()
        room_payload = {"title": "NATaaS Room"}
        messages_payload = {
            "items": [
                {
                    "created": "2026-04-03T18:00:00.000Z",
                    "personEmail": "two@example.com",
                    "personDisplayName": "Two",
                    "text": "second",
                },
                {
                    "created": "2026-04-03T17:00:00.000Z",
                    "personEmail": "one@example.com",
                    "personDisplayName": "One",
                    "text": "first",
                },
            ]
        }

        with mock.patch.object(module, "resolve_access_token", return_value="webex-token"):
            with mock.patch.object(
                module.WebexClient,
                "api",
                side_effect=[room_payload, messages_payload],
            ):
                with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                    module.cmd_summarize(argparse.Namespace(room_id="room-123", max=10))

        output = stdout.getvalue().strip().splitlines()
        self.assertIn("[2026-04-03 17:00:00] One <one@example.com>: first", output)
        self.assertIn("[2026-04-03 18:00:00] Two <two@example.com>: second", output)
        first_index = output.index("[2026-04-03 17:00:00] One <one@example.com>: first")
        second_index = output.index("[2026-04-03 18:00:00] Two <two@example.com>: second")
        self.assertLess(first_index, second_index)

    def test_find_person_messages_scans_active_rooms_and_filters_by_window(self) -> None:
        module = load_module()

        class FakeClient:
            def paginate(self, path: str, *, params=None, max_items=200):
                self.paginate_args = (path, params, max_items)
                return [
                    {
                        "id": "room-active",
                        "title": "RouteX Internal",
                        "type": "group",
                        "lastActivity": "2026-04-03T19:00:00Z",
                    },
                    {
                        "id": "room-old",
                        "title": "Old Room",
                        "type": "group",
                        "lastActivity": "2026-04-02T19:00:00Z",
                    },
                ]

            def api(self, method: str, path: str, *, params=None, body=None):
                self.api_args = getattr(self, "api_args", [])
                self.api_args.append((method, path, params))
                if params and params.get("roomId") == "room-active":
                    return {
                        "items": [
                            {
                                "created": "2026-04-03T18:30:00Z",
                                "personEmail": "lmaheshw@cisco.com",
                                "text": "Can you review this today?",
                                "parentId": "parent-1",
                            },
                            {
                                "created": "2026-04-03T06:30:00Z",
                                "personEmail": "lmaheshw@cisco.com",
                                "text": "older message",
                            },
                        ]
                    }
                raise AssertionError(params)

        fake_client = FakeClient()
        args = argparse.Namespace(
            pretty=True,
            email="lmaheshw@cisco.com",
            since="2026-04-03T07:00:00Z",
            until=None,
            max_rooms=100,
            max_messages=100,
            room_type=None,
        )

        with mock.patch.object(module, "build_client", return_value=fake_client):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                module.cmd_find_person_messages(args)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["target_email"], "lmaheshw@cisco.com")
        self.assertEqual(payload["active_rooms_considered"], 1)
        self.assertEqual(payload["rooms_fetched"], 1)
        self.assertEqual(len(payload["hits"]), 1)
        self.assertEqual(payload["hits"][0]["roomTitle"], "RouteX Internal")
        self.assertEqual(payload["hits"][0]["text"], "Can you review this today?")


if __name__ == "__main__":
    unittest.main()
