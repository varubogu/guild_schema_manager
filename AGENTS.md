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
- Implementation proposal/plan documents must use this fixed format:
  1. `Summary`
  2. `Implementation Changes`
  3. `Test Plan`
  4. `Assumptions and Defaults`

## Required Final Checks
- Every implementation task must run these commands before completion:
  1. `UV_CACHE_DIR=/tmp/uv-cache uv run --with pyright pyright`
  2. `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check`
  3. `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format`
  4. `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`
- Report the result of each command in the final response.
- If any check fails, do not claim completion; include failure details and remaining actions.

## Suggested Module Boundaries
- `src/bot/commands/`: slash command handlers.
- `src/bot/schema/`: YAML model and validation.
- `src/bot/snapshot/`: guild state normalization.
- `src/bot/diff/`: change detection logic.
- `src/bot/planner/`: ordered apply plan generation.
- `src/bot/executor/`: Discord mutation execution.
- `src/bot/security/`: permission and invoker checks.
- `src/bot/rendering/`: markdown and file outputs.

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
