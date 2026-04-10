# Webex Commands Reference

Reference for the local Webex helper in this environment.

## Helper Path

```bash
SCRIPT=/Users/mcrewson/.agents/skills/webex/scripts/webex.py
```

## Auth Checks

If a Webex command fails on auth, inspect the runtime first:

```bash
auth-runtime doctor webex --format json
```

If you specifically need to know whether a Webex token is already available without refresh:

```bash
auth-runtime resolve webex --no-refresh --format json
```

If live Webex access is still needed and the no-refresh path is empty or stale:

```bash
auth-runtime resolve webex --format json
```

Do not fall back to direct `security` or `op read` calls from Codex.

For ordinary room/message reads, do not preflight with `auth-check` or `--help`
unless the helper behavior is actually unclear. Stable commands should be called
directly.

## Rooms And Messages

```bash
python3 "$SCRIPT" --pretty auth-check
python3 "$SCRIPT" --pretty rooms --max 20
python3 "$SCRIPT" --pretty rooms --type group --max 20
python3 "$SCRIPT" --pretty room-info ROOM_ID
python3 "$SCRIPT" --pretty search-rooms --query "NATaaS"
python3 "$SCRIPT" --pretty messages ROOM_ID --max 30
python3 "$SCRIPT" --pretty messages ROOM_ID --parent-id PARENT_MESSAGE_ID
python3 "$SCRIPT" --pretty read MESSAGE_ID
python3 "$SCRIPT" --pretty members ROOM_ID
```

## People Search

```bash
python3 "$SCRIPT" --pretty people-search --query "Mark Crewson"
python3 "$SCRIPT" --pretty people-search --email "mcrewson@cisco.com"
```

## Cross-Room Person Scans

Use this when the question is "did X post/ask anything today?" or similar.

```bash
python3 "$SCRIPT" --pretty find-person-messages --email "lmaheshw@cisco.com" --since 2026-04-03T07:00:00Z
python3 "$SCRIPT" --pretty find-person-messages --email "lmaheshw@cisco.com" --since 2026-04-03T07:00:00Z --room-type direct
python3 "$SCRIPT" --pretty find-person-messages --email "lmaheshw@cisco.com" --since 2026-03-30T07:00:00Z --until 2026-04-04T06:59:59Z
```

Notes:

- `find-person-messages` scans recent active rooms rather than one known room.
- It returns room metadata plus matching messages, so the caller can decide whether something was an ask, a reply, or just a status update.
- If the email is unknown, use `people-search` once, then call `find-person-messages`.

## Summarization

`summarize` is read-only. It emits chronological plain text for LLM consumption.

```bash
python3 "$SCRIPT" summarize ROOM_ID
python3 "$SCRIPT" summarize ROOM_ID --max 100
```

## Safe Writes

Preview before posting:

```bash
python3 "$SCRIPT" send --room-id ROOM_ID --text "hello"
python3 "$SCRIPT" reply MESSAGE_ID --text "reply text"
```

Actually send:

```bash
python3 "$SCRIPT" --pretty send --room-id ROOM_ID --text "hello" --confirm
python3 "$SCRIPT" --pretty reply MESSAGE_ID --text "reply text" --confirm
```

`send` also supports:

```bash
python3 "$SCRIPT" send --person-email "user@cisco.com" --text "hello"
python3 "$SCRIPT" send --room-id ROOM_ID --markdown "**bold**" --confirm
```

## Output Notes

- `messages` returns newest-first, matching the Webex API.
- `summarize` reorders messages chronologically for easier downstream summarization.
- `search-rooms` uses client-side title filtering over recent rooms.
- `auth-check` prefers `/people/me` but can still verify a token without that scope.
- `auth-check` is for diagnosing auth only; it is not routine preflight for normal reads.
