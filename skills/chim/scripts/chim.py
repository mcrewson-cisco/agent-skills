#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_SERVICE_MAP_PATH = SKILL_DIR / "data" / "services.json"
DEFAULT_BASE_URL = os.environ.get("CHIM_API_URL", "https://api.chim.umbrella.com/api/v1")
SEVERITY_LABELS = {
    "1": "Catastrophic",
    "2": "Critical",
    "3": "Significant",
    "4": "Impaired",
}


class ChimSkillError(RuntimeError):
    pass


class ServiceMapError(ChimSkillError):
    pass


class ChimAuthError(ChimSkillError):
    pass


class ChimApiError(ChimSkillError):
    pass


def parse_auth_runtime_error(output: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def is_sandbox_auth_block(record: dict[str, Any] | None) -> bool:
    if not record:
        return False
    return str(record.get("code", "")).strip() in {
        "cache_unavailable",
        "desktop_app_unreachable",
    }


def load_service_map(path: Path | str = DEFAULT_SERVICE_MAP_PATH) -> dict[str, dict[str, str]]:
    service_map_path = Path(path)
    try:
        raw = json.loads(service_map_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ServiceMapError(f"CHIM service map not found at {service_map_path}") from error
    except json.JSONDecodeError as error:
        raise ServiceMapError(
            f"CHIM service map at {service_map_path} is not valid JSON: {error}"
        ) from error

    if not isinstance(raw, dict):
        raise ServiceMapError(
            f"CHIM service map at {service_map_path} must be a JSON object keyed by service ID"
        )

    normalized: dict[str, dict[str, str]] = {}
    for service_id, metadata in raw.items():
        if not isinstance(service_id, str) or not service_id.strip():
            raise ServiceMapError("CHIM service IDs must be non-empty strings")
        if not isinstance(metadata, dict):
            raise ServiceMapError(
                f"CHIM service {service_id} must map to an object with at least name/team"
            )
        normalized[service_id.strip()] = {
            "name": str(metadata.get("name", service_id)).strip() or service_id,
            "team": str(metadata.get("team", "Unknown")).strip() or "Unknown",
        }
    return normalized


def parse_service_ids(
    services_arg: str | None,
    service_map: dict[str, dict[str, str]],
) -> list[str]:
    if not services_arg:
        return list(service_map.keys())
    return [service_id.strip() for service_id in services_arg.split(",") if service_id.strip()]


def filter_incidents_by_services(
    incidents: list[dict[str, Any]],
    allowed_service_ids: list[str],
) -> list[dict[str, Any]]:
    allowed = set(allowed_service_ids)
    if not allowed:
        return incidents
    return [
        incident
        for incident in incidents
        if incident_service_id(incident) in allowed
    ]


def filter_changes_by_services(
    changes: list[dict[str, Any]],
    allowed_service_ids: list[str],
) -> list[dict[str, Any]]:
    allowed = set(allowed_service_ids)
    if not allowed:
        return changes
    return [
        change
        for change in changes
        if change_service_id(change) in allowed
    ]


def service_name_for(service_id: str | None, service_map: dict[str, dict[str, str]]) -> str:
    if not service_id:
        return "Unknown"
    return service_map.get(service_id, {}).get("name", service_id)


def team_for(service_id: str | None, service_map: dict[str, dict[str, str]]) -> str:
    if not service_id:
        return "Unknown"
    return service_map.get(service_id, {}).get("team", "Unknown")


def run_auth_runtime_resolve(no_refresh: bool) -> str:
    auth_runtime_bin = os.environ.get("AUTH_RUNTIME_BIN", "auth-runtime")
    command = [auth_runtime_bin, "resolve", "chim"]
    if no_refresh:
        command.append("--no-refresh")
    command.extend(["--format", "value"])
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def resolve_api_key(env_var: str = "CHIM_API_KEY", allow_refresh: bool = True) -> str:
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return env_value

    attempts = [True] + ([] if not allow_refresh else [False])
    errors: list[str] = []
    for no_refresh in attempts:
        command_text = "auth-runtime resolve chim --no-refresh --format value"
        if not no_refresh:
            command_text = "auth-runtime resolve chim --format value"
        try:
            token = run_auth_runtime_resolve(no_refresh=no_refresh)
        except FileNotFoundError as error:
            raise ChimAuthError(
                "Could not resolve the CHIM API key because `auth-runtime` was not found on PATH. "
                "Install or upgrade it with `uv tool install --upgrade "
                "git+ssh://git@github.com/mcrewson-cisco/auth_runtime.git`."
            ) from error
        except subprocess.CalledProcessError as error:
            output = (error.stderr or error.stdout or "").strip()
            record = parse_auth_runtime_error(output)
            if is_sandbox_auth_block(record):
                message = str(record.get("message") or "local auth path unavailable").strip()
                raise ChimAuthError(
                    "CHIM credential resolution is blocked in this session because auth-runtime cannot access "
                    f"the local cache or desktop auth path ({message}). This is common in sandboxed Codex runs. "
                    "Run `auth-runtime doctor chim --format json`, then rerun this same CHIM command with narrow escalation."
                ) from error
            errors.append(
                f"`{command_text}` failed: {output or f'exited with status {error.returncode}'}"
            )
            continue
        if token:
            return token
        errors.append(f"`{command_text}` returned an empty token")

    hint = "Run `auth-runtime doctor chim --format json`, then retry."
    raise ChimAuthError(
        "Could not resolve the CHIM API key. "
        f"{hint} Original output: {' | '.join(errors)}"
    )


class ChimClient:
    def __init__(
        self,
        api_key: str,
        service_map: dict[str, dict[str, str]],
        base_url: str = DEFAULT_BASE_URL,
        max_http_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.service_map = service_map
        self.base_url = base_url.rstrip("/")
        self.max_http_retries = max_http_retries

    def request_json(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)

        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        data = json.dumps(body).encode("utf-8") if body else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)

        for attempt in range(self.max_http_retries + 1):
            try:
                with urllib.request.urlopen(request) as response:
                    payload = response.read().decode("utf-8")
                    return json.loads(payload) if payload else {}
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8") if error.fp else ""
                if error.code == 429 and attempt < self.max_http_retries:
                    retry_after = 1
                    if error.headers and error.headers.get("Retry-After"):
                        try:
                            retry_after = int(float(error.headers.get("Retry-After", "1")))
                        except ValueError:
                            retry_after = 1
                    time.sleep(retry_after)
                    continue
                raise ChimApiError(
                    f"CHIM API error {error.code} on {method} {path}: {detail or error.reason}"
                ) from error
            except urllib.error.URLError as error:
                raise ChimApiError(
                    f"CHIM API request failed on {method} {path}: {error.reason}"
                ) from error

        raise ChimApiError(f"CHIM API request exhausted retries on {method} {path}")

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_pages: int = 100,
        max_items: int = 5000,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        base_params = dict(params or {})
        while page <= max_pages and len(items) < max_items:
            page_params = dict(base_params)
            page_params["page"] = page
            payload = self.request_json("GET", path, params=page_params)
            page_items = payload.get("results", [])
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(page_items)
            pages = payload.get("pages", {})
            next_page = pages.get("next") if isinstance(pages, dict) else None
            if next_page in (None, "", 0):
                break
            try:
                page = int(next_page)
            except (TypeError, ValueError):
                break
        return items[:max_items]


def incident_service_id(incident: dict[str, Any]) -> str | None:
    pagerduty = incident.get("pagerduty")
    if isinstance(pagerduty, dict):
        service = pagerduty.get("service")
        if isinstance(service, dict):
            service_id = service.get("id")
            if isinstance(service_id, str) and service_id.strip():
                return service_id.strip()
    return None


def incident_service_name(
    incident: dict[str, Any],
    service_map: dict[str, dict[str, str]],
) -> str:
    pagerduty = incident.get("pagerduty")
    if isinstance(pagerduty, dict):
        service = pagerduty.get("service")
        if isinstance(service, dict):
            summary = service.get("summary")
            if isinstance(summary, str) and summary.strip():
                return summary.strip()
    return service_name_for(incident_service_id(incident), service_map)


def change_service_id(change: dict[str, Any]) -> str | None:
    service = change.get("service")
    if isinstance(service, dict):
        service_id = service.get("id")
        if isinstance(service_id, str) and service_id.strip():
            return service_id.strip()
    return None


def change_service_name(
    change: dict[str, Any],
    service_map: dict[str, dict[str, str]],
) -> str:
    service = change.get("service")
    if isinstance(service, dict):
        name = service.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return service_name_for(change_service_id(change), service_map)


def format_severity_key(value: Any) -> str:
    normalized = str(value).strip()
    label = SEVERITY_LABELS.get(normalized)
    if label:
        return f"sev{normalized} ({label})"
    return normalized or "unknown"


def incident_summary_row(
    incident: dict[str, Any],
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    service_id = incident_service_id(incident)
    return {
        "outage_id": incident.get("outage_id"),
        "title": incident.get("title"),
        "severity": incident.get("severity"),
        "status": incident.get("status"),
        "created_at": incident.get("created_at"),
        "updated_at": incident.get("updated_at"),
        "external_customer_impact": bool(incident.get("external_customer_impact")),
        "internal_customer_impact": bool(incident.get("internal_customer_impact")),
        "service": incident_service_name(incident, service_map),
        "team": team_for(service_id, service_map),
    }


def change_summary_row(
    change: dict[str, Any],
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    service_id = change_service_id(change)
    return {
        "change_id": change.get("change_id"),
        "title": change.get("title"),
        "type": change.get("type"),
        "status": change.get("status"),
        "environment": change.get("environment"),
        "created_at": change.get("created_at"),
        "updated_at": change.get("updated_at"),
        "service": change_service_name(change, service_map),
        "team": team_for(service_id, service_map),
        "reporter": change.get("reporter"),
    }


def build_incident_params(
    args: argparse.Namespace,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    service_ids = parse_service_ids(args.services, service_map)
    if service_ids:
        params["services"] = ",".join(service_ids)
    if getattr(args, "created_after", None):
        params["created_after"] = args.created_after
    if getattr(args, "created_before", None):
        params["created_before"] = args.created_before
    if getattr(args, "severity", None):
        params["severity"] = args.severity
    if getattr(args, "status", None):
        params["status"] = args.status
    if getattr(args, "environment", None):
        params["environment"] = args.environment
    if getattr(args, "search", None):
        params["search"] = args.search
    if getattr(args, "external_impact", False):
        params["external_customer_impact"] = "true"
    if getattr(args, "internal_impact", False):
        params["internal_customer_impact"] = "true"
    return params


def build_change_params(
    args: argparse.Namespace,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    service_ids = parse_service_ids(args.services, service_map)
    if service_ids:
        params["service"] = ",".join(service_ids)
    if getattr(args, "created_after", None):
        params["created_after"] = args.created_after
    if getattr(args, "created_before", None):
        params["created_before"] = args.created_before
    if getattr(args, "change_type", None):
        params["type"] = args.change_type
    if getattr(args, "status", None):
        params["status"] = args.status
    return params


def build_analysis(
    incidents: list[dict[str, Any]],
    service_map: dict[str, dict[str, str]],
    since: str,
    until: str,
) -> dict[str, Any]:
    by_severity: Counter[str] = Counter()
    by_team: Counter[str] = Counter()
    by_service: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_month: Counter[str] = Counter()
    severity_by_team: dict[str, Counter[str]] = defaultdict(Counter)
    incidents_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    title_counts: Counter[str] = Counter()
    external_count = 0
    internal_count = 0

    for incident in incidents:
        summary = incident_summary_row(incident, service_map)
        severity_key = format_severity_key(summary["severity"])
        team = str(summary["team"])
        service = str(summary["service"])
        status = str(summary["status"] or "unknown")
        created_at = str(summary["created_at"] or "")

        by_severity[severity_key] += 1
        by_team[team] += 1
        by_service[service] += 1
        by_status[status] += 1
        severity_by_team[team][severity_key] += 1
        if len(created_at) >= 7:
            by_month[created_at[:7]] += 1
        if summary["external_customer_impact"]:
            external_count += 1
        if summary["internal_customer_impact"]:
            internal_count += 1

        title = str(summary["title"] or "").strip()
        if title:
            title_counts[title] += 1

        incidents_by_team[team].append(summary)

    noisy_incidents = {
        title: count
        for title, count in sorted(
            title_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        if count > 1
    }

    notable_incidents = sorted(
        [
            incident_summary_row(incident, service_map)
            for incident in incidents
            if str(incident.get("severity", "")) in {"1", "2"}
            or bool(incident.get("external_customer_impact"))
        ],
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )[:10]

    return {
        "period": {
            "from": since,
            "to": until,
        },
        "total_incidents": len(incidents),
        "by_severity": dict(by_severity),
        "by_team": dict(by_team.most_common()),
        "by_service": dict(by_service.most_common()),
        "by_status": dict(by_status.most_common()),
        "by_month": dict(sorted(by_month.items())),
        "customer_impact": {
            "external": external_count,
            "internal": internal_count,
        },
        "severity_by_team": {
            team: dict(counts)
            for team, counts in severity_by_team.items()
        },
        "noisy_incidents": noisy_incidents,
        "notable_incidents": notable_incidents,
        "incidents_by_team": {
            team: sorted(
                rows,
                key=lambda item: str(item.get("created_at") or ""),
                reverse=True,
            )
            for team, rows in incidents_by_team.items()
        },
    }


def print_json(data: Any, pretty: bool = False) -> None:
    if pretty:
        print(json.dumps(data, indent=2, sort_keys=True, default=str))
        return
    print(json.dumps(data, sort_keys=True, default=str))


def load_client(service_map: dict[str, dict[str, str]], base_url: str | None = None) -> ChimClient:
    return ChimClient(
        api_key=resolve_api_key(),
        service_map=service_map,
        base_url=base_url or DEFAULT_BASE_URL,
    )


def cmd_list_incidents(args: argparse.Namespace) -> None:
    service_map = load_service_map(args.service_map)
    client = load_client(service_map, base_url=args.base_url)
    selected_service_ids = parse_service_ids(args.services, service_map)
    incidents = client.paginate("/outages/", params=build_incident_params(args, service_map))
    incidents = filter_incidents_by_services(incidents, selected_service_ids)
    if args.format == "summary":
        print_json(
            [incident_summary_row(incident, service_map) for incident in incidents],
            pretty=args.pretty,
        )
        return
    print_json(incidents, pretty=args.pretty)


def cmd_get_incident(args: argparse.Namespace) -> None:
    service_map = load_service_map(args.service_map)
    client = load_client(service_map, base_url=args.base_url)
    print_json(
        client.request_json("GET", f"/outages/{args.outage_id}/"),
        pretty=args.pretty,
    )


def cmd_list_changes(args: argparse.Namespace) -> None:
    service_map = load_service_map(args.service_map)
    client = load_client(service_map, base_url=args.base_url)
    selected_service_ids = parse_service_ids(args.services, service_map)
    changes = client.paginate("/changes/", params=build_change_params(args, service_map))
    changes = filter_changes_by_services(changes, selected_service_ids)
    if args.format == "summary":
        print_json(
            [change_summary_row(change, service_map) for change in changes],
            pretty=args.pretty,
        )
        return
    print_json(changes, pretty=args.pretty)


def cmd_get_change(args: argparse.Namespace) -> None:
    service_map = load_service_map(args.service_map)
    client = load_client(service_map, base_url=args.base_url)
    print_json(
        client.request_json("GET", f"/changes/{args.change_id}/"),
        pretty=args.pretty,
    )


def cmd_analyze(args: argparse.Namespace) -> None:
    service_map = load_service_map(args.service_map)
    client = load_client(service_map, base_url=args.base_url)
    selected_service_ids = parse_service_ids(args.services, service_map)

    created_after = args.created_after or (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    created_before = args.created_before or datetime.now().strftime("%Y-%m-%d")

    params = build_incident_params(args, service_map)
    params["created_after"] = created_after
    params["created_before"] = created_before
    incidents = client.paginate("/outages/", params=params)
    incidents = filter_incidents_by_services(incidents, selected_service_ids)
    print_json(
        build_analysis(
            incidents=incidents,
            service_map=service_map,
            since=created_after,
            until=created_before,
        ),
        pretty=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local CHIM helper for SWG/NATaaS incident and change reads")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument(
        "--service-map",
        default=str(DEFAULT_SERVICE_MAP_PATH),
        help="Path to the CHIM service map JSON file.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="CHIM API base URL.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_incidents = subparsers.add_parser("list-incidents", help="List CHIM incidents with filters")
    list_incidents.add_argument("--services", help="Comma-separated service IDs")
    list_incidents.add_argument("--created-after", help="Start date YYYY-MM-DD")
    list_incidents.add_argument("--created-before", help="End date YYYY-MM-DD")
    list_incidents.add_argument("--severity", help="Severity filter (1-4)")
    list_incidents.add_argument("--status", help="Status filter (open/resolved/closed)")
    list_incidents.add_argument("--environment", help="Environment filter")
    list_incidents.add_argument("--search", help="Free-text search")
    list_incidents.add_argument("--external-impact", action="store_true", help="Only incidents with external customer impact")
    list_incidents.add_argument("--internal-impact", action="store_true", help="Only incidents with internal customer impact")
    list_incidents.add_argument("--format", choices=["summary", "full"], default="summary")
    list_incidents.set_defaults(func=cmd_list_incidents)

    get_incident = subparsers.add_parser("get-incident", help="Get a single CHIM incident")
    get_incident.add_argument("outage_id", help="Outage ID, for example OTG-1234")
    get_incident.set_defaults(func=cmd_get_incident)

    list_changes = subparsers.add_parser("list-changes", help="List CHIM changes with filters")
    list_changes.add_argument("--services", help="Comma-separated service IDs")
    list_changes.add_argument("--created-after", help="Start date YYYY-MM-DD")
    list_changes.add_argument("--created-before", help="End date YYYY-MM-DD")
    list_changes.add_argument("--change-type", help="Change type filter")
    list_changes.add_argument("--status", help="Status filter")
    list_changes.add_argument("--format", choices=["summary", "full"], default="summary")
    list_changes.set_defaults(func=cmd_list_changes)

    get_change = subparsers.add_parser("get-change", help="Get a single CHIM change")
    get_change.add_argument("change_id", help="Change ID, for example CHG-1234")
    get_change.set_defaults(func=cmd_get_change)

    analyze = subparsers.add_parser("analyze", help="Analyze CHIM incidents across team, service, severity, and month")
    analyze.add_argument("--services", help="Comma-separated service IDs")
    analyze.add_argument("--created-after", help="Start date YYYY-MM-DD")
    analyze.add_argument("--created-before", help="End date YYYY-MM-DD")
    analyze.add_argument("--severity", help="Severity filter (1-4)")
    analyze.add_argument("--status", help="Status filter (open/resolved/closed)")
    analyze.add_argument("--environment", help="Environment filter")
    analyze.add_argument("--search", help="Free-text search")
    analyze.add_argument("--external-impact", action="store_true", help="Only incidents with external customer impact")
    analyze.add_argument("--internal-impact", action="store_true", help="Only incidents with internal customer impact")
    analyze.set_defaults(func=cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ChimSkillError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
