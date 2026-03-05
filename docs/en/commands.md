# Commands

## Command System
- Slash commands only.
- Command group: `/schema`.

## Invoker Requirements (All Commands)
- Command invoker must have guild `Administrator` permission.
- Non-administrator invokers are rejected before any diff/apply planning.
- This restriction applies to `/schema export`, `/schema diff`, and `/schema apply`.

## Public Command Interface
1. `/schema export`
2. `/schema diff file:<attachment>`
3. `/schema apply file:<attachment>`

## `/schema export`
Purpose: export current guild structure to schema YAML.

Input:
- No attachment input.

Output:
- YAML attachment (`guild-schema.yaml`).
- Optional short Markdown summary.

Required bot permissions:
- `View Channels`
- `Read Message History`
- `Send Messages`
- `Attach Files`
- `Use Application Commands`

## `/schema diff file:<attachment>`
Purpose: compare uploaded schema against current guild and display diff.

Input:
- One YAML attachment.

Output:
- Markdown summary.
- Detailed change table (Create/Update/Delete/Move/Reorder).

Behavior:
- No mutating operations.
- Invalid schema returns validation error with field path.

## `/schema apply file:<attachment>`
Purpose: preview and apply schema changes with confirmation.

Input:
- One YAML attachment.

Workflow:
1. Parse and validate file.
2. Compute diff and show preview.
3. Show confirmation button with TTL (default 10 minutes).
4. Only the command invoker can confirm.
5. On confirm, create backup and execute apply plan.
6. Return final result report.

Output:
- Pre-confirmation: Markdown preview + confirmation UI.
- Post-confirmation: backup attachment + apply report.

Execution rules:
- Delete actions are never executed without confirmation.
- Expired confirmation button returns timeout message and requires rerun.
- Any apply request without diff changes returns no-op summary.

## Response Shape Contracts
- Diff output model:
  - `summary`
  - `changes[]` with `action`, `target_type`, `target_id`, `before`, `after`, `risk`
- Apply output model:
  - `backup_file`
  - `applied[]`
  - `failed[]`
  - `skipped[]`
