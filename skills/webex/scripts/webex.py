#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = os.environ.get("WEBEX_API_BASE", "https://webexapis.com/v1")


class WebexSkillError(RuntimeError):
    pass


class WebexAuthError(WebexSkillError):
    pass


class WebexApiError(WebexSkillError):
    pass


def parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    normalized = value.strip()
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise WebexSkillError(
            f"{field_name} must be an ISO 8601 timestamp, got {value!r}"
        ) from error


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


def run_auth_runtime_resolve(no_refresh: bool) -> str:
    auth_runtime_bin = os.environ.get("AUTH_RUNTIME_BIN", "auth-runtime")
    command = [auth_runtime_bin, "resolve", "webex"]
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


def resolve_access_token(env_var: str = "WEBEX_ACCESS_TOKEN", allow_refresh: bool = True) -> str:
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return env_value

    attempts = [True] + ([] if not allow_refresh else [False])
    errors: list[str] = []
    for no_refresh in attempts:
        command_text = "auth-runtime resolve webex --no-refresh --format value"
        if not no_refresh:
            command_text = "auth-runtime resolve webex --format value"
        try:
            token = run_auth_runtime_resolve(no_refresh=no_refresh)
        except FileNotFoundError as error:
            raise WebexAuthError(
                "Could not resolve the Webex access token because `auth-runtime` was not found on PATH. "
                "Install or upgrade it with `uv tool install --upgrade "
                "git+ssh://git@github.com/mcrewson-cisco/auth_runtime.git`."
            ) from error
        except subprocess.CalledProcessError as error:
            output = (error.stderr or error.stdout or "").strip()
            record = parse_auth_runtime_error(output)
            if is_sandbox_auth_block(record):
                message = str(record.get("message") or "local auth path unavailable").strip()
                raise WebexAuthError(
                    "Webex credential resolution is blocked in this session because auth-runtime cannot access "
                    f"the local cache or desktop auth path ({message}). This is common in sandboxed Codex runs. "
                    "Run `auth-runtime doctor webex --format json`, then rerun this same Webex command with narrow escalation."
                ) from error
            errors.append(
                f"`{command_text}` failed: {output or f'exited with status {error.returncode}'}"
            )
            continue
        if token:
            return token
        errors.append(f"`{command_text}` returned an empty token")

    raise WebexAuthError(
        "Could not resolve the Webex access token. "
        "Run `auth-runtime doctor webex --format json`, then retry. "
        f"Original output: {' | '.join(errors)}"
    )


class WebexClient:
    def __init__(
        self,
        *,
        access_token: str,
        base_url: str = DEFAULT_BASE_URL,
        max_http_retries: int = 2,
    ) -> None:
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.max_http_retries = max_http_retries

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self.base_url + path
        if params:
            url += ("&" if "?" in path else "?") + urllib.parse.urlencode(params, doseq=True)

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

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
                try:
                    message = json.loads(detail).get("message", detail)
                except (json.JSONDecodeError, AttributeError):
                    message = detail or error.reason
                raise WebexApiError(
                    f"Webex API error {error.code} on {method} {path}: {message}"
                ) from error
            except urllib.error.URLError as error:
                raise WebexApiError(
                    f"Webex API request failed on {method} {path}: {error.reason}"
                ) from error

    def api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.request_json(method, path, params=params, body=body)

    def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        max_items: int = 200,
    ) -> list[dict[str, Any]]:
        url = self.base_url + path
        if params:
            url += ("&" if "?" in path else "?") + urllib.parse.urlencode(params, doseq=True)

        items: list[dict[str, Any]] = []
        while url and len(items) < max_items:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            }
            request = urllib.request.Request(url, headers=headers, method="GET")
            for attempt in range(self.max_http_retries + 1):
                try:
                    with urllib.request.urlopen(request) as response:
                        payload = response.read().decode("utf-8")
                        data = json.loads(payload) if payload else {}
                        items.extend(data.get("items", []))
                        url = parse_next_link(response.headers.get("Link", ""))
                        break
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
                    raise WebexApiError(
                        f"Webex API error {error.code} on GET {path}: {detail or error.reason}"
                    ) from error
                except urllib.error.URLError as error:
                    raise WebexApiError(
                        f"Webex API request failed on GET {path}: {error.reason}"
                    ) from error
            else:
                break
        return items[:max_items]


def parse_next_link(link_header: str) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        match = re.search(r"<([^>]+)>", part)
        if match:
            return match.group(1)
    return None


def format_person(payload: dict[str, Any]) -> str:
    display_name = payload.get("personDisplayName") or payload.get("displayName") or ""
    email = payload.get("personEmail") or ""
    emails = payload.get("emails") or []
    if not email and isinstance(emails, list) and emails:
        email = str(emails[0])
    if display_name and email:
        return f"{display_name} <{email}>"
    return display_name or email


def format_room(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id"),
        "title": payload.get("title"),
        "type": payload.get("type"),
        "isLocked": payload.get("isLocked"),
        "lastActivity": payload.get("lastActivity"),
        "created": payload.get("created"),
        "teamId": payload.get("teamId"),
    }


def html_to_text(html_content: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html_content, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "  - ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_message(payload: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
    result = {
        "id": payload.get("id"),
        "roomId": payload.get("roomId"),
        "personEmail": payload.get("personEmail"),
        "personDisplayName": format_person(payload),
        "created": payload.get("created"),
    }
    text = payload.get("text", "")
    html = payload.get("html", "")
    if full and html:
        result["text"] = html_to_text(html)
        result["markdown"] = payload.get("markdown", "")
    elif full:
        result["text"] = text
    else:
        result["text"] = (text[:200] + "...") if len(text) > 200 else text
    if payload.get("files"):
        result["files"] = payload["files"]
    if payload.get("parentId"):
        result["parentId"] = payload["parentId"]
    return result


def format_member(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id"),
        "personId": payload.get("personId"),
        "personEmail": payload.get("personEmail"),
        "personDisplayName": payload.get("personDisplayName"),
        "isModerator": payload.get("isModerator"),
        "isMonitor": payload.get("isMonitor"),
        "created": payload.get("created"),
    }


def emit(payload: Any, *, pretty: bool = False) -> None:
    if pretty:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))


def build_client(args: argparse.Namespace) -> WebexClient:
    return WebexClient(
        access_token=resolve_access_token(),
        base_url=getattr(args, "base_url", DEFAULT_BASE_URL),
    )


def should_fallback_identity_probe(error: WebexApiError) -> bool:
    return "Webex API error 403" in str(error)


def cmd_auth_check(args: argparse.Namespace) -> None:
    client = build_client(args)
    method = "token"
    try:
        identity = client.api("GET", "/people/me")
        result = {
            "status": "authenticated",
            "method": method,
            "displayName": identity.get("displayName"),
            "emails": identity.get("emails", []),
            "orgId": identity.get("orgId"),
        }
    except WebexApiError as error:
        if not should_fallback_identity_probe(error):
            raise
        probe = client.api("GET", "/rooms", params={"max": "1"})
        result = {
            "status": "authenticated",
            "method": method,
            "verified": probe is not None,
            "note": "Token valid, but /people/me is unavailable for this token scope.",
        }
    emit(result, pretty=args.pretty)


def cmd_rooms(args: argparse.Namespace) -> None:
    client = build_client(args)
    params: dict[str, Any] = {"max": str(args.max)}
    if args.type:
        params["type"] = args.type
    if args.team_id:
        params["teamId"] = args.team_id
    if args.sort_by:
        params["sortBy"] = args.sort_by
    payload = client.api("GET", "/rooms", params=params)
    emit([format_room(room) for room in payload.get("items", [])], pretty=args.pretty)


def cmd_room_info(args: argparse.Namespace) -> None:
    client = build_client(args)
    payload = client.api("GET", f"/rooms/{args.room_id}")
    emit(format_room(payload), pretty=args.pretty)


def cmd_search_rooms(args: argparse.Namespace) -> None:
    client = build_client(args)
    query = args.query.lower()
    rooms = client.paginate(
        "/rooms",
        params={"max": "200", "sortBy": "lastactivity"},
        max_items=max(args.max, 200),
    )
    matches = [
        format_room(room)
        for room in rooms
        if query in str(room.get("title", "")).lower()
    ][: args.max]
    emit(matches, pretty=args.pretty)


def cmd_messages(args: argparse.Namespace) -> None:
    client = build_client(args)
    params: dict[str, Any] = {
        "roomId": args.room_id,
        "max": str(args.max),
    }
    if args.before:
        params["before"] = args.before
    if args.parent_id:
        params["parentId"] = args.parent_id
    payload = client.api("GET", "/messages", params=params)
    emit([format_message(message) for message in payload.get("items", [])], pretty=args.pretty)


def cmd_read(args: argparse.Namespace) -> None:
    client = build_client(args)
    payload = client.api("GET", f"/messages/{args.message_id}")
    emit(format_message(payload, full=True), pretty=args.pretty)


def cmd_members(args: argparse.Namespace) -> None:
    client = build_client(args)
    payload = client.api(
        "GET",
        "/memberships",
        params={"roomId": args.room_id, "max": str(args.max)},
    )
    emit([format_member(item) for item in payload.get("items", [])], pretty=args.pretty)


def cmd_people_search(args: argparse.Namespace) -> None:
    if not args.query and not args.email:
        raise WebexSkillError("people-search requires --query or --email")
    client = build_client(args)
    params: dict[str, Any] = {"max": str(args.max)}
    if args.query:
        params["displayName"] = args.query
    if args.email:
        params["email"] = args.email
    payload = client.api("GET", "/people", params=params)
    people = [
        {
            "id": person.get("id"),
            "displayName": person.get("displayName"),
            "emails": person.get("emails", []),
            "orgId": person.get("orgId"),
            "type": person.get("type"),
        }
        for person in payload.get("items", [])
    ]
    emit(people, pretty=args.pretty)


def cmd_find_person_messages(args: argparse.Namespace) -> None:
    client = build_client(args)
    target_email = args.email.strip().lower()
    since_dt = parse_iso_datetime(args.since, field_name="--since") if args.since else None
    until_dt = parse_iso_datetime(args.until, field_name="--until") if args.until else None
    if since_dt and until_dt and until_dt < since_dt:
        raise WebexSkillError("--until must be greater than or equal to --since")

    rooms = client.paginate(
        "/rooms",
        params={"max": "200", "sortBy": "lastactivity"},
        max_items=args.max_rooms,
    )

    hits: list[dict[str, Any]] = []
    active_rooms_considered = 0
    rooms_fetched = 0
    for room in rooms:
        room_type = room.get("type")
        if args.room_type and room_type != args.room_type:
            continue

        last_activity = str(room.get("lastActivity", "")).strip()
        if since_dt and last_activity:
            try:
                last_activity_dt = parse_iso_datetime(last_activity, field_name="room lastActivity")
            except WebexSkillError:
                last_activity_dt = None
            if last_activity_dt and last_activity_dt < since_dt:
                continue

        active_rooms_considered += 1
        payload = client.api(
            "GET",
            "/messages",
            params={"roomId": room["id"], "max": str(args.max_messages)},
        )
        rooms_fetched += 1
        for message in payload.get("items", []):
            created_text = str(message.get("created", "")).strip()
            if not created_text:
                continue
            try:
                created_dt = parse_iso_datetime(created_text, field_name="message created")
            except WebexSkillError:
                continue
            if until_dt and created_dt > until_dt:
                continue
            if since_dt and created_dt < since_dt:
                break
            if str(message.get("personEmail", "")).strip().lower() != target_email:
                continue
            hits.append(
                {
                    "roomId": room.get("id"),
                    "roomTitle": room.get("title"),
                    "roomType": room_type,
                    "created": message.get("created"),
                    "text": message.get("text", ""),
                    "parentId": message.get("parentId"),
                    "messageId": message.get("id"),
                }
            )

    hits.sort(key=lambda hit: str(hit.get("created", "")), reverse=True)
    emit(
        {
            "target_email": target_email,
            "since": args.since,
            "until": args.until,
            "active_rooms_considered": active_rooms_considered,
            "rooms_fetched": rooms_fetched,
            "hits": hits,
        },
        pretty=args.pretty,
    )


def cmd_summarize(args: argparse.Namespace) -> None:
    client = build_client(args)
    room = client.api("GET", f"/rooms/{args.room_id}")
    payload = client.api(
        "GET",
        "/messages",
        params={"roomId": args.room_id, "max": str(args.max)},
    )
    messages = list(payload.get("items", []))
    messages.reverse()

    lines = [
        f"# Messages from: {room.get('title', 'Unknown Room')}",
        f"# Count: {len(messages)}",
        "",
    ]
    for message in messages:
        ts = str(message.get("created", ""))[:19].replace("T", " ")
        sender = format_person(message)
        text = str(message.get("text", "")).strip()
        if message.get("files"):
            text += f" [+{len(message['files'])} file(s)]"
        lines.append(f"[{ts}] {sender}: {text}")
    print("\n".join(lines))


def cmd_send(args: argparse.Namespace) -> None:
    body: dict[str, Any] = {}
    if args.room_id:
        body["roomId"] = args.room_id
    if args.person_email:
        body["toPersonEmail"] = args.person_email
    if args.person_id:
        body["toPersonId"] = args.person_id
    if not body:
        raise WebexSkillError("send requires --room-id, --person-email, or --person-id")

    if args.markdown:
        body["markdown"] = args.markdown
    elif args.text:
        body["text"] = args.text
    else:
        raise WebexSkillError("send requires --text or --markdown")

    if args.parent_id:
        body["parentId"] = args.parent_id

    if not args.confirm:
        destination = args.room_id or args.person_email or args.person_id
        content = args.markdown or args.text
        print("=== Send Preview ===", file=sys.stderr)
        print(f"To: {destination}", file=sys.stderr)
        if args.parent_id:
            print(f"Thread (parentId): {args.parent_id}", file=sys.stderr)
        print(f"Content:\n{content}\n", file=sys.stderr)
        print("Re-run with --confirm to send.", file=sys.stderr)
        emit({"status": "preview", "message": "Add --confirm to send"})
        return

    client = build_client(args)
    result = client.api("POST", "/messages", body=body)
    emit(
        {
            "status": "sent",
            "id": result.get("id"),
            "roomId": result.get("roomId"),
            "created": result.get("created"),
        },
        pretty=args.pretty,
    )


def cmd_reply(args: argparse.Namespace) -> None:
    client = build_client(args)
    parent = client.api("GET", f"/messages/{args.message_id}")
    room_id = parent.get("roomId")
    if not room_id:
        raise WebexSkillError("Could not determine roomId from the parent message")

    body = {
        "roomId": room_id,
        "parentId": args.message_id,
    }
    if args.markdown:
        body["markdown"] = args.markdown
    elif args.text:
        body["text"] = args.text
    else:
        raise WebexSkillError("reply requires --text or --markdown")

    if not args.confirm:
        content = args.markdown or args.text
        print("=== Reply Preview ===", file=sys.stderr)
        print(f"Replying to: {format_person(parent)}", file=sys.stderr)
        print(f"Original: {str(parent.get('text', ''))[:150]}", file=sys.stderr)
        print(f"Reply:\n{content}\n", file=sys.stderr)
        print("Re-run with --confirm to send.", file=sys.stderr)
        emit({"status": "preview", "message": "Add --confirm to send"})
        return

    result = client.api("POST", "/messages", body=body)
    emit(
        {
            "status": "sent",
            "id": result.get("id"),
            "roomId": result.get("roomId"),
            "parentId": args.message_id,
            "created": result.get("created"),
        },
        pretty=args.pretty,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Webex helper for Codex")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Webex API base URL (default: {DEFAULT_BASE_URL})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth-check", help="Verify Webex auth and show identity")

    sp = sub.add_parser("rooms", help="List rooms/spaces")
    sp.add_argument("--type", choices=["direct", "group"], help="Filter by room type")
    sp.add_argument("--team-id", help="Filter by team ID")
    sp.add_argument("--max", type=int, default=50, help="Max results")
    sp.add_argument(
        "--sort-by",
        choices=["id", "lastactivity", "created"],
        default="lastactivity",
        help="Sort order",
    )

    sp = sub.add_parser("room-info", help="Get room details")
    sp.add_argument("room_id", help="Room ID")

    sp = sub.add_parser("search-rooms", help="Search recent rooms by title")
    sp.add_argument("--query", required=True, help="Case-insensitive room title substring")
    sp.add_argument("--max", type=int, default=20, help="Max results")

    sp = sub.add_parser("messages", help="List messages in a room")
    sp.add_argument("room_id", help="Room ID")
    sp.add_argument("--max", type=int, default=30, help="Max messages")
    sp.add_argument("--before", help="ISO timestamp")
    sp.add_argument("--parent-id", help="List replies under a specific parent message")

    sp = sub.add_parser("read", help="Read a single message in full")
    sp.add_argument("message_id", help="Message ID")

    sp = sub.add_parser("members", help="List room members")
    sp.add_argument("room_id", help="Room ID")
    sp.add_argument("--max", type=int, default=100, help="Max results")

    sp = sub.add_parser("people-search", help="Search people by display name or email")
    sp.add_argument("--query", help="Display name query")
    sp.add_argument("--email", help="Email address lookup")
    sp.add_argument("--max", type=int, default=10, help="Max results")

    sp = sub.add_parser(
        "find-person-messages",
        help="Search recent active rooms for messages by a specific person",
    )
    sp.add_argument("--email", required=True, help="Person email to match")
    sp.add_argument("--since", help="Only include messages at or after this ISO timestamp")
    sp.add_argument("--until", help="Only include messages at or before this ISO timestamp")
    sp.add_argument("--room-type", choices=["direct", "group"], help="Limit rooms by type")
    sp.add_argument("--max-rooms", type=int, default=100, help="Max rooms to inspect")
    sp.add_argument("--max-messages", type=int, default=100, help="Max messages per room")

    sp = sub.add_parser("summarize", help="Format recent room messages for LLM summarization")
    sp.add_argument("room_id", help="Room ID")
    sp.add_argument("--max", type=int, default=50, help="Max messages")

    sp = sub.add_parser("send", help="Preview or send a message")
    sp.add_argument("--room-id", help="Target room ID")
    sp.add_argument("--person-email", help="Target person email for 1:1")
    sp.add_argument("--person-id", help="Target person ID for 1:1")
    sp.add_argument("--text", help="Plain-text content")
    sp.add_argument("--markdown", help="Markdown content")
    sp.add_argument("--parent-id", help="Parent message ID for threaded send")
    sp.add_argument("--confirm", action="store_true", help="Actually send the message")

    sp = sub.add_parser("reply", help="Preview or send a threaded reply")
    sp.add_argument("message_id", help="Parent message ID")
    sp.add_argument("--text", help="Plain-text reply")
    sp.add_argument("--markdown", help="Markdown reply")
    sp.add_argument("--confirm", action="store_true", help="Actually send the reply")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "auth-check": cmd_auth_check,
        "rooms": cmd_rooms,
        "room-info": cmd_room_info,
        "search-rooms": cmd_search_rooms,
        "messages": cmd_messages,
        "read": cmd_read,
        "members": cmd_members,
        "people-search": cmd_people_search,
        "find-person-messages": cmd_find_person_messages,
        "summarize": cmd_summarize,
        "send": cmd_send,
        "reply": cmd_reply,
    }

    try:
        dispatch[args.command](args)
    except WebexSkillError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
