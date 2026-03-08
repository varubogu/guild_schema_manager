# Deployment

## Technology Stack
- Python
- `discord.py`
- `uv`
- `ruff`
- `pytest`
- Docker (production runtime)

## Environment Variables
Minimum runtime variables:
- `DISCORD_TOKEN`: bot token.
- `APPLICATION_ID`: Discord application ID.
- `LOG_LEVEL`: optional (`INFO` default).
- `CONFIRM_TTL_SECONDS`: optional (`600` default).
- `SCHEMA_HINT_URL_TEMPLATE`: optional direct URL template used for `/schema export` schema hint.

If `SCHEMA_HINT_URL_TEMPLATE` is set, exported YAML includes:
- `# yaml-language-server: $schema=<resolved URL>`
- `{version}` in `SCHEMA_HINT_URL_TEMPLATE` is replaced with the schema version number.

## Local Development
Example flow:
1. Install `uv`.
2. Create environment and install dependencies.
3. Run formatting and lint checks with `ruff`.
4. Run bot with environment variables.
5. Run tests with `pytest`.

Example commands:
```bash
uv sync
uv run ruff format
uv run ruff check
uv run python -m bot
uv run pytest
```

## Development Documentation Rule
- Implementation proposal/plan documents are required to follow this fixed structure:
  1. `Summary`
  2. `Implementation Changes`
  3. `Test Plan`
  4. `Assumptions and Defaults`
- Treat this as a mandatory development rule for implementation planning docs (including files under `plans/`).

## Docker Production
Container requirements:
- Non-root runtime user.
- Read-only root filesystem when practical.
- Writable temp directory for short-lived attachments.
- Secrets supplied through environment injection.

Example image entrypoint:
```bash
python -m bot
```

Example run:
```bash
docker run --rm \
  -e DISCORD_TOKEN=*** \
  -e APPLICATION_ID=*** \
  -e LOG_LEVEL=INFO \
  -e SCHEMA_HINT_URL_TEMPLATE=https://example.com/schema/v{version}/schema.json \
  discord-schema-manager:latest
```

## Discord Invite Guidance
Use scopes:
- `bot`
- `applications.commands`

Grant only the minimum permissions documented in `permissions-and-security.md`.

## Invite-Only-When-Needed Model
Recommended operations:
1. Generate invite URL with minimal permissions.
2. Invite bot to target guild.
3. Run export/diff/apply tasks.
4. Remove bot from guild when tasks are complete.

## Production Notes
- Monitor command errors and API rate-limit warnings.
- Rotate bot token if compromise is suspected.
- Keep `discord.py` updated and revalidate channel type compatibility after upgrades.
