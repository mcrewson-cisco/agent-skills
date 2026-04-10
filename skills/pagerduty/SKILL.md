---
name: pagerduty
description: Use when working with PagerDuty incidents, on-call schedules, rotations, or incident analytics through the local read-only PagerDuty helper, especially for current SWG/NATaaS service coverage, incident detail, or trend analysis.
---

# PagerDuty

Read-only PagerDuty workflow for this Codex environment.

Use the bundled helper:

```bash
SCRIPT=/Users/mcrewson/.agents/skills/pagerduty/scripts/pagerduty.py
```

## Scope

This skill is read-only in v1.

Use it for:

- current on-call coverage
- schedules tied to the default SWG/NATaaS services
- incident lookup and recent incident lists
- per-service MTTA/MTTR analytics
- broader incident-pattern analysis

Do not use this skill for acknowledge, resolve, reassign, escalate, or other PagerDuty mutations.

## Auth

Do not call `security` or raw `op read` from this skill.

The helper resolves credentials in this order:

1. `PAGERDUTY_API_KEY`
2. `auth-runtime resolve pagerduty --no-refresh --format value`
3. `auth-runtime resolve pagerduty --format value`

`auth-runtime` owns its own `~/.config/auth_runtime/config.toml` lookup, so the
skill helper does not source a separate env file.

If auth fails, inspect it with:

```bash
auth-runtime doctor pagerduty --format json
```

## Default Service Scope

The helper defaults to the service map in `data/services.json`.

To override the default scope for a command, pass:

```bash
--services ID1,ID2,ID3
```

## Quick Reference

| Intent | Command |
|--------|---------|
| Current on-call | `python3 "$SCRIPT" --pretty oncall` |
| Recent incidents | `python3 "$SCRIPT" --pretty list-incidents --since 2026-03-01 --until 2026-04-03` |
| Single incident | `python3 "$SCRIPT" --pretty get-incident INCIDENT_ID` |
| Service list | `python3 "$SCRIPT" --pretty list-services` |
| Schedules | `python3 "$SCRIPT" --pretty list-schedules` |
| Analytics | `python3 "$SCRIPT" --pretty analytics --since 2026-01-01 --until 2026-04-01` |
| Broader analysis | `python3 "$SCRIPT" --pretty analyze --since 2026-01-01 --until 2026-04-01` |

## Workflow

1. Start with the narrowest read that answers the question.
2. Prefer `oncall`, `list-schedules`, `list-incidents`, or `get-incident` before `analyze`.
3. Use `analytics` when the question is explicitly about MTTA/MTTR or aggregate response metrics.
4. Use `analyze` for broader questions about trend, noisy alerts, team/service distribution, or time patterns.
5. If the helper reports an auth failure, stop and inspect `auth-runtime doctor pagerduty --format json` instead of retrying raw secret access paths.

## Sandbox and Network

PagerDuty reads require network access to `api.pagerduty.com`.

Run read-only helper commands in the sandbox first. If a command fails due to a network or sandbox restriction, rerun that same command with narrow escalation rather than broad shell access.

## Deep Dive

Load `references/commands.md` when you need:

- examples with `--services`
- incident filter combinations
- interpretation guidance for `analytics` or `analyze`
- troubleshooting auth/runtime failures
