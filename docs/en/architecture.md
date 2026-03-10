# Architecture

## Component Overview
Primary runtime components:
- Discord gateway/client layer (`discord.py`): receives slash commands and interactions.
- Command handlers: `export`, `diff`, `apply` orchestration.
- Schema parser/validator: parses YAML and validates structure/types.
- Snapshot builder: converts live guild objects into normalized schema model.
- Diff engine: computes Create/Update/Delete/Move/Reorder actions.
- Apply planner/executor: converts diff to ordered Discord API operations.
- Confirmation session store (in-memory): keeps short-lived pending apply plans.
- Result renderer: produces Markdown summaries and attachment outputs.

## Source Structure (Cog + UseCase)
- Runtime bootstrap and dependency wiring: `src/bot/app.py`
- Slash command cog: `src/bot/commands/cogs/schema_cog.py`
- Event cog (`on_ready`): `src/bot/commands/cogs/events_cog.py`
- Interaction views (invoker-only confirmation UI): `src/bot/commands/views/*`
- Interaction orchestration handlers: `src/bot/commands/handlers/schema_handlers.py`
- Localization translator and command metadata: `src/bot/commands/translator.py`
- Use case layer (command business logic): `src/bot/usecases/schema/service.py`
- Compatibility re-export for legacy imports: `src/bot/commands/service.py`

Dependency direction:
1. Cog / View layer (`commands/*`) handles Discord I/O only.
2. UseCase layer (`usecases/*`) executes export/diff/apply logic.
3. Domain modules (`schema`, `snapshot`, `diff`, `planner`, `executor`, `rendering`, `security`) provide pure processing and mutation primitives.

## Data Flow
### `/schema export`
1. Verify command invoker has guild administrator permission.
2. Read guild state (roles, categories, channels, overwrites).
3. Normalize into schema model.
4. Serialize to YAML.
5. Return YAML as attachment.

### `/schema diff file:<attachment>`
1. Verify command invoker has guild administrator permission.
2. Receive YAML attachment.
3. Validate schema.
4. Build current live snapshot.
5. Compute diff.
6. Return Markdown summary and detailed change table.

### `/schema apply file:<attachment>`
1. Verify command invoker has guild administrator permission.
2. Receive YAML attachment.
3. Validate schema.
4. Build live snapshot and compute diff.
5. Return preview + confirmation button (invoker-only).
6. On confirmation:
   - Export current state as backup attachment.
   - Execute ordered operations.
   - Return apply result report (`applied`, `failed`, `skipped`) with backup file.

## State Management
- No DB and no persistent disk state.
- Pending apply plans are stored in-memory with TTL (default: 10 minutes).
- Pending plans are invalidated on process restart.
- Uploaded files and generated temporary files are deleted after response lifecycle.

## Error Handling Policy
- Validation errors: reject with actionable message, no side effects.
- Authorization errors: reject non-administrator command invokers before planning.
- Permission errors: stop the failing operation and report exact missing permission.
- Partial failures during apply: continue best-effort for independent actions, then report per action result.
- Confirmation timeout: mark plan expired and require re-run of `/schema apply`.

## Discord API Constraints
- Handle rate limits by using `discord.py` built-in HTTP retry behavior and controlled operation pacing.
- Expect partial failures (deleted objects, hierarchy conflicts, role position limits).
- Preserve operation ordering:
  1. Roles
  2. Categories
  3. Channels
- Resolve parent-child dependencies before reorder operations.
