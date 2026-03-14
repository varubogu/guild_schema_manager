# Commands

## Command System
- Slash commands only.
- Command group: `/schema`.
- Runtime implementation: `SchemaCog` (`src/bot/cogs/commands.py`) + `SchemaCommandService` (`src/bot/usecases/schema/service.py`).

## Invoker Requirements (All Commands)
- Command invoker must have guild `Administrator` permission.
- Non-administrator invokers are rejected before any diff/apply planning.
- This restriction applies to `/schema export`, `/schema diff`, and `/schema apply`.

## Response Language
- User-facing messages are localized per invoker locale.
- If user locale is Japanese (`ja`), responses are shown in Japanese.
- Any non-Japanese locale is treated as English (`en`).
- Localization applies to command descriptions, button labels, confirmation prompts, errors, and diff/apply Markdown headings/status labels.

## Public Command Interface
1. `/schema export`
2. `/schema diff file:<attachment> file_trust_mode:<bool=false>`
3. `/schema apply file:<attachment> file_trust_mode:<bool=false>`

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
- Role `bot_managed` is exported only when `include_other_settings=true`.
- Category/channel role-target overwrites are exported only when `include_role_overwrites=true`.
- Member-target overwrites and remaining attributes (`type`, `position`, `topic`, `hoist`, etc.) are exported only when `include_other_settings=true`.

Output:
- YAML attachment (`{guild.name}-{yyyyMMdd_HHmmss}.yaml`).
- Optional short Markdown summary.
- If `SCHEMA_HINT_URL_TEMPLATE` is set, prepend YAML schema hint comment:
  - `# yaml-language-server: $schema=<resolved URL>`
  - `{version}` in `SCHEMA_HINT_URL_TEMPLATE` is replaced with schema version.
- If any export field option is disabled, the output is a filtered view. For `/schema diff` and `/schema apply`, omitted sections/fields are treated as keep-current.

Required bot permissions:
- `View Channels`

## `/schema diff file:<attachment>`
Purpose: compare uploaded schema against current guild and display diff.

Input:
- One YAML attachment.
- Optional boolean parameter:
  - `file_trust_mode` (default: `false`)

Output:
- Markdown summary (inline when short).
- Downloadable diff result file (`{guild.name}-{yyyyMMdd_HHmmss}_diff.md`) containing full details.

Behavior:
- No mutating operations.
- Structural schema problems (for example unknown keys or unsupported channel types) return validation error with field path.
- Ambiguous name matches are treated as differences so comparison can continue.
- Channel name matching uses parent scope + channel type + name. If still ambiguous, deterministic internal temporary ordering is used.
- `file_trust_mode=false`: uploaded file is merged as partial patch; omitted sections/entities/fields are kept from current guild state.
- `file_trust_mode=false`: resources existing in guild but omitted from uploaded file are shown as `No change (undefined in file)`.
- Resources defined in both guild and uploaded file and fully equal are shown as `No change (exact match)`.
- `file_trust_mode=true`: uploaded file is parsed as full schema source-of-truth; omitted resources become delete diffs.
- If uploaded `guild.id` is present and differs from the current guild, the bot asks whether to overwrite it to the current guild ID before continuing.
- If that confirmation is cancelled or times out, the command is aborted.

## `/schema apply file:<attachment>`
Purpose: preview and apply schema changes with confirmation.

Input:
- One YAML attachment.
- Optional boolean parameter:
  - `file_trust_mode` (default: `false`)

Workflow:
1. Parse uploaded file and check `guild.id` mismatch.
2. If mismatch is detected, ask whether to overwrite `guild.id` to the current guild.
3. Parse and validate file.
4. Compute diff and show preview.
5. Show confirmation button with TTL (default 10 minutes).
6. Only the command invoker can confirm.
7. On confirm, create backup and execute apply plan.
8. Return final result report.

Output:
- Pre-confirmation: Markdown preview (inline when short) + preview file attachment (`{guild.name}-{yyyyMMdd_HHmmss}_apply.md`) + confirmation UI.
- Post-confirmation: backup attachment + apply report file attachment (`{guild.name}-{yyyyMMdd_HHmmss}_apply.md`).

Execution rules:
- Delete actions are never executed without confirmation.
- `file_trust_mode=false`: omitting roles/categories/channels from upload does not generate delete actions.
- `file_trust_mode=true`: omission in uploaded full schema generates delete actions.
- If uploaded `guild.id` differs and the override confirmation is cancelled or timed out, apply does not proceed.
- If uploaded `guild.id` differs and override confirmation is approved, roles/categories/channels matching is handled in name-first mode for that request (no ID fallback).
- After confirmation, channel delete targets are moved to `GSM-Dustbox` instead of hard-deleted.
- For category delete targets, child channels are moved to `GSM-Dustbox` and the category is archived for manual cleanup.
- `GSM-Dustbox` is created with admin-only visibility if it does not exist.
- Role delete targets are reported for manual deletion (no hard delete by bot).
- Role operations (`Create`/`Update`/`Delete`/`Reorder`) where `bot_managed=true` are excluded from execution and reported as `skipped[]` with reason `bot_managed_role`.
- Expired confirmation button returns timeout message and requires rerun.
- Any apply request without diff changes returns no-op summary.

## Response Shape Contracts
- Diff output model:
  - `summary`
  - `changes[]` with `action`, `target_type`, `target_id`, `before_name`, `after_name`, `before`, `after`, `risk`
  - `informational_changes[]` with `action`, `target_type`, `target_id`, `before_name`, `after_name`, `before`, `after`
- Apply output model:
  - `backup_file`
  - `applied[]`
  - `failed[]`
  - `skipped[]`
