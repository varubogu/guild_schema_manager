# Testing Strategy

## Test Framework
- Use `pytest`.
- Prefer deterministic unit tests for schema, diff, and planner logic.

## Test Layers
1. Schema parsing and validation.
2. Snapshot normalization.
3. Diff calculation.
4. Apply planning (ordering and dependency resolution).
5. Command-level flow with mocked Discord interactions.
6. Permission and confirmation guards.

## Required Core Scenarios
1. ID present with renamed object is detected as update/rename.
2. Name-only unique match updates existing object.
3. Name-only duplicate match returns validation error.
4. Delete targets appear in preview and are never hard-deleted before confirmation.
5. Confirmed channel delete targets are moved to `GSM-Dustbox`.
6. Confirmed category delete targets move child channels to `GSM-Dustbox` and archive the source category.
7. `GSM-Dustbox` is created with admin-only visibility when missing.
8. Role delete is reported for manual deletion (not hard-deleted by bot).
9. Non-administrator command invocation is rejected for all `/schema` commands.
10. Non-invoker confirmation attempt is rejected.
11. Pre-apply backup is always produced.
12. Category/channel overwrite add/update/delete diffs are detected.
13. Parent category move and reorder diffs are detected.
14. Unsupported channel type fails validation.
15. Partial Discord API failures are separated into `failed[]` while successful operations remain in `applied[]`.
16. Bot restart invalidates pending confirmation plans.

## Mocking Strategy
- Mock discord.py HTTP/guild objects at service boundary.
- Use fixture snapshots for current state and desired state.
- Avoid real Discord API calls in unit test suite.

## CI Test Set
Fast default CI set:
- Validation tests
- Diff engine tests
- Planner ordering tests
- Command guard tests

Optional extended set:
- Container smoke test
- Integration test against a temporary test guild (manual or scheduled, not required for every PR)

## Acceptance Criteria
- All core scenarios above are covered.
- No mutating apply path executes without confirmation test coverage.
- Permission and invoker checks are explicitly asserted.
- Administrator-only command access is explicitly asserted.
