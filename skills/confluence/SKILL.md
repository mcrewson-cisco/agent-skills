---
name: confluence
description: Use when working with Confluence page IDs, page URLs, page trees, attachments, comments, or markdown exports through the local confluence CLI, especially for searching, reading, exporting, or updating Confluence content in this Codex environment.
---

# Confluence

CLI-first Confluence workflow for this Codex environment. Use `auth-runtime exec confluence -- ...` so `auth-runtime` injects the credential and required non-secret env such as `CONFLUENCE_DOMAIN` and `CONFLUENCE_EMAIL`.

Do not default to running raw `confluence ...` directly. In this environment, direct CLI use may fall back to local profile config and behave differently than the `auth-runtime` path.

Do not use `confluence profile ...`, `confluence init`, or repo-local Confluence REST helper scripts as the normal execution path. Those are debugging and legacy escape hatches, not the standard workflow here.

## Preflight

Run this in order before Confluence work:

1. `auth-runtime doctor confluence --format json`

For normal reads, prefer `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- ...`. That lets the CLI itself block writes even if you accidentally reach for a mutation command.

If `doctor` looks healthy, go straight to the read-only command you actually need. Do not burn a first Keychain/sandbox approval on `auth-runtime exec confluence -- --help` when this skill already covers the command family.

If `auth-runtime doctor confluence --format json` does not show `exec_environment_keys` including `CONFLUENCE_DOMAIN`, and for Atlassian Cloud basic auth usually `CONFLUENCE_EMAIL`, fix `~/.config/auth_runtime/config.toml` first.

If a command fails, surface the exact error first. Common cases:

- `No configuration found`: missing or broken `auth-runtime` Confluence config
- `403`: token or Confluence permissions mismatch
- `404`: wrong page ID/URL, missing page, or inaccessible page
- `macOS Keychain access appears unavailable from this environment`: sandbox/keychain restriction; rerun the same read-only family with escalation and a reusable prefix rule

Do not jump straight to `confluence init`, `confluence profile ...`, or `--profile` unless you are explicitly debugging the CLI itself. Do not revive old repo-local REST helper scripts just because they exist in reference material. In this environment, `auth-runtime exec confluence -- ...` is the normal path.

## Sandbox And Approvals

Run `auth-runtime doctor confluence --format json` in the sandbox first.

For real CLI reads, Confluence often needs Keychain access through `auth-runtime`, which may fail in the sandbox even when `doctor` succeeds. If the first read-only `auth-runtime exec confluence -- ...` command fails with a likely sandbox or Keychain restriction, rerun that same command with `sandbox_permissions: "require_escalated"` and request a reusable prefix for the read-only family you are about to use.

When you need a reusable approval, prefer `env CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- ...` over a shell variable assignment prefix. It gives you a stable command prefix for `prefix_rule`.

Typical read-only bundle for a Confluence investigation:

- `["auth-runtime", "doctor", "confluence"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "search"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "find"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "info"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "read"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "children"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "attachments"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "comments"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "export"]`
- `["env", "CONFLUENCE_READ_ONLY=true", "auth-runtime", "exec", "confluence", "--", "spaces"]`

Do not request a broad prefix like `["auth-runtime", "exec", "confluence"]`, because that would also cover mutations.

Do not keep escalating one exact read command at a time once you know the task will require multiple Confluence reads. Request the narrow read-only bundle once, then stay inside it.

For writes, use the same pattern as Jira:

1. read the current state first
2. show the exact mutation command
3. get user approval
4. run the exact mutation with `sandbox_permissions: "require_escalated"`
5. use a narrow mutation-family prefix rule such as:
   - `["auth-runtime", "exec", "confluence", "--", "create"]`
   - `["auth-runtime", "exec", "confluence", "--", "create-child"]`
   - `["auth-runtime", "exec", "confluence", "--", "update"]`
   - `["auth-runtime", "exec", "confluence", "--", "move"]`
   - `["auth-runtime", "exec", "confluence", "--", "comment"]`
   - `["auth-runtime", "exec", "confluence", "--", "attachment-upload"]`

## Quick Reference

| Intent | Command |
|--------|---------|
| Search text | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- search "query" -l 10` |
| Search with CQL | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- search --cql 'siteSearch ~ "Geneve Options" and space = "PROD"' -l 20` |
| Find by title | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- find "Exact Title"` |
| Page metadata | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- info 123456` |
| Read page text | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- read 123456 -f text` |
| Read page markdown | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- read 123456 -f markdown` |
| Read by URL | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- read "https://.../pages/123456/Title"` |
| Child tree | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- children 123456 --recursive --format tree --show-id` |
| Child tree JSON | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- children 123456 --recursive --format json --show-id --show-url` |
| List attachments | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- attachments 123456 -f json` |
| Download attachments | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- attachments 123456 --download --dest /tmp/conf-files` |
| Read comments | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- comments 123456 -f markdown --all` |
| Export to markdown | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- export 123456 --format markdown --dest /tmp/conf-export` |
| Dry-run export | `CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- export 123456 --dry-run` |

Most commands that take `<pageId>` also accept supported Confluence page URLs. Prefer numeric IDs or `/pages/<id>` URLs over display URLs when possible.

## Retrieval Workflow

Use this order for read-mostly agent work:

1. Resolve the target page with `find` or `search`.
2. Confirm the page with `info` if the title or space matters.
3. Use one read format first, chosen for the page shape.
4. Narrow locally with `sed` or `rg` before fetching the whole page again in another format.
5. Use `export --format markdown` when you need a local markdown file, attachments, or descendants.
6. Use `children` for page trees, `attachments` for files, and `comments` for discussion context.

Search choice:

- Use `find` first when the user gives a likely page title.
- Use plain `search "query"` for quick broad discovery.
- Use `search --cql '...'` when `find` misses or when you need precision such as constraining to a space, combining multiple conditions, or making the search reproducible.

Once `find` or `search` gives you a confident page match, stop searching and move to `info` or `read`. Do not keep running broader searches against the same title unless the resolved page looks wrong.

Read format choice:

- Prefer `read -f markdown` for tables, changelogs, weekly status pages, and other structured content.
- Prefer `read -f text` for prose pages where table fidelity does not matter.
- For long pages, pipe one read through local filters first, for example `... read 123456 -f markdown | sed -n '1,120p'` or `... read 123456 -f markdown | rg -n -C 2 'April 7|CHANGE-3285'`.
- Do not fetch the same large page in both text and markdown unless the first format is clearly insufficient.

Useful CQL example for generic scoped content search:

```bash
CONFLUENCE_READ_ONLY=true auth-runtime exec confluence -- \
  search --cql 'siteSearch ~ "Geneve Options" and space = "PROD"' -l 20
```

Prefer `export --format markdown` over `read -f markdown` when you need:

- a local markdown file on disk
- attachment download
- recursive descendant export
- predictable filesystem output for later processing

`spaces` is available, but it is usually noisier than `search` or `find`. Use it only when you actually need a broad inventory of accessible spaces.

## Markdown And Fidelity

Markdown support is useful, but it is not lossless.

- `read -f markdown` and `export --format markdown` are best-effort conversions for agent consumption.
- `create --format markdown` and `update --format markdown` are convenient for simple pages.
- For high-fidelity round-trips, use `edit <pageId> -o page.storage` to inspect current content, then update with `--format storage`.
- `convert` is local-only and useful for format experiments:

```bash
confluence convert \
  --input-file page.md \
  --input-format markdown \
  --output-format storage
```

If preserving Confluence structure matters more than markdown ergonomics, prefer storage format over markdown.

## Write Workflow

Only write after explicit user approval.

Common commands:

- `auth-runtime exec confluence -- create "Title" SPACE --file page.md --format markdown`
- `auth-runtime exec confluence -- create-child "Title" 123456 --file page.md --format markdown`
- `auth-runtime exec confluence -- update 123456 --file page.md --format markdown`
- `auth-runtime exec confluence -- update 123456 --file page.storage --format storage`
- `auth-runtime exec confluence -- move 123456 987654`

For writes:

1. Read the current state first with `info`, `read`, or `edit`.
2. Show the exact write command before running it.
3. Get user approval.
4. Do not include `CONFLUENCE_READ_ONLY=true` on the actual mutation.
5. Verify the result by rereading the page or running a targeted export.

## Safety

- Prefer `find` or `search` before using a guessed page ID.
- Use `--dry-run` before large recursive exports.
- Do not use `delete`, `comment-delete`, `attachment-delete`, or `move` without explicit confirmation.
- Do not assume markdown import/export is a clean round-trip.
- Surface CLI and runtime errors exactly instead of paraphrasing them away.
