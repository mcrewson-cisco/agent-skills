# Commands Reference

Reference for Jira CLI execution in this environment.

## Preflight

```bash
auth-runtime exec jira -- me
```

If `auth-runtime exec jira -- me` fails, the session is not ready for live Jira work yet. In this environment, recover auth with:

```bash
auth-runtime refresh jira
auth-runtime exec jira -- me
```

Only bring in `auth-runtime doctor jira --format json` or `auth-runtime resolve jira --no-refresh --format json` when you actually need diagnostics or an explicit token for Jira REST or a packaged helper script. For ordinary CLI reads, stay on `auth-runtime exec jira -- ...`.
If you only need to know whether a token is already available without kicking refresh, use:

```bash
auth-runtime resolve jira --no-refresh --format json
```

After `auth-runtime exec jira -- me` succeeds, capture the identity once and reuse it:

```bash
ME="$(auth-runtime exec jira -- me)"
auth-runtime exec jira -- issue list -a"$ME" --updated today --order-by updated --reverse
```

Avoid nested `$(auth-runtime exec jira -- me)` in later commands when you already know the answer.

If the first Jira read in a session fails with a likely sandbox/keychain restriction and the task is clearly investigative, do not request approval command-by-command. Ask for persistent approval for the narrow read-only families you will reuse:

```text
["auth-runtime", "exec", "jira", "--", "me"]
["auth-runtime", "exec", "jira", "--", "issue", "view"]
["auth-runtime", "exec", "jira", "--", "issue", "list"]
["auth-runtime", "exec", "jira", "--", "issue", "search"]
["auth-runtime", "resolve", "jira"]
```

Do not request `["auth-runtime", "exec", "jira"]`, because that would also cover writes.

## Capability Discovery

If you only need local help text or command-shape discovery, prefer the Jira exec path so the command runs in the same auth context as normal CLI work.

Pattern:

```bash
auth-runtime exec jira -- issue comment --help
```

Use this once to confirm whether a subcommand exists. If the real CLI help shows the operation is unsupported, stop probing and move to the REST fallback after user approval.

Do not spend approvals on `--help` when this reference already answers the command shape you need.

## Viewing Issues

```bash
auth-runtime exec jira -- issue view ISSUE-KEY
auth-runtime exec jira -- issue view ISSUE-KEY --comments 5
auth-runtime exec jira -- issue view ISSUE-KEY --raw
```

## Listing Issues

```bash
auth-runtime exec jira -- issue list
ME="$(auth-runtime exec jira -- me)"
auth-runtime exec jira -- issue list -a"$ME"
auth-runtime exec jira -- issue list -a"$ME" -s"In Progress"
auth-runtime exec jira -- issue list -sDone
auth-runtime exec jira -- issue list -tBug
auth-runtime exec jira -- issue list -yHigh
auth-runtime exec jira -- issue list -lurgent -lbug
auth-runtime exec jira -- issue list "login error"
auth-runtime exec jira -- issue list --history
auth-runtime exec jira -- issue list --watching
auth-runtime exec jira -- issue list --created today
auth-runtime exec jira -- issue list --updated -2d
auth-runtime exec jira -- issue list --plain --no-headers
auth-runtime exec jira -- issue list --plain --columns key,summary,status,assignee
auth-runtime exec jira -- issue list -q"status = 'In Progress' AND assignee = currentUser()"
auth-runtime exec jira -- issue list --paginate 20
auth-runtime exec jira -- issue list --paginate 10:50
```

For stable ordering in this environment, prefer CLI flags over `ORDER BY` inside the JQL string:

```bash
auth-runtime exec jira -- issue list -q 'assignee = currentUser() AND updated >= "2026-04-01"' --order-by updated --reverse --plain --columns key,summary,status,updated
```

Avoid embedding `ORDER BY` inside `-q` unless you have evidence the target command shape accepts it cleanly.

For person-centric activity questions like “what did Alex work on this week?”:

1. If the question is clearly about a person rather than only the current project, start with a cross-project query instead of NAT-only and only narrow later if needed.
2. Use assignment-based results first as the default meaning of “worked on.”
3. Use strict done-state or resolved queries second if the user asks how much was completed.
4. Only escalate to comment/transition/changelog history if the user asks for a stronger definition than “assigned and updated.”

Patterns:

```bash
auth-runtime exec jira -- issue list -q 'project IS NOT EMPTY AND assignee = "Alex Giunta" AND updated >= "2026-03-28"' --order-by updated --reverse --plain --columns key,summary,status,updated

auth-runtime exec jira -- issue list -q 'project IS NOT EMPTY AND assignee = "Alex Giunta" AND statusCategory = Done AND updated >= "2026-03-28"' --order-by updated --reverse --plain --columns key,summary,status,updated
```

Do not spend a turn on `auth-runtime exec jira -- issue search --help` just to determine whether this style of query is possible. Use the documented query shape directly.

## Creating Issues

```bash
auth-runtime exec jira -- issue create
auth-runtime exec jira -- issue create -tBug -s"Login button not working" -b"Users cannot click the login button on Safari" -yHigh -lbug -lurgent
ME="$(auth-runtime exec jira -- me)"
auth-runtime exec jira -- issue create -tTask -s"Summary" -a"$ME"
auth-runtime exec jira -- issue create -tSub-task -P"PROJ-123" -s"Subtask summary"
auth-runtime exec jira -- issue create -tStory -s"Summary" --custom story-points=3
auth-runtime exec jira -- issue create -tTask -s"Quick task" --no-input
auth-runtime exec jira -- issue create -tBug -s"Bug title" --web
auth-runtime exec jira -- issue create -tStory -s"Summary" --template /path/to/template.md
printf 'Description here\n' | auth-runtime exec jira -- issue create -tTask -s"Summary" --template -
```

From Codex, treat create/edit/move/assign/comment/link/sprint commands as host-side mutations: after the user approves the exact command, run that exact mutation outside the sandbox with `auth-runtime exec jira -- ...` instead of trying it in the sandbox first.

For larger or multi-line bodies, prefer stdin or `--template` over long inline shell strings:

```bash
printf '%s\n' \
  '## Description' \
  'User needs ability to export data.' \
  '' \
  '## Acceptance Criteria' \
  '- Export works for CSV' \
  '- Export works for JSON' \
  | auth-runtime exec jira -- issue create --no-input -pPROJ -tStory -s"Add export functionality" --template -
```

## Transitioning Issues

```bash
auth-runtime exec jira -- issue move ISSUE-KEY "In Progress"
auth-runtime exec jira -- issue move ISSUE-KEY "Done"
auth-runtime exec jira -- issue move ISSUE-KEY "Done" --comment "Completed the implementation"
auth-runtime exec jira -- issue move ISSUE-KEY "Done" -R"Fixed"
auth-runtime exec jira -- issue move ISSUE-KEY "In Review" -a"reviewer@example.com"
auth-runtime exec jira -- issue move ISSUE-KEY "Done" --web
```

`jira issue move` does not support setting arbitrary custom fields during the transition. If the target workflow state requires custom fields, set them first with `issue edit`, then move the issue.

Pattern:

```bash
auth-runtime exec jira -- issue edit ISSUE-KEY \
  --custom total-effort-days=0.5 \
  --custom copilot-days-saved=0 \
  --no-input

auth-runtime exec jira -- issue move ISSUE-KEY Done --comment "Completed the work"
```

The `--custom` identifiers are derived from the custom field `name` entries in `~/.config/.jira/.config.yml`, not from raw Jira field IDs like `customfield_11707`.

## Assigning Issues

```bash
auth-runtime exec jira -- issue assign ISSUE-KEY "user@example.com"
auth-runtime exec jira -- issue assign ISSUE-KEY "John Doe"
ME="$(auth-runtime exec jira -- me)"
auth-runtime exec jira -- issue assign ISSUE-KEY "$ME"
auth-runtime exec jira -- issue assign ISSUE-KEY default
auth-runtime exec jira -- issue assign ISSUE-KEY x
```

## Comments

```bash
auth-runtime exec jira -- issue comment add ISSUE-KEY "This is my comment"
auth-runtime exec jira -- issue comment add ISSUE-KEY --template /path/to/comment.md
printf 'Comment from stdin\n' | auth-runtime exec jira -- issue comment add ISSUE-KEY --template -
```

For repeated comment work, use a narrow persistent approval when available:

```text
prefix_rule: ["auth-runtime", "exec", "jira", "--", "issue", "comment", "add"]
```

The installed `jira-cli` here supports comment add. If comment delete is requested, confirm with `auth-runtime exec jira -- issue comment --help` once, then switch to the Jira REST delete endpoint instead of guessing CLI syntax.

Comment delete pattern:

1. Read the issue first.
2. Get exact comment IDs from `auth-runtime exec jira -- issue view ISSUE-KEY --raw`.
3. Show the exact delete call(s).
4. Get user approval.
5. Run the delete call(s) outside the sandbox.
6. Read the issue back to verify the comment count and IDs changed as expected.

REST delete example:

```bash
JIRA_LOGIN="$(auth-runtime exec jira -- me)"
JIRA_API_TOKEN="$(auth-runtime resolve jira --no-refresh --format value)"

curl -sS \
  -o /tmp/jira-comment-delete.out \
  -w "%{http_code}" \
  -X DELETE \
  -u "$JIRA_LOGIN:$JIRA_API_TOKEN" \
  -H "Accept: application/json" \
  "https://cisco-sbg.atlassian.net/rest/api/3/issue/ISSUE-KEY/comment/COMMENT_ID"
```

Expected success code for delete: `204`

Do not use `Authorization: Bearer ...` for this Jira token path unless you have separate evidence that the target API expects it. In this environment, the working REST pattern is Atlassian-style basic auth with email/login plus API token.
If you only need a token availability probe first, use `auth-runtime resolve jira --no-refresh --format json`.
If the no-refresh token path fails, run `auth-runtime refresh jira` once, then retry `auth-runtime resolve jira --format value` once if the delete is still required.
If that retry still fails, stop retrying the REST path and report that the explicit token flow is blocked.

For read-heavy history/tree questions, once you have established that `auth-runtime exec jira -- issue view --raw` does not include the needed changelog or relationship data, stop poking at `jq` over the same raw payload and switch to the Jira REST path immediately.

For multiple comment deletions, keep the request narrowly scoped to the exact comment IDs the user asked to remove. Do not bulk-delete comments by pattern matching or author unless the user explicitly asked for that.

## REST Fallback Pattern

When the `jira` CLI does not support the requested mutation cleanly:

1. confirm the CLI gap once with `auth-runtime exec jira -- ... --help` or a documented limitation
2. switch to Jira REST instead of looping on CLI guesses
3. use basic auth with login plus API token
4. run the REST mutation outside the sandbox after approval
5. verify by rereading the issue state

## Sprints

```bash
auth-runtime exec jira -- sprint list
auth-runtime exec jira -- sprint list --state active
auth-runtime exec jira -- sprint list --state active --table --plain
auth-runtime exec jira -- sprint add SPRINT-ID ISSUE-KEY
auth-runtime exec jira -- sprint close SPRINT-ID
```

## Linking Issues

```bash
auth-runtime exec jira -- issue link PROJ-123 PROJ-456 Relates
auth-runtime exec jira -- issue link PROJ-100 PROJ-200 Blocks
auth-runtime exec jira -- issue link PROJ-EPIC PROJ-STORY Epic-Story
```

## Other Commands

```bash
auth-runtime exec jira -- open ISSUE-KEY
auth-runtime exec jira -- me
auth-runtime exec jira -- serverinfo
auth-runtime exec jira -- project list
auth-runtime exec jira -- board list
```
