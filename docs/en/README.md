# Discord Server Schema Manager Bot

## Purpose
This project defines a Discord bot that manages server structure as a file-driven schema.

Core goals:
- Export current Discord server structure to a file.
- Compare server structure with an uploaded file and show diffs.
- Apply file-based changes only after explicit user confirmation.

## Non-Functional Constraints
- No database.
- No persistent server-side storage.
- No administrator permission.
- Bot can be invited only when needed.
- Bot runs as a standalone process.
- File exchange happens via command input/output attachments.

## MVP Features
- Manage `roles`, `categories`, and `channels`.
- Support ID-based and name-based management (default ID-first, but name-first when guild ID mismatch continuation is explicitly approved).
- Use slash commands only.
- Restrict all bot command execution to guild administrators.
- Show change preview before apply.
- Require invoker-only confirmation button for apply.
- Always create and return pre-apply backup.

## Out of Scope
- Permanent sync daemon.
- Database-backed audit/history.
- Auto-apply without confirmation.
- Administrator permission usage.

## Documentation Index
- [Architecture](./architecture.md)
- [Commands](./commands.md)
- [Schema](./schema.md)
- [Diff and Apply](./diff-and-apply.md)
- [Permissions and Security](./permissions-and-security.md)
- [Deployment](./deployment.md)
- [Testing](./testing.md)

## Canonical Language Policy
- `docs/en` is the canonical source.
- `docs/ja` must stay functionally equivalent.

## Other Languages
- [日本語ドキュメント](../ja/)

## Back to Docs Root
- [Docs home](../)
