# CHIM Commands Reference

Reference for the local read-only CHIM helper in this environment.

## Helper Path

```bash
SCRIPT=/Users/mcrewson/.agents/skills/chim/scripts/chim.py
```

## Auth Checks

If a CHIM command fails on auth, inspect the runtime first:

```bash
which auth-runtime
auth-runtime doctor chim --format json
```

If the helper says the local cache or desktop auth path is unavailable, that is
usually a sandboxed-session issue. In that case:

1. run the `doctor` command above once
2. rerun the same `python3 "$SCRIPT" ...` command with narrow escalation
3. do not loop on `auth-runtime resolve chim ...`

If you specifically need to know whether a token is already available without refresh:

```bash
auth-runtime resolve chim --no-refresh --format json
```

If live CHIM access is still needed and the no-refresh path is empty or stale:

```bash
auth-runtime resolve chim --format json
```

Do not fall back to direct `security` or `op read` calls from Codex.

## Incident Reads

```bash
python3 "$SCRIPT" --pretty list-incidents --created-after 2026-03-01 --created-before 2026-04-03
python3 "$SCRIPT" --pretty list-incidents --services PNON446 --created-after 2026-04-01 --created-before 2026-04-03
python3 "$SCRIPT" --pretty list-incidents --severity 2 --external-impact
python3 "$SCRIPT" --pretty list-incidents --status resolved --search sidecar
python3 "$SCRIPT" --pretty list-incidents --format full
python3 "$SCRIPT" --pretty get-incident OTG-1234
```

## Change Reads

```bash
python3 "$SCRIPT" --pretty list-changes --created-after 2026-03-01 --created-before 2026-04-03
python3 "$SCRIPT" --pretty list-changes --services PNON446 --change-type significant
python3 "$SCRIPT" --pretty list-changes --format full
python3 "$SCRIPT" --pretty get-change CHG-1234
```

## Analysis

Use `analyze` for broader incident trend and distribution questions.

```bash
python3 "$SCRIPT" --pretty analyze
python3 "$SCRIPT" --pretty analyze --created-after 2026-01-01 --created-before 2026-04-01
python3 "$SCRIPT" --pretty analyze --services PNON446 --external-impact
python3 "$SCRIPT" --pretty analyze --severity 2 --status resolved
```

## Output Notes

- `list-incidents` summary rows include service and team enrichment from the local service map.
- `list-changes` summary rows include service and team enrichment where CHIM exposes service metadata.
- `analyze` surfaces repeated incident titles under `noisy_incidents` and recent high-severity or externally impacting incidents under `notable_incidents`.

## Default Scope

The helper defaults to `data/services.json`, which currently maps these services:

- `PQJOF34` Artemis SWG Traffic Acquisition Production Service
- `PZ2VH4U` Athena MPS Production Service
- `PB7YIB6` Atlantis - China Environment - Production
- `P7VLSUG` Atlantis - Production Critical
- `PXSWYNF` Athena Proxy Production Service
- `PNON446` NAT as a Service

Override that scope per command with `--services`.
