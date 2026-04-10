---
name: chim
description: Use when working with CHIM incidents, outages, changes, or incident trend analysis through the local read-only CHIM helper, especially for current SWG/NATaaS service coverage, incident detail, change history, or aggregate patterns.
---

# CHIM

Read-only CHIM workflow for this Codex environment.

Use the bundled helper:

```bash
SCRIPT=/Users/mcrewson/.agents/skills/chim/scripts/chim.py
```

## Scope

This skill is read-only in v1.

Use it for:

- incident and outage lookup
- recent incident lists with filters
- change history tied to the default SWG/NATaaS services
- single incident or change detail
- broader incident-pattern analysis across severity, team, service, and month

Do not use this skill for creating or mutating CHIM incidents, changes, deployments, retrospectives, or other records.

## Auth

Do not call `security` or raw `op read` from this skill.

The helper resolves credentials in this order:

1. `CHIM_API_KEY`
2. `auth-runtime resolve chim --no-refresh --format value`
3. `auth-runtime resolve chim --format value`

`auth-runtime` owns its own `~/.config/auth_runtime/config.toml` lookup, so the
skill helper does not source a separate env file.

If auth fails, inspect it with:

```bash
auth-runtime doctor chim --format json
```

If the helper reports that the local cache or desktop auth path is unavailable,
treat that as a sandboxed-session signal:

1. run `auth-runtime doctor chim --format json` once for diagnosis
2. rerun the same CHIM helper command with narrow escalation
3. do not keep retrying raw `auth-runtime resolve chim ...` calls in the same sandbox state

## Default Service Scope

The helper defaults to the service map in `data/services.json`.

To override the default scope for a command, pass:

```bash
--services ID1,ID2,ID3
```

## Quick Reference

| Intent | Command |
|--------|---------|
| Recent incidents | `python3 "$SCRIPT" --pretty list-incidents --created-after 2026-03-01 --created-before 2026-04-03` |
| Single incident | `python3 "$SCRIPT" --pretty get-incident OTG-1234` |
| Recent changes | `python3 "$SCRIPT" --pretty list-changes --created-after 2026-03-01 --created-before 2026-04-03` |
| Single change | `python3 "$SCRIPT" --pretty get-change CHG-1234` |
| Broader analysis | `python3 "$SCRIPT" --pretty analyze --created-after 2026-01-01 --created-before 2026-04-01` |

## Workflow

1. Start with the narrowest read that answers the question.
2. Prefer `list-incidents`, `get-incident`, `list-changes`, or `get-change` before `analyze`.
3. Use `analyze` for broader questions about incident load, severity distribution, noisy incidents, team/service concentration, or month-over-month patterns.
4. If the helper reports a sandboxed auth failure, run `auth-runtime doctor chim --format json` once, then rerun the same CHIM helper command with narrow escalation.
5. Do not keep retrying raw `auth-runtime resolve chim ...` calls after a sandboxed auth failure; that does not change the underlying condition.

## Sandbox and Network

CHIM reads require network access to `api.chim.umbrella.com`.

Run read-only helper commands in the sandbox first. If a command fails due to a network or sandbox restriction, rerun that same command with narrow escalation rather than broad shell access.

## Deep Dive

Load `references/commands.md` when you need:

- examples with `--services`
- incident or change filter combinations
- interpretation guidance for `analyze`
- troubleshooting auth/runtime failures
