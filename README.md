# Guild Schema Manager

Discord bot to manage guild structure as YAML files, with explicit confirmation before any mutation.

## What You Can Do
1. Export current guild config to YAML (`/schema export`).
2. Compare an uploaded YAML file to current guild state (`/schema diff file:<attachment>`).
3. Preview and apply changes from YAML with invoker-only confirmation (`/schema apply file:<attachment>`).

Managed resources:
- Roles
- Categories
- Channels
- Permission overwrites on categories/channels

## Safety Model (Always Enforced)
- No database.
- No persistent server-side schema storage.
- No bot `Administrator` permission.
- Only guild administrators can execute `/schema` commands.
- Apply is always `preview -> confirmation -> backup -> execute -> report`.
- Confirmation is invoker-only.
- Full backup export is mandatory before every apply execution.

Delete behavior on apply:
- Channel deletes are converted to move into `GSM-Dustbox`.
- Category deletes move child channels to `GSM-Dustbox`, then archive category for manual cleanup.
- Role deletes are reported for manual deletion (no hard delete by bot).

## Quick Start (Local)
Prerequisites:
- Python `3.11+`
- `uv`

1. Install dependencies.
```bash
uv sync
```

2. Create env file.
```bash
cp .env.example .env
```

3. Set required values in `.env`.
- `DISCORD_TOKEN` (required)
- `APPLICATION_ID` (required)
- `LOG_LEVEL` (optional, default `INFO`)
- `CONFIRM_TTL_SECONDS` (optional, default `600`)
- `SCHEMA_REPO_OWNER` (optional)
- `SCHEMA_REPO_NAME` (optional)

4. Run bot.
```bash
uv run python -m bot
```

5. Use slash commands in your guild.
- `/schema export`: Export current guild configuration to `guild-schema.yaml` (baseline/backup).
- `/schema diff file:<attachment>`: Validate uploaded YAML and show Create/Update/Delete/Move/Reorder differences without mutating anything.
- `/schema apply file:<attachment>`: Show preview, require invoker-only confirmation, take mandatory full backup, then execute and report `applied[]`, `failed[]`, and `skipped[]`.
- Detailed command contract: `docs/en/commands.md`

## Discord Setup Checklist
1. Create a Discord application and bot user.
2. Enable scopes:
- `bot`
- `applications.commands`
3. Grant only minimum bot permissions:
- `Manage Roles`
- `Manage Channels`
- `View Channels`

## First Practical Workflow
1. Run `/schema export` and download `guild-schema.yaml`.
2. Edit YAML (roles/categories/channels/overwrites).
3. Run `/schema diff file:<edited yaml>` and review risk labels.
4. Run `/schema apply file:<edited yaml>`.
5. Confirm with the button as the same invoker within TTL (default: 10 minutes).
6. Review final report sections:
- `applied[]`
- `failed[]`
- `skipped[]`
7. Keep returned `guild-schema-backup.yaml` as rollback baseline.

## Minimal YAML Shape
```yaml
version: 1
guild:
  id: "123456789012345678"
  name: "Example Guild"
roles: []
categories: []
channels: []
```

Unknown keys and unsupported channel types are validation errors.

## Development Commands
Run tests:
```bash
uv run pytest
```

type checking, format, and lint:
```bash
uv run pyright
uv run ruff format
uv run ruff check
```

## Docs Index
- Product docs (canonical): `docs/en/*`
- Japanese mirror docs: `docs/ja/*`
- Entry points:
  - `docs/en/README.md`
  - `docs/en/commands.md`
  - `docs/en/schema.md`
  - `docs/en/diff-and-apply.md`
  - `docs/en/permissions-and-security.md`
  - `docs/en/deployment.md`
