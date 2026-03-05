# Diff and Apply

## Diff Categories
Every detected change is classified as one of:
- `Create`
- `Update`
- `Delete`
- `Move`
- `Reorder`

## Diff Output Format
Primary output is human-readable Markdown:
- Summary block with counts per action.
- Detailed change table with risk labels.

Example table columns:
- `action`
- `target_type`
- `target_id`
- `before`
- `after`
- `risk`

## Apply Workflow
`/schema apply` uses one command with confirmation UI:
1. Validate uploaded schema.
2. Compute diff and render preview.
3. Present confirmation button to invoker.
4. On approval, run backup then apply.

## Confirmation Rules
- Confirm button is valid for 10 minutes.
- Only invoker can confirm.
- Non-invoker interaction returns rejection message.
- Expired confirmation requires rerun.

## Backup Policy
- A full current-state export is always created before mutating operations.
- Backup is returned as attachment in final apply response.
- Backup is not persisted after response lifecycle.

## Delete Policy
- Delete actions appear in preview like other changes.
- Delete execution happens only after explicit confirmation.

## Atomicity and Failure Handling
- Execution model is best effort, not global transaction.
- Independent operations continue when safe.
- Final report separates:
  - `applied[]`
  - `failed[]`
  - `skipped[]`

## Restart and Session Expiry
- Pending plans are memory-only.
- Bot restart invalidates all pending confirmations.
