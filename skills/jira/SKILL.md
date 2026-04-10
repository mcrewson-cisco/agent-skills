---
name: jira
description: Use when working with Jira tickets, issue keys such as PROJ-123, sprints, or boards through the local jira CLI, especially for viewing, searching, creating, assigning, commenting on, or transitioning issues.
---

# Jira

CLI-first Jira workflow for this Codex environment. Use `auth-runtime exec jira -- ...` for Jira CLI work.

## Preflight

Run this in order before any Jira work:

1. `auth-runtime exec jira -- me`

After readiness succeeds, capture that identity once and reuse it. Prefer `ME="$(auth-runtime exec jira -- me)"` or the literal email you already saw over nested readiness calls inside later Jira commands.

Do not require `JIRA_API_TOKEN` to be present in the Codex process. For ordinary Jira CLI work, use `auth-runtime exec jira -- ...` so the command runs in the same auth context as readiness checks.

If `auth-runtime exec jira -- me` fails, surface the exact auth/config error first. Distinguish these cases:

- Jira CLI auth failures after a token is present, such as `Unauthorized` or `x509`/server errors: surface the exact output.
- `auth-runtime resolve jira --no-refresh --format json`, `auth-runtime resolve jira --format value`, or `auth-runtime doctor jira --format json` failures: surface the exact runtime error first. Use `--no-refresh` when you only need to know whether an explicit token is already available without kicking refresh. If you still need an explicit token after that, run `auth-runtime refresh jira` once, retry the needed `auth-runtime` command once, then abandon that token path instead of looping.

Do not jump straight to raw `op read ...` from Codex. In this environment, `auth-runtime exec jira -- ...` is the Jira CLI path, and `auth-runtime` owns the reliable refresh and token-resolution path. `jira init` may still be required if the real CLI has never been configured.

For ordinary CLI reads, use `auth-runtime exec jira -- issue list`, `auth-runtime exec jira -- issue view`, or `auth-runtime exec jira -- issue view --raw`. Use `auth-runtime doctor jira --format json` only when you need diagnostics, and use `auth-runtime resolve jira --no-refresh --format json` only when you need to check explicit-token availability.

For CLI capability discovery such as `--help`, use `auth-runtime exec jira -- ... --help` when you want the command to run in the Jira execution context. If you only need diagnostics, prefer `auth-runtime doctor jira --format json`.

For person-centric reporting such as “what did Alex work on this past week?”, prefer `auth-runtime exec jira -- issue list -q ... --order-by updated --reverse` instead of embedding `ORDER BY` inside the JQL string. In this environment, CLI ordering flags are more reliable than `ORDER BY` inside `-q`.

## Sandbox and Approvals

Run narrow Jira reads in the sandbox first. If a command fails with a likely sandbox or network restriction, rerun that same command with `sandbox_permissions: "require_escalated"` and a short justification tied to the requested lookup.

For multi-step investigative reads, do not keep escalating one exact Jira read at a time. After the first likely sandbox/keychain failure on a read-only Jira task, request persistent approval for the narrow read-only families you are about to use, then stay inside those families for the rest of the investigation.

Typical read-only bundle for an investigative Jira session:

- `["auth-runtime", "exec", "jira", "--", "me"]`
- `["auth-runtime", "exec", "jira", "--", "issue", "view"]`
- `["auth-runtime", "exec", "jira", "--", "issue", "list"]`
- `["auth-runtime", "exec", "jira", "--", "issue", "search"]`
- `["auth-runtime", "resolve", "jira"]`

Use that pattern when the task is clearly going to involve multiple issue reads, raw views, JQL searches, or a Jira REST fallback. Do not request a broad prefix like `["auth-runtime", "exec", "jira"]`, because that would also cover Jira mutations.

For auth recovery, prefer this sequence:

1. `auth-runtime exec jira -- me`
2. `auth-runtime refresh jira`
3. `auth-runtime exec jira -- me`

Run `auth-runtime refresh jira` in the sandbox first. If that helper itself fails with a likely sandbox restriction, rerun that exact helper with `sandbox_permissions: "require_escalated"` and a narrow prefix rule for the helper path.

Do not apply the same sandbox-first rule to Jira mutations. In this environment, read-only Jira commands such as `auth-runtime exec jira -- me` and `auth-runtime exec jira -- issue view` may already be covered by approved unrestricted prefixes, while mutation commands are not. That means `auth-runtime exec jira -- me` succeeding does not prove a later `auth-runtime exec jira -- issue comment add`, `auth-runtime exec jira -- issue move`, or `auth-runtime exec jira -- issue assign` will work in the sandbox.

For Jira mutations, once you have:

1. read the current state
2. shown the exact mutation command
3. received user approval

run the exact mutation with `sandbox_permissions: "require_escalated"` immediately. Do not burn a first attempt on the sandbox and then retry the same mutation outside it.

For workflow transitions, remember that `auth-runtime exec jira -- issue move ...` cannot set arbitrary custom fields during the transition. If moving an issue to `Done` or another final state requires custom fields, populate those first with `auth-runtime exec jira -- issue edit ISSUE-KEY --custom ...`, then run the move command.

For `issue edit --custom`, do not guess with raw Jira field IDs like `customfield_11707`. In this environment, the `--custom` identifier comes from the custom field `name` in `~/.config/.jira/.config.yml`, normalized into a dash-separated lowercase token. Check that file first if the custom name is unclear.

When escalation is likely to be reused, include a narrow `prefix_rule` so the approval can persist. Prefer narrow prefixes such as:

- `["auth-runtime", "exec", "jira", "--", "me"]`
- `["auth-runtime", "exec", "jira", "--", "issue", "view"]`
- `["auth-runtime", "exec", "jira", "--", "issue", "list"]`
- `["auth-runtime", "exec", "jira", "--", "project", "list"]`
- `["auth-runtime", "exec", "jira", "--", "sprint", "list"]`
- `["auth-runtime", "refresh", "jira"]`

For mutations, keep the prefix rule narrow to the exact command family you are running. Good examples:

- `["auth-runtime", "exec", "jira", "--", "issue", "comment", "add"]`
- `["auth-runtime", "exec", "jira", "--", "issue", "assign"]`
- `["auth-runtime", "exec", "jira", "--", "issue", "move"]`
- `["auth-runtime", "exec", "jira", "--", "issue", "edit"]`

If the user approves persistence for one of those mutation prefixes, future sessions can avoid repeated sandbox failures and repeated approval prompts for that same write family.

Prefer command shapes that already match approved prefixes when they satisfy the request. In this environment, reach for these first:

- `auth-runtime exec jira -- me`
- `auth-runtime exec jira -- issue view ISSUE-KEY`
- `auth-runtime exec jira -- issue list ...`
- `auth-runtime exec jira -- issue search ...`
- `auth-runtime exec jira -- project list`
- `auth-runtime exec jira -- project view ...`
- `auth-runtime exec jira -- issue transitions ISSUE-KEY`
- `auth-runtime exec jira -- sprint list ...`

If one of those approved command families answers the question, use it instead of a broader or write-capable command. For example, prefer `auth-runtime exec jira -- issue view ISSUE-123` before trying to infer workflow state from a mutation command, and prefer `auth-runtime exec jira -- issue search ...` over jumping straight to browser-based exploration.

Do not burn approvals on `auth-runtime exec jira -- ... --help` when [commands.md](./references/commands.md) already covers the command family you need. Use `--help` once only when the reference is insufficient or you are confirming a suspected CLI capability gap before switching to Jira REST.

For person-centric activity questions, prefer the command/reference path over a capability check. Do not reach for `auth-runtime exec jira -- issue search --help` just to decide whether a cross-project query is possible; use the documented cross-project JQL pattern directly.

Do not request a broad prefix like `["auth-runtime"]`. Keep explicit approval for mutations such as `auth-runtime exec jira -- issue create`, `auth-runtime exec jira -- issue edit`, `auth-runtime exec jira -- issue move`, `auth-runtime exec jira -- issue assign`, `auth-runtime exec jira -- issue comment add`, and sprint-changing commands.

For explicit token tooling, prefer narrow read-only prefixes such as:

- `["auth-runtime", "doctor", "jira"]`
- `["auth-runtime", "resolve", "jira"]`

Use those only when the task actually needs Jira token diagnostics or a Jira API token. Do not use them as a default part of CLI-only investigation.

## Quick Reference

| Intent | Command |
|--------|---------|
| View issue | `auth-runtime exec jira -- issue view ISSUE-KEY` |
| List my issues | `ME="$(auth-runtime exec jira -- me)"; auth-runtime exec jira -- issue list -a"$ME"` |
| My in-progress | `ME="$(auth-runtime exec jira -- me)"; auth-runtime exec jira -- issue list -a"$ME" -s"In Progress"` |
| Create issue | `auth-runtime exec jira -- issue create -tTask -s"Summary"` |
| Create with body | `auth-runtime exec jira -- issue create -tTask -s"Summary" --template -` |
| Move/transition | `auth-runtime exec jira -- issue move ISSUE-KEY "State"` |
| Assign to me | `ME="$(auth-runtime exec jira -- me)"; auth-runtime exec jira -- issue assign ISSUE-KEY "$ME"` |
| Add comment | `auth-runtime exec jira -- issue comment add ISSUE-KEY "Comment text"` |
| Current sprint | `auth-runtime exec jira -- sprint list --state active --table --plain` |
| Open in browser | `auth-runtime exec jira -- open ISSUE-KEY` |

Issue keys usually match `[A-Z][A-Z0-9]+-[0-9]+`.

## Write Workflow

For any create, edit, move, assign, comment, link, or sprint mutation:

1. Read current state first with `auth-runtime exec jira -- issue view`, `auth-runtime exec jira -- sprint list`, or `auth-runtime exec jira -- project list`.
2. Show the exact command you plan to run.
3. Get user approval before the write.
4. Run the write outside the sandbox with `sandbox_permissions: "require_escalated"`.
5. Include a narrow `prefix_rule` for that exact mutation family when reuse is likely.
6. Verify the result after the write.

Use `--template -` or `--template /path/to/file` for multi-line descriptions and comments.

For unsupported CLI mutations that must fall back to Jira REST, use the same approval model:

1. Read the current state first.
2. Identify exact target IDs first for destructive operations such as comment deletion.
3. Show the exact REST command you plan to run.
4. Get user approval before the write.
5. Run the REST mutation outside the sandbox.
6. Verify by rereading the issue state, not just by trusting the HTTP status code.

Do not keep guessing at CLI syntax after one clear capability check. If `auth-runtime exec jira -- ... --help` shows the operation is unsupported, switch to the REST path after approval instead of burning turns on more help attempts.

For Jira REST in this environment:

- use Atlassian basic auth with `curl -u "$JIRA_LOGIN:$JIRA_API_TOKEN"`, not `Authorization: Bearer ...`
- do not waste a turn on `which auth-runtime` unless command resolution itself is in doubt
- if you only need to know whether a cached or exported token is already available, probe with `auth-runtime resolve jira --no-refresh --format json`
- obtain the token explicitly for that command with `JIRA_API_TOKEN="$(auth-runtime resolve jira --no-refresh --format value)"`; the Jira CLI exec path does not export credentials into `curl`
- prefer login/account values from the Jira CLI or environment when available
- keep destructive REST calls scoped to exact IDs
- if the no-refresh token path fails and the REST path is still required, run `auth-runtime refresh jira` once, then retry with `auth-runtime resolve jira --format value` once
- if that retry still fails, stop retrying and either surface the blocked REST path or fall back to the Jira CLI path when it can still answer the question
- avoid broad or generic `curl` prefix approvals; if this pattern becomes common, add a single-purpose local helper instead
- if you already proved that `jira --raw` does not expose the needed data shape in this environment, stop probing and go straight to the REST path

## Safety

- Do not assume transition names are universal. Check the current issue and project workflow first.
- Do not overwrite a description without showing the current and proposed content.
- Do not bulk-modify tickets without explicit approval.
- Assignee values must be exact matches for the Jira instance.
- Surface auth and config failures exactly as returned by the CLI.

## Deep Dive

Load `references/commands.md` when working with:

- multi-line issue bodies or comments
- JQL searches
- linking issues
- sprint commands beyond a simple list
- auth or CLI troubleshooting
- CLI capability gaps or REST fallbacks such as unsupported comment deletion

Load `references/nat-project-issue-creation.md` when working in the `NAT` project, especially when creating or editing issues that may require project-specific custom fields.
