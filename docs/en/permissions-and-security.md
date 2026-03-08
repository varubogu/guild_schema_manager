# Permissions and Security

## Hard Security Constraints
- Administrator permission is prohibited.
- Database persistence is prohibited.
- Configuration files and generated artifacts are transient.

Note:
- The prohibition above applies to bot-granted permissions.
- Command invokers are restricted to guild administrators.

## Required Bot Permissions (Minimum)
- `Manage Roles` (only required role operations)
- `Manage Channels`
- `View Channels`

## Command Invoker Controls
- All `/schema` commands require invoker guild `Administrator` permission.
- `/schema apply` confirmation action is invoker-only.
- Interaction identity must be checked against original command user ID.

## File Handling and Retention
- Uploaded files are parsed from attachment payload.
- Temporary file material is limited to memory or short-lived temp storage.
- Temporary artifacts are deleted immediately after completion.
- No schema, diff, or backup is stored in DB.

## Input Validation Controls
- Strict YAML schema validation before planning.
- Reject unknown keys and unsupported channel types.
- Validate overwrite targets and hierarchy references before apply.

## Operational Safety Controls
- Mandatory pre-apply backup on every apply run.
- Dry preview prior to every apply.
- Explicit confirmation required for all mutating actions.
- Detailed result reporting for incident triage.

## Minimal Audit Strategy (No DB)
Because persistent storage is disallowed:
- Keep concise operation summary in command response.
- Include timestamp, invoker ID, and outcome counts in response text.
- Rely on Discord message history for short-term audit trace.
