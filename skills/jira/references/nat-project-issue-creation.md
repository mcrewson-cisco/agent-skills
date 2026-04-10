# NAT Project Issue Creation

Use this reference when creating or editing issues in the `NAT` Jira project.

## Why NAT Differs

The generic `auth-runtime exec jira -- issue create` flow is often not enough for `NAT`. This project can require additional custom fields on create, and the Jira CLI path may fail to set those fields non-interactively even when the field names and field IDs are known.

This is not limited to sub-tasks. Treat it as general NAT issue-creation guidance.

## NAT Custom Fields

### Task Type

- display name: `Task Type`
- field key: `customfield_11703`
- field type: option
- context id: `12020`

Known options:

| Option ID | Value |
|-----------|-------|
| `13697` | `Break/Fix` |
| `13698` | `Design` |
| `13699` | `Deployment` |
| `13700` | `Development` |
| `13701` | `Documentation` |
| `13702` | `Monitors` |
| `13703` | `Service Request` |
| `13704` | `Spike` |
| `13705` | `Testing` |
| `13706` | `Unit Testing` |
| `13707` | `Other` |

Related freeform field when needed:

- display name: `Other Task Type`
- field key: `customfield_11704`
- field type: string

### Programming Language

- display name: `Programming Language`
- field key: `customfield_11705`
- field type: option
- context id: `12025`

Known options:

| Option ID | Value |
|-----------|-------|
| `13717` | `C` |
| `13718` | `C++` |
| `13719` | `Groovy` |
| `13720` | `HCL` |
| `13721` | `Java` |
| `13722` | `Javascript` |
| `13723` | `Python` |
| `13724` | `PHP` |
| `13725` | `SQL` |
| `13726` | `TypeScript` |
| `13727` | `Other` |

Related freeform field when needed:

- display name: `Other Programming Language`
- field key: `customfield_11706`
- field type: string

Use `Programming Language = Other` plus `Other Programming Language = <value>` when the language is not present in the option list. For example, recent NAT Go work used:

- `customfield_11705 = Other`
- `customfield_11706 = Go`

## Recommended NAT Create Workflow

1. Run the normal Jira preflight:
   - `auth-runtime exec jira -- me`
2. Read a nearby NAT issue first to confirm parentage, issue type, and any required fields:
   - `auth-runtime exec jira -- issue view NAT-XXXX`
   - `auth-runtime exec jira -- issue view NAT-XXXX --raw`
3. Draft the description into a temp file and show the user the exact create command before any write.
4. Expect `auth-runtime exec jira -- issue create` to fail if NAT-specific required fields are enforced and the CLI cannot set them.
5. If the CLI cannot create the issue cleanly, fall back to Jira REST API creation.
6. Verify the created issue's key, parent when applicable, issue type, and required custom fields.

## Known CLI Limitation

In this environment, `auth-runtime exec jira -- issue create --custom ...` may reject both:

- display-name syntax such as `--custom "Task Type=Development"`
- field-key syntax such as `--custom customfield_11703=Development`

When that happens, do not keep guessing at `jira` CLI syntax. Move to the REST API path after user approval.

## REST API Fallback

Use the Jira server URL and login from the local Jira CLI config:

- config file: `/Users/mcrewson/.config/.jira/.config.yml`
- server key: `server`
- login key: `login`

POST to:

`https://cisco-sbg.atlassian.net/rest/api/3/issue`

Build the payload with the fields you actually need. Typical shapes:

- option field: `"customfield_11703": { "id": "13700" }`
- freeform field: `"customfield_11706": "Go"`

Use ADF (`type: doc`, `version: 1`) for the description body.

For REST calls, obtain the token explicitly for that command with `auth-runtime resolve jira --no-refresh --format value` instead of assuming `JIRA_API_TOKEN` is already exported in the Codex process.

Example create pattern:

```bash
JIRA_API_TOKEN="$(auth-runtime resolve jira --no-refresh --format value)"

curl -sS \
  -u "$JIRA_LOGIN:$JIRA_API_TOKEN" \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -X POST \
  --data @/tmp/nat-issue.json \
  https://cisco-sbg.atlassian.net/rest/api/3/issue
```

Read `JIRA_LOGIN` from the local Jira config instead of hardcoding it when possible.
If you only need to check token availability first, use `auth-runtime resolve jira --no-refresh --format json`.
If the no-refresh token path fails and the REST call is still required, run `auth-runtime refresh jira` once, then retry with `auth-runtime resolve jira --format value`.

## Verification

After any NAT issue create or edit:

1. Read the issue back immediately.
2. Confirm:
   - issue key
   - summary
   - parent link when applicable
   - issue type
   - relevant `customfield_11703` / `customfield_11704`
   - relevant `customfield_11705` / `customfield_11706`
3. Share the Jira browse URL in the final response.

## Practical Rule

For `NAT` issue creation:

- try the normal `auth-runtime exec jira -- issue create` workflow first if the required fields are likely simple
- if NAT required-field handling starts to loop, switch to REST API creation instead of burning turns on CLI syntax experiments
