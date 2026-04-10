---
name: op
description: Use when reading secrets, passwords, API keys, item metadata, or OTP codes from 1Password with the local op CLI.
---

# 1Password CLI (`op`)

Use this skill to retrieve the minimum 1Password data the user asked for.

## User Request

$ARGUMENTS

## Preflight

1. Verify that `op` can perform the kind of request you need. Use the narrowest low-risk command that matches the task.
   ```bash
   op vault list --format=json
   ```
2. Run `op` commands in the sandbox first. If a command fails with a likely sandbox or desktop-app access error such as `couldn't connect to the 1Password desktop app`, rerun that same narrow command with `sandbox_permissions: "require_escalated"` and a short justification tied to the requested lookup.
3. Do not rely on `op whoami` as the auth gate. It can report `account is not signed in` even when other `op` commands still work in the current shell.
4. If the preflight command needed for the requested operation still fails after the escalated retry, stop and tell the user `op` is not available in this session. Do not guess or continue.
5. If multiple accounts may be in scope, confirm the target account and use `--account` or `OP_ACCOUNT`.
6. For service accounts, item commands require `--vault`.

## Safe Workflow

1. Discover vaults when needed:
   ```bash
   op vault list --format=json
   ```
2. Keep escalated retries narrow. Re-run only the specific `op` command you need next; do not broaden the query just because the first attempt needed escalation.
3. If the user did not name a vault and multiple vaults are plausible, ask before retrieving secrets.
4. If the user needs to find an item, list narrowly:
   ```bash
   op item list --vault "VAULT_NAME" --categories Login --format=json
   op item list --vault "VAULT_NAME" --tags production --format=json
   ```
5. For a specific secret value, prefer `op read`:
   ```bash
   op read "op://VAULT_NAME/Item Title/username"
   op read "op://VAULT_NAME/Item Title/password"
   op read "op://VAULT_NAME/Item Title/one-time password?attribute=otp"
   ```
6. Use `op item get` for metadata, field discovery, or full item details:
   ```bash
   op item get "Item Title" --vault "VAULT_NAME" --format=json
   op item get "Item Title" --vault "VAULT_NAME" --fields label=username --format=json
   op item get "Item Title" --vault "VAULT_NAME" --otp
   ```
7. Use `--reveal` only when the user explicitly wants concealed field values from `op item get` rather than a direct `op read`.

## Output Rules

- Return only what the user asked for.
- Prefer a single secret value over full item dumps.
- Do not echo unrelated fields, raw JSON, or extra secrets unless requested.
- If the lookup is ambiguous, ask for the missing vault, account, item, or field.
- For OTP requests, return just the current code.
- For metadata requests, summarize the useful fields instead of dumping the whole object unless the user asked for JSON.

## Quick Reference

```bash
op vault list --format=json
op item list --vault "VAULT_NAME" --format=json
op item get "Item Title" --vault "VAULT_NAME" --format=json
op read "op://VAULT_NAME/Item Title/field"
```
