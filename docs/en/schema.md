# Schema Specification

## File Format
- Single YAML file.
- Logical sections:
  - `version`
  - `guild`
  - `roles`
  - `categories`
  - `channels`

## Top-Level Example
```yaml
version: 1
guild:
  id: "123456789012345678"
  name: "Example Guild"

roles:
  - id: "223456789012345678"
    name: "Moderators"
    color: 3447003
    hoist: true
    mentionable: false
    permissions:
      - manage_channels
      - mute_members

categories:
  - id: "323456789012345678"
    name: "Information"
    position: 0
    overwrites:
      - target:
          type: role
          id: "223456789012345678"
        allow: [view_channel]
        deny: []

channels:
  - id: "423456789012345678"
    name: "announcements"
    type: text
    parent_id: "323456789012345678"
    position: 0
    topic: "Official updates"
    nsfw: false
    slowmode_delay: 0
    overwrites: []
```

## Identity and Matching Rules
- ID-first matching is mandatory.
- If `id` exists in file, object identity is determined only by `id`.
- `name` is treated as mutable data and can be updated.
- If `id` is missing, fallback matching uses `name` within the same object scope.

## Name-Only Behavior
- Unique name match: treated as update target.
- Multiple objects with same name in scope: validation error.
- No name match: treated as create.

## Input Mode Behavior (`/schema diff`, `/schema apply`)
- `file_trust_mode=false` (default): uploaded files may be partial and are merged as patch.
- In patch mode, omitted sections (`roles`, `categories`, `channels`) and omitted fields are kept as current state.
- In patch mode, omitted entities in a listed section are kept as current state (no delete-by-omission).
- `file_trust_mode=true`: uploaded file is parsed as full schema source-of-truth.
- In trust mode, omitted entities are interpreted as delete intent by diff.

## Managed Entities
- Roles.
- Categories.
- Guild channels supported by the running `discord.py` version.
- Permission overwrites on categories and channels.

## Channel Type Policy
- The implementation targets all guild channel types exposed as creatable/managable by the running `discord.py` release.
- Unsupported or unknown type values must fail validation before diff/apply.

## Ordering and Dependencies
Apply planner must respect:
1. Roles first.
2. Categories second.
3. Channels third.
4. Parent assignment before channel reorder.
5. Reorder operations after create/update dependencies are resolved.

## Validation Rules
- Unknown top-level keys: error.
- Missing required fields (`name`, `type` where applicable): error for full schema parsing, trust mode, and create targets in patch mode.
- Invalid overwrite target references: error.
- Conflicting parent references (`parent_id` and unmatched `parent_name`): error.
- Duplicate explicit IDs in the same section: error.

## Published JSON Schema
- Versioned path: `/schema/v1/schema.json`
- Latest alias: `/schema/latest/schema.json`
- Recommended YAML header:
  - `# yaml-language-server: $schema=https://example.com/schema/v1/schema.json`
- Cross-reference constraints (for example duplicate explicit IDs and overwrite target existence) are still validated by bot runtime validation.
