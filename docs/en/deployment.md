# Deployment

## Technology Stack
- Python
- `discord.py`
- `uv`
- `pytest`
- Docker (production runtime)

## Environment Variables
Minimum runtime variables:
- `DISCORD_TOKEN`: bot token.
- `APPLICATION_ID`: Discord application ID.
- `LOG_LEVEL`: optional (`INFO` default).
- `CONFIRM_TTL_SECONDS`: optional (`600` default).
- `SCHEMA_REPO_OWNER`: optional GitHub owner used for `/schema export` schema hint.
- `SCHEMA_REPO_NAME`: optional GitHub repository name used for `/schema export` schema hint.

If both `SCHEMA_REPO_OWNER` and `SCHEMA_REPO_NAME` are set, exported YAML includes:
- `# yaml-language-server: $schema=https://<owner>.github.io/<repo>/schema/v<version>/schema.json`

## Local Development
Example flow:
1. Install `uv`.
2. Create environment and install dependencies.
3. Run bot with environment variables.
4. Run tests with `pytest`.

Example commands:
```bash
uv sync
uv run python -m bot
uv run pytest
```

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
  -e SCHEMA_REPO_OWNER=your-org \
  -e SCHEMA_REPO_NAME=guild_schema_manager \
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
