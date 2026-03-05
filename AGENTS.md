# AGENTS.md

## Agent Communication Policy
- Respond to user requests in Japanese by default.
- If the user explicitly requests another language, follow the user request for that response.

## Mission
Build and maintain a Discord Server Schema Manager Bot that can export, diff, and apply guild configuration from file input with explicit confirmation controls.

## Canonical Documentation Map
- Primary docs: `docs/en/*`
- Mirror docs: `docs/ja/*`
- Both language sets must remain functionally equivalent.

## Non-Negotiable Constraints
- No database usage.
- No persistent server-side configuration storage.
- No `Administrator` permission.
- Bot command execution is restricted to guild administrators only.
- Confirmation is required before any apply mutation.
- Confirmation is invoker-only.
- A full backup export is mandatory before every apply execution.

## Product Scope Baseline
- Managed resources: roles, categories, channels.
- Permission overwrites on categories and channels are in scope.
- Slash commands only:
  - `/schema export`
  - `/schema diff file:<attachment>`
  - `/schema apply file:<attachment>`

## Implementation Conventions
- Language/runtime: Python.
- Discord SDK: `discord.py`.
- Dependency and task runner: `uv`.
- Testing: `pytest`.
- Production packaging: Docker.

## Suggested Module Boundaries
- `bot/commands/`: slash command handlers.
- `bot/schema/`: YAML model and validation.
- `bot/snapshot/`: guild state normalization.
- `bot/diff/`: change detection logic.
- `bot/planner/`: ordered apply plan generation.
- `bot/executor/`: Discord mutation execution.
- `bot/security/`: permission and invoker checks.
- `bot/rendering/`: markdown and file outputs.

## Safe Change Policy
- Preserve hard security constraints exactly.
- Enforce administrator-only access checks for every `/schema` command.
- Do not introduce background sync or silent auto-apply behavior.
- Keep apply flow as preview -> confirmation -> backup -> execute -> report.
- Treat unknown schema keys and unsupported channel types as validation errors.

## Test Expectations
- Add or update tests with every behavior change.
- Cover administrator-only command access guard.
- Cover ID-first matching semantics.
- Cover invoker-only confirmation guard.
- Cover mandatory backup behavior.
- Cover partial failure reporting (`applied[]`, `failed[]`, `skipped[]`).

## Rules for Editing Docs
- Keep `docs/en` as canonical source of truth.
- Keep `docs/ja` synchronized for any semantic change.
- Update command and schema docs together when interfaces change.
- Preserve security constraints text verbatim in both languages where applicable.
