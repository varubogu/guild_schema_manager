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
- Optional boolean parameters:
  - `include_name` (default: `true`)
  - `include_permissions` (default: `true`)
  - `include_role_overwrites` (default: `true`)
  - `include_other_settings` (default: `true`)

Field behavior:
- `id` is always exported.
- `name` is exported only when `include_name=true`.
- Role `permissions` are exported only when `include_permissions=true`.
- Category/channel role-target overwrites are exported only when `include_role_overwrites=true`.
- Member-target overwrites and remaining attributes (`type`, `position`, `topic`, `hoist`, etc.) are exported only when `include_other_settings=true`.

Output:
- YAML attachment (`guild-schema.yaml`).
- Optional short Markdown summary.
- If `SCHEMA_REPO_OWNER` and `SCHEMA_REPO_NAME` are set, prepend YAML schema hint comment:
  - `# yaml-language-server: $schema=https://<owner>.github.io/<repo>/schema/v<version>/schema.json`
- If any export field option is disabled, the output is a filtered view and may fail schema validation for `/schema diff` and `/schema apply`.

Required bot permissions:
- `View Channels`

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
- After confirmation, channel delete targets are moved to `GSM-Dustbox` instead of hard-deleted.
- For category delete targets, child channels are moved to `GSM-Dustbox` and the category is archived for manual cleanup.
- `GSM-Dustbox` is created with admin-only visibility if it does not exist.
- Role delete targets are reported for manual deletion (no hard delete by bot).
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
