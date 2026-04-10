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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_SERVICE_MAP_PATH = SKILL_DIR / "data" / "services.json"
DEFAULT_BASE_URL = os.environ.get("PAGERDUTY_API_URL", "https://api.pagerduty.com")


class PagerDutySkillError(RuntimeError):
    pass


class ServiceMapError(PagerDutySkillError):
    pass


class PagerDutyAuthError(PagerDutySkillError):
    pass


class PagerDutyApiError(PagerDutySkillError):
    pass


def load_service_map(path: Path | str = DEFAULT_SERVICE_MAP_PATH) -> dict[str, dict[str, str]]:
    service_map_path = Path(path)
    try:
        raw = json.loads(service_map_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ServiceMapError(f"PagerDuty service map not found at {service_map_path}") from error
    except json.JSONDecodeError as error:
        raise ServiceMapError(
            f"PagerDuty service map at {service_map_path} is not valid JSON: {error}"
        ) from error

    if not isinstance(raw, dict):
        raise ServiceMapError(
            f"PagerDuty service map at {service_map_path} must be a JSON object keyed by service ID"
        )

    normalized: dict[str, dict[str, str]] = {}
    for service_id, metadata in raw.items():
        if not isinstance(service_id, str) or not service_id.strip():
            raise ServiceMapError("PagerDuty service IDs must be non-empty strings")
        if not isinstance(metadata, dict):
            raise ServiceMapError(
                f"PagerDuty service {service_id} must map to an object with at least name/team"
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


def service_name_for(service_id: str, service_map: dict[str, dict[str, str]]) -> str:
    return service_map.get(service_id, {}).get("name", service_id)


def team_for(service_id: str, service_map: dict[str, dict[str, str]]) -> str:
    return service_map.get(service_id, {}).get("team", "Unknown")


def run_auth_runtime_resolve(no_refresh: bool) -> str:
    auth_runtime_bin = os.environ.get("AUTH_RUNTIME_BIN", "auth-runtime")
    command = [auth_runtime_bin, "resolve", "pagerduty"]
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


def resolve_api_key(
    env_var: str = "PAGERDUTY_API_KEY",
    allow_refresh: bool = True,
) -> str:
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return env_value

    attempts = [True] + ([] if not allow_refresh else [False])
    errors: list[str] = []
    for no_refresh in attempts:
        command_text = "auth-runtime resolve pagerduty --no-refresh --format value"
        if not no_refresh:
            command_text = "auth-runtime resolve pagerduty --format value"
        try:
            token = run_auth_runtime_resolve(no_refresh=no_refresh)
        except FileNotFoundError as error:
            raise PagerDutyAuthError(
                "Could not resolve the PagerDuty API key because `auth-runtime` was not found on PATH. "
                "Install or upgrade it with `uv tool install --upgrade "
                "git+ssh://git@github.com/mcrewson-cisco/auth_runtime.git`."
            ) from error
        except subprocess.CalledProcessError as error:
            output = (error.stderr or error.stdout or "").strip()
            errors.append(f"`{command_text}` failed: {output or f'exited with status {error.returncode}'}")
            continue
        if token:
            return token
        errors.append(f"`{command_text}` returned an empty token")

    hint = "Run `auth-runtime doctor pagerduty --format json`, then retry."
    raise PagerDutyAuthError(
        "Could not resolve the PagerDuty API key. "
        f"{hint} Original output: {' | '.join(errors)}"
    )


def parse_dt(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_to_human(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def format_metric(seconds: float | None) -> dict[str, Any] | None:
    if seconds is None:
        return None
    return {"seconds": round(seconds, 1), "human": seconds_to_human(seconds)}


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def median(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    size = len(sorted_values)
    middle = size // 2
    if size % 2:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = int(len(sorted_values) * pct)
    return sorted_values[min(index, len(sorted_values) - 1)]


class PagerDutyClient:
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
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)

        headers = {
            "Authorization": f"Token token={self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

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
                raise PagerDutyApiError(
                    f"PagerDuty API error {error.code} on {method} {path}: {detail or error.reason}"
                ) from error
            except urllib.error.URLError as error:
                raise PagerDutyApiError(
                    f"PagerDuty API request failed on {method} {path}: {error.reason}"
                ) from error

        raise PagerDutyApiError(f"PagerDuty API request exhausted retries on {method} {path}")

    def paginate(
        self,
        path: str,
        collection_key: str,
        params: dict[str, Any] | None = None,
        limit: int = 100,
        max_items: int = 5000,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        offset = 0
        base_params = dict(params or {})
        base_params["limit"] = limit

        while True:
            base_params["offset"] = offset
            data = self.request_json("GET", path, params=base_params)
            items = data.get(collection_key, [])
            results.extend(items)
            if not data.get("more", False):
                break
            offset += limit
            if len(results) >= max_items:
                break
        return results


def fetch_service_analytics(
    client: PagerDutyClient,
    service_ids: list[str],
    since: str,
    until: str,
    aggregate_unit: str | None = None,
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        "filters": {
            "created_at_start": since + "T00:00:00Z",
            "created_at_end": until + "T23:59:59Z",
            "service_ids": service_ids,
        }
    }
    if aggregate_unit:
        body["aggregate_unit"] = aggregate_unit

    data = client.request_json(
        "POST",
        "/analytics/metrics/incidents/services",
        body=body,
        extra_headers={"X-EARLY-ACCESS": "analytics-v2"},
    )
    return data.get("data", [])


def build_analysis(
    incidents: list[dict[str, Any]],
    service_map: dict[str, dict[str, str]],
    since: str,
    until: str,
    analytics_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_service: Counter[str] = Counter()
    by_team: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_urgency: Counter[str] = Counter()
    by_month: dict[str, int] = defaultdict(int)
    by_day_of_week: Counter[str] = Counter()
    by_hour: Counter[int] = Counter()
    incidents_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    resolve_times: list[float] = []
    resolve_times_by_service: dict[str, list[float]] = defaultdict(list)
    title_counter: Counter[str] = Counter()

    for incident in incidents:
        service = incident.get("service", {})
        service_id = service.get("id", "")
        service_name = service.get("summary") or service_name_for(service_id, service_map)
        team_name = team_for(service_id, service_map)

        by_service[service_name] += 1
        by_team[team_name] += 1
        by_status[incident.get("status", "unknown")] += 1
        by_urgency[incident.get("urgency", "unknown")] += 1

        created_at = incident.get("created_at", "")
        created_dt = parse_dt(created_at)
        if created_dt:
            by_month[created_dt.strftime("%Y-%m")] += 1
            by_day_of_week[created_dt.strftime("%A")] += 1
            by_hour[created_dt.hour] += 1

        if incident.get("status") == "resolved" and created_dt:
            resolved_dt = parse_dt(incident.get("last_status_change_at"))
            if resolved_dt:
                delta = (resolved_dt - created_dt).total_seconds()
                if delta >= 0:
                    resolve_times.append(delta)
                    resolve_times_by_service[service_name].append(delta)

        title_counter[incident.get("title", "")] += 1
        incidents_by_team[team_name].append(
            {
                "id": incident.get("id"),
                "incident_number": incident.get("incident_number"),
                "title": incident.get("title"),
                "status": incident.get("status"),
                "urgency": incident.get("urgency"),
                "created_at": created_at[:19] if created_at else "",
                "service": service_name,
            }
        )

    analytics_by_service_id = {
        entry.get("service_id"): entry for entry in (analytics_entries or []) if entry.get("service_id")
    }
    per_service_metrics: dict[str, Any] = {}
    for service_name, count in by_service.most_common():
        service_resolve_times = resolve_times_by_service.get(service_name, [])
        entry: dict[str, Any] = {
            "incident_count": count,
            "mttr_mean": format_metric(average(service_resolve_times)),
            "mttr_median": format_metric(median(service_resolve_times)),
            "mttr_p90": format_metric(percentile(service_resolve_times, 0.9)),
        }
        for service_id, analytics_entry in analytics_by_service_id.items():
            if (
                analytics_entry.get("service_name") == service_name
                or service_name_for(service_id, service_map) == service_name
            ):
                entry["mtta_mean_analytics"] = format_metric(
                    analytics_entry.get("mean_seconds_to_first_ack")
                )
                entry["mttr_mean_analytics"] = format_metric(
                    analytics_entry.get("mean_seconds_to_resolve")
                )
                break
        per_service_metrics[service_name] = entry

    weighted_pairs = [
        (
            entry.get("mean_seconds_to_first_ack"),
            entry.get("total_incident_count", 0),
        )
        for entry in analytics_by_service_id.values()
        if entry.get("mean_seconds_to_first_ack") is not None
    ]
    overall_mtta: dict[str, Any]
    if weighted_pairs and sum(count for _, count in weighted_pairs) > 0:
        weighted_total = sum(metric * count for metric, count in weighted_pairs)
        total_weight = sum(count for _, count in weighted_pairs)
        overall_mtta = {
            "weighted_mean": format_metric(weighted_total / total_weight),
            "source": "analytics_api",
        }
    else:
        overall_mtta = {
            "note": "MTTA requires Analytics API access or individual incident fetches",
        }

    day_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    ordered_day_of_week = {day: by_day_of_week.get(day, 0) for day in day_order}
    hour_distribution = {f"{hour:02d}:00": by_hour.get(hour, 0) for hour in range(24)}
    noisy_incidents = {
        title: count
        for title, count in title_counter.most_common(20)
        if title and count >= 3
    }

    return {
        "period": {"from": since, "to": until},
        "total_incidents": len(incidents),
        "mttr": {
            "mean": format_metric(average(resolve_times)),
            "median": format_metric(median(resolve_times)),
            "p90": format_metric(percentile(resolve_times, 0.9)),
            "sample_size": len(resolve_times),
            "source": "computed_from_incidents",
        },
        "mtta": overall_mtta,
        "by_urgency": dict(by_urgency.most_common()),
        "by_status": dict(by_status.most_common()),
        "by_team": dict(by_team.most_common()),
        "by_service": dict(by_service.most_common()),
        "by_month": dict(sorted(by_month.items())),
        "patterns": {
            "by_day_of_week": ordered_day_of_week,
            "by_hour_utc": hour_distribution,
        },
        "noisy_incidents": noisy_incidents,
        "per_service_metrics": per_service_metrics,
        "incidents_by_team": {
            team_name: sorted(
                team_incidents,
                key=lambda incident: incident.get("created_at", ""),
                reverse=True,
            )
            for team_name, team_incidents in incidents_by_team.items()
        },
    }


def output_json(payload: Any, pretty: bool = False) -> None:
    if pretty:
        print(json.dumps(payload, indent=2, default=str))
        return
    print(json.dumps(payload, default=str))


def cmd_list_services(
    args: argparse.Namespace,
    client: PagerDutyClient,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    service_ids = parse_service_ids(args.services, service_map)
    services: list[dict[str, Any]] = []
    warnings: list[str] = []
    for service_id in service_ids:
        try:
            data = client.request_json(
                "GET",
                f"/services/{service_id}",
                params={"include[]": ["escalation_policies", "teams"]},
            )
        except PagerDutyApiError as error:
            warnings.append(f"{service_id}: {error}")
            continue
        service = data.get("service", {})
        escalation_policy = service.get("escalation_policy", {})
        teams = service.get("teams", [])
        services.append(
            {
                "id": service.get("id"),
                "name": service.get("name"),
                "status": service.get("status"),
                "team": team_for(service_id, service_map),
                "escalation_policy": {
                    "id": escalation_policy.get("id"),
                    "name": escalation_policy.get("summary") or escalation_policy.get("name"),
                },
                "pd_teams": [
                    {"id": team.get("id"), "name": team.get("summary")} for team in teams
                ],
                "description": service.get("description"),
                "created_at": service.get("created_at"),
            }
        )
    return {"services": services, "warnings": warnings}


def cmd_get_service(
    args: argparse.Namespace,
    client: PagerDutyClient,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    del service_map
    data = client.request_json(
        "GET",
        f"/services/{args.service_id}",
        params={"include[]": ["escalation_policies", "integrations", "teams"]},
    )
    return data.get("service", data)


def cmd_list_incidents(
    args: argparse.Namespace,
    client: PagerDutyClient,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    service_ids = parse_service_ids(args.services, service_map)
    params: dict[str, Any] = {
        "service_ids[]": service_ids,
        "sort_by": "created_at:desc",
    }
    if args.since:
        params["since"] = args.since + "T00:00:00Z"
    if args.until:
        params["until"] = args.until + "T23:59:59Z"
    if args.statuses:
        params["statuses[]"] = [status.strip() for status in args.statuses.split(",")]
    if args.urgencies:
        params["urgencies[]"] = [urgency.strip() for urgency in args.urgencies.split(",")]

    incidents = client.paginate("/incidents", "incidents", params=params)
    if args.format == "full":
        return {"incidents": incidents, "count": len(incidents)}

    rows: list[dict[str, Any]] = []
    for incident in incidents:
        service = incident.get("service", {})
        service_id = service.get("id", "")
        rows.append(
            {
                "id": incident.get("id"),
                "incident_number": incident.get("incident_number"),
                "title": incident.get("title"),
                "status": incident.get("status"),
                "urgency": incident.get("urgency"),
                "created_at": incident.get("created_at", "")[:19],
                "service_id": service_id,
                "service_name": service.get("summary") or service_name_for(service_id, service_map),
                "team": team_for(service_id, service_map),
            }
        )
    return {"incidents": rows, "count": len(rows)}


def cmd_get_incident(
    args: argparse.Namespace,
    client: PagerDutyClient,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    del service_map
    data = client.request_json(
        "GET",
        f"/incidents/{args.incident_id}",
        params={
            "include[]": [
                "acknowledgers",
                "assignees",
                "conference_bridge",
                "external_references",
            ]
        },
    )
    return data.get("incident", data)


def cmd_list_schedules(
    args: argparse.Namespace,
    client: PagerDutyClient,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    service_ids = parse_service_ids(args.services, service_map)
    escalation_policy_ids: set[str] = set()
    warnings: list[str] = []

    for service_id in service_ids:
        try:
            data = client.request_json("GET", f"/services/{service_id}")
        except PagerDutyApiError as error:
            warnings.append(f"{service_id}: {error}")
            continue
        service = data.get("service", {})
        escalation_policy = service.get("escalation_policy", {})
        if escalation_policy.get("id"):
            escalation_policy_ids.add(escalation_policy["id"])

    schedule_ids: set[str] = set()
    for escalation_policy_id in escalation_policy_ids:
        try:
            data = client.request_json("GET", f"/escalation_policies/{escalation_policy_id}")
        except PagerDutyApiError as error:
            warnings.append(f"{escalation_policy_id}: {error}")
            continue
        escalation_policy = data.get("escalation_policy", {})
        for rule in escalation_policy.get("escalation_rules", []):
            for target in rule.get("targets", []):
                if target.get("type") in ("schedule_reference", "schedule") and target.get("id"):
                    schedule_ids.add(target["id"])

    schedules: list[dict[str, Any]] = []
    for schedule_id in sorted(schedule_ids):
        try:
            data = client.request_json("GET", f"/schedules/{schedule_id}")
        except PagerDutyApiError as error:
            warnings.append(f"{schedule_id}: {error}")
            continue
        schedule = data.get("schedule", {})
        users = schedule.get("users", [])
        schedules.append(
            {
                "id": schedule.get("id"),
                "name": schedule.get("name") or schedule.get("summary"),
                "time_zone": schedule.get("time_zone"),
                "description": schedule.get("description"),
                "users": [
                    {"id": user.get("id"), "name": user.get("summary")} for user in users
                ],
            }
        )
    return {"schedules": schedules, "warnings": warnings}


def cmd_oncall(
    args: argparse.Namespace,
    client: PagerDutyClient,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    service_ids = parse_service_ids(args.services, service_map)
    escalation_policy_map: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for service_id in service_ids:
        try:
            data = client.request_json("GET", f"/services/{service_id}")
        except PagerDutyApiError as error:
            warnings.append(f"{service_id}: {error}")
            continue
        service = data.get("service", {})
        escalation_policy = service.get("escalation_policy", {})
        if escalation_policy.get("id"):
            escalation_policy_map[escalation_policy["id"]] = {
                "service_id": service_id,
                "service_name": service.get("name") or service_name_for(service_id, service_map),
                "team": team_for(service_id, service_map),
                "escalation_policy_name": escalation_policy.get("summary")
                or escalation_policy.get("name"),
            }

    if not escalation_policy_map:
        return {
            "oncall_by_service": {},
            "warnings": warnings + ["No escalation policies found for the requested services"],
        }

    params: dict[str, Any] = {
        "escalation_policy_ids[]": list(escalation_policy_map.keys()),
        "include[]": ["users"],
    }
    if args.schedule_ids:
        params["schedule_ids[]"] = [value.strip() for value in args.schedule_ids.split(",") if value.strip()]

    oncalls = client.paginate("/oncalls", "oncalls", params=params)
    by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for oncall in oncalls:
        escalation_policy = oncall.get("escalation_policy", {})
        escalation_policy_id = escalation_policy.get("id")
        service_info = escalation_policy_map.get(escalation_policy_id, {})
        service_label = service_info.get("service_name", escalation_policy.get("summary", "Unknown"))
        user = oncall.get("user", {})
        schedule = oncall.get("schedule", {})
        by_service[service_label].append(
            {
                "user_name": user.get("summary") or user.get("name"),
                "user_email": user.get("email"),
                "escalation_level": oncall.get("escalation_level", 0),
                "schedule_name": schedule.get("summary") if schedule else None,
                "start": oncall.get("start"),
                "end": oncall.get("end"),
                "team": service_info.get("team"),
                "escalation_policy": service_info.get("escalation_policy_name")
                or escalation_policy.get("summary"),
            }
        )

    sorted_by_service = {
        service_name: sorted(entries, key=lambda entry: entry.get("escalation_level", 99))
        for service_name, entries in by_service.items()
    }
    return {"oncall_by_service": sorted_by_service, "warnings": warnings}


def cmd_analytics(
    args: argparse.Namespace,
    client: PagerDutyClient,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    service_ids = parse_service_ids(args.services, service_map)
    since = args.since or (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%d")
    until = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    analytics_entries = fetch_service_analytics(
        client=client,
        service_ids=service_ids,
        since=since,
        until=until,
        aggregate_unit=args.aggregate_unit,
    )
    services: list[dict[str, Any]] = []
    for entry in analytics_entries:
        service_id = entry.get("service_id", "")
        enriched = dict(entry)
        enriched["team"] = team_for(service_id, service_map)
        enriched["mtta_human"] = seconds_to_human(entry.get("mean_seconds_to_first_ack"))
        enriched["mttr_human"] = seconds_to_human(entry.get("mean_seconds_to_resolve"))
        services.append(enriched)
    return {"period": {"from": since, "to": until}, "services": services}


def cmd_analyze(
    args: argparse.Namespace,
    client: PagerDutyClient,
    service_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    service_ids = parse_service_ids(args.services, service_map)
    since = args.since or (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%d")
    until = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    params: dict[str, Any] = {
        "service_ids[]": service_ids,
        "since": since + "T00:00:00Z",
        "until": until + "T23:59:59Z",
        "sort_by": "created_at:desc",
    }
    if args.statuses:
        params["statuses[]"] = [status.strip() for status in args.statuses.split(",")]
    if args.urgencies:
        params["urgencies[]"] = [urgency.strip() for urgency in args.urgencies.split(",")]

    incidents = client.paginate("/incidents", "incidents", params=params)
    warnings: list[str] = []
    analytics_entries: list[dict[str, Any]] | None = None
    try:
        analytics_entries = fetch_service_analytics(
            client=client,
            service_ids=service_ids,
            since=since,
            until=until,
        )
    except PagerDutyApiError as error:
        warnings.append(f"Analytics API unavailable: {error}")

    analysis = build_analysis(
        incidents=incidents,
        service_map=service_map,
        since=since,
        until=until,
        analytics_entries=analytics_entries,
    )
    if warnings:
        analysis["warnings"] = warnings
    return analysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only PagerDuty helper for incidents, on-call, schedules, and analysis"
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="PagerDuty API base URL",
    )
    parser.add_argument(
        "--services-data",
        default=str(DEFAULT_SERVICE_MAP_PATH),
        help="Path to the default PagerDuty service metadata JSON file",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_services = subparsers.add_parser("list-services", help="List PagerDuty services")
    list_services.add_argument("--services", help="Comma-separated service IDs override")
    list_services.set_defaults(func=cmd_list_services)

    get_service = subparsers.add_parser("get-service", help="Get a specific service")
    get_service.add_argument("service_id", help="PagerDuty service ID")
    get_service.set_defaults(func=cmd_get_service)

    list_incidents = subparsers.add_parser("list-incidents", help="List incidents")
    list_incidents.add_argument("--services", help="Comma-separated service IDs override")
    list_incidents.add_argument("--since", help="Start date YYYY-MM-DD")
    list_incidents.add_argument("--until", help="End date YYYY-MM-DD")
    list_incidents.add_argument("--statuses", help="Comma-separated incident statuses")
    list_incidents.add_argument("--urgencies", help="Comma-separated incident urgencies")
    list_incidents.add_argument(
        "--format",
        choices=["summary", "full"],
        default="summary",
        help="Output format",
    )
    list_incidents.set_defaults(func=cmd_list_incidents)

    get_incident = subparsers.add_parser("get-incident", help="Get a specific incident")
    get_incident.add_argument("incident_id", help="PagerDuty incident ID")
    get_incident.set_defaults(func=cmd_get_incident)

    list_schedules = subparsers.add_parser("list-schedules", help="List related schedules")
    list_schedules.add_argument("--services", help="Comma-separated service IDs override")
    list_schedules.set_defaults(func=cmd_list_schedules)

    oncall = subparsers.add_parser("oncall", help="Show current on-call coverage")
    oncall.add_argument("--services", help="Comma-separated service IDs override")
    oncall.add_argument("--schedule-ids", help="Optional comma-separated schedule filter")
    oncall.set_defaults(func=cmd_oncall)

    analytics = subparsers.add_parser("analytics", help="Show PagerDuty analytics metrics")
    analytics.add_argument("--services", help="Comma-separated service IDs override")
    analytics.add_argument("--since", help="Start date YYYY-MM-DD")
    analytics.add_argument("--until", help="End date YYYY-MM-DD")
    analytics.add_argument(
        "--aggregate-unit",
        choices=["day", "week", "month"],
        help="Aggregate analytics by day, week, or month",
    )
    analytics.set_defaults(func=cmd_analytics)

    analyze = subparsers.add_parser("analyze", help="Build a broader incident analysis report")
    analyze.add_argument("--services", help="Comma-separated service IDs override")
    analyze.add_argument("--since", help="Start date YYYY-MM-DD")
    analyze.add_argument("--until", help="End date YYYY-MM-DD")
    analyze.add_argument("--statuses", help="Comma-separated incident statuses")
    analyze.add_argument("--urgencies", help="Comma-separated incident urgencies")
    analyze.set_defaults(func=cmd_analyze)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    service_map = load_service_map(args.services_data)
    api_key = resolve_api_key()
    client = PagerDutyClient(
        api_key=api_key,
        service_map=service_map,
        base_url=args.base_url,
    )
    payload = args.func(args, client, service_map)
    output_json(payload, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PagerDutySkillError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
