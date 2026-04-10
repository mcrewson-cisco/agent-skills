---
name: webex
description: Use when working with Webex spaces, messages, room membership, people lookup, or room summarization through the local helper, especially for reading room activity, drafting or sending replies safely, or gathering chat context for follow-up work.
---

# Webex

Webex workflow for this Codex environment.

Use the bundled helper:

```bash
SCRIPT=/Users/mcrewson/.agents/skills/webex/scripts/webex.py
```

## Scope

This skill covers read-heavy Webex workflows plus safe message send/reply in v1.

Use it for:

- room and space lookup
- reading recent room messages
- reading a single message in full
- listing room members
- people search by name or email
- cross-room scans for a specific person's recent messages
- formatting room history for LLM summarization
- previewing and sending new messages
- previewing and sending threaded replies

Do not use this skill yet for delete, meetings, recordings, transcripts, or AI meeting summaries.

## Auth

Do not call `security` or raw `op read` from this skill.

The helper resolves credentials in this order:

1. `WEBEX_ACCESS_TOKEN`
2. `auth-runtime resolve webex --no-refresh --format value`
3. `auth-runtime resolve webex --format value`

`auth-runtime` owns its own `~/.config/auth_runtime/config.toml` lookup.

If auth fails, inspect it with:

```bash
auth-runtime doctor webex --format json
```

If the helper reports that the local cache or desktop auth path is unavailable,
treat that as a sandboxed-session signal:

1. run `auth-runtime doctor webex --format json` once for diagnosis
2. rerun the same Webex helper command with narrow escalation
3. do not keep retrying raw `auth-runtime resolve webex ...` calls in the same sandbox state

## Safety

`send` and `reply` require `--confirm` to actually post. Without `--confirm`,
the helper prints a preview and exits without mutating Webex.

## Quick Reference

| Intent | Command |
|--------|---------|
| Verify auth | `python3 "$SCRIPT" --pretty auth-check` |
| List rooms | `python3 "$SCRIPT" --pretty rooms --max 20` |
| Search rooms | `python3 "$SCRIPT" --pretty search-rooms --query "NATaaS"` |
| Room messages | `python3 "$SCRIPT" --pretty messages ROOM_ID --max 30` |
| Read one message | `python3 "$SCRIPT" --pretty read MESSAGE_ID` |
| Room members | `python3 "$SCRIPT" --pretty members ROOM_ID` |
| People search | `python3 "$SCRIPT" --pretty people-search --query "Mark"` |
| Cross-room person scan | `python3 "$SCRIPT" --pretty find-person-messages --email user@cisco.com --since 2026-04-03T07:00:00Z` |
| Summarize room | `python3 "$SCRIPT" summarize ROOM_ID --max 100` |
| Preview a send | `python3 "$SCRIPT" send --room-id ROOM_ID --text "hello"` |
| Send a message | `python3 "$SCRIPT" --pretty send --room-id ROOM_ID --text "hello" --confirm` |
| Preview a reply | `python3 "$SCRIPT" reply MESSAGE_ID --text "reply text"` |
| Send a reply | `python3 "$SCRIPT" --pretty reply MESSAGE_ID --text "reply text" --confirm` |

## Workflow

1. Start with the narrowest read that answers the question.
2. For stable helper commands, do not burn turns on `--help` or `auth-check` before the real read; call the targeted command directly.
3. For questions like "did X ask/post anything today?", use `find-person-messages` directly once you know the email. Use `people-search` only if the email is unknown.
4. Prefer `search-rooms`, `messages`, `read`, or `members` before `summarize`.
5. Use `summarize` when the goal is to hand room context to another LLM step or produce a compact narrative.
6. Use `send` or `reply` without `--confirm` first, then repeat with `--confirm` only after the content is right.
7. If the helper reports a sandboxed auth or network failure, rerun that same Webex helper command with narrow escalation instead of probing with extra `auth-check` or `--help` calls.

## Sandbox And Network

Webex reads and writes require network access to `webexapis.com`.

Run helper commands in the sandbox first. If a command fails due to a network or sandbox restriction, rerun that same command with narrow escalation rather than broad shell access.

## Deep Dive

Load `references/commands.md` when you need:

- more room/message command examples
- auth-runtime troubleshooting steps
- cross-room person scan examples
- `people-search` examples
- guidance on when to use `summarize` versus raw `messages`
