# PagerDuty Commands Reference

Reference for the local read-only PagerDuty helper in this environment.

## Helper Path

```bash
SCRIPT=/Users/mcrewson/.agents/skills/pagerduty/scripts/pagerduty.py
```

## Auth Checks

If a PagerDuty command fails on auth, inspect the runtime first:

```bash
which auth-runtime
auth-runtime doctor pagerduty --format json
```

If you specifically need to know whether a token is already available without refresh:

```bash
auth-runtime resolve pagerduty --no-refresh --format json
```

If live PagerDuty access is still needed and the no-refresh path is empty or stale:

```bash
auth-runtime resolve pagerduty --format json
```

Do not fall back to direct `security` or `op read` calls from Codex.

## Current On-Call

```bash
python3 "$SCRIPT" --pretty oncall
python3 "$SCRIPT" --pretty oncall --services PQJOF34,PZ2VH4U
python3 "$SCRIPT" --pretty oncall --schedule-ids PABC123,PXYZ789
```

## Services and Schedules

```bash
python3 "$SCRIPT" --pretty list-services
python3 "$SCRIPT" --pretty list-services --services PQJOF34
python3 "$SCRIPT" --pretty get-service PQJOF34
python3 "$SCRIPT" --pretty list-schedules
python3 "$SCRIPT" --pretty list-schedules --services P7VLSUG,PXSWYNF
```

## Incident Reads

```bash
python3 "$SCRIPT" --pretty list-incidents --since 2026-03-01 --until 2026-04-03
python3 "$SCRIPT" --pretty list-incidents --statuses triggered,acknowledged
python3 "$SCRIPT" --pretty list-incidents --urgencies high
python3 "$SCRIPT" --pretty list-incidents --services PQJOF34,PZ2VH4U --format full
python3 "$SCRIPT" --pretty get-incident PABC123
```

## Analytics and Analysis

Use `analytics` for aggregate PagerDuty metrics and `analyze` for broader trend/pattern questions.

```bash
python3 "$SCRIPT" --pretty analytics --since 2026-01-01 --until 2026-04-01
python3 "$SCRIPT" --pretty analytics --aggregate-unit month
python3 "$SCRIPT" --pretty analyze
python3 "$SCRIPT" --pretty analyze --since 2026-01-01 --until 2026-04-01
python3 "$SCRIPT" --pretty analyze --statuses resolved --urgencies high
```

## Output Notes

- `list-services`, `list-schedules`, and `oncall` may include a `warnings` array when some related lookups fail but the overall read still succeeded.
- `analytics` reflects PagerDuty Analytics API results directly and may be limited by PagerDuty plan/permissions.
- `analyze` computes MTTR from incident timestamps and enriches MTTA/MTTR from the Analytics API when available.
- `analyze` surfaces repeated incident titles under `noisy_incidents`.

## Default Scope

The helper defaults to `data/services.json`, which currently maps these services:

- `PQJOF34` Artemis SWG Traffic Acquisition Production Service
- `PZ2VH4U` Athena MPS Production Service
- `PB7YIB6` Atlantis - China Environment - Production
- `P7VLSUG` Atlantis - Production Critical
- `PXSWYNF` Athena Proxy Production Service
- `PNON446` NAT as a Service

Override that scope per command with `--services`.
