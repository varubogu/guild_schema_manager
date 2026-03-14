from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from typing import Any, Callable, TypeVar

from bot.usecases.schema_model.models import (
    CategorySchema,
    ChannelSchema,
    GuildSchema,
    RoleSchema,
)

from .errors import DiffValidationError
from .models import DiffChange, DiffResult

T = TypeVar("T", RoleSchema, CategorySchema, ChannelSchema)
_APPLY_EXCLUDED_REASON_KEY = "apply_excluded_reason"
_BOT_MANAGED_SKIP_REASON = "bot_managed_role"


def diff_schemas(
    current: GuildSchema,
    desired: GuildSchema,
    *,
    prefer_name_matching: bool = False,
    allow_ambiguous_name_match: bool = False,
) -> DiffResult:
    changes: list[DiffChange] = []
    changes.extend(
        _diff_section(
            current_items=current.roles,
            desired_items=desired.roles,
            target_type="role",
            compare_fn=_compare_role,
            prefer_name_matching=prefer_name_matching,
            allow_ambiguous_name_match=allow_ambiguous_name_match,
        )
    )
    changes.extend(
        _diff_section(
            current_items=current.categories,
            desired_items=desired.categories,
            target_type="category",
            compare_fn=_compare_category,
            prefer_name_matching=prefer_name_matching,
            allow_ambiguous_name_match=allow_ambiguous_name_match,
        )
    )
    changes.extend(
        _diff_section(
            current_items=_channels_for_name_matching(
                current,
                prefer_name_matching=prefer_name_matching,
            ),
            desired_items=_channels_for_name_matching(
                desired,
                prefer_name_matching=prefer_name_matching,
            ),
            target_type="channel",
            compare_fn=lambda current_item, desired_item: _compare_channel(
                current_item,
                desired_item,
                prefer_name_matching=prefer_name_matching,
            ),
            prefer_name_matching=prefer_name_matching,
            allow_ambiguous_name_match=allow_ambiguous_name_match,
        )
    )

    summary_counter = Counter(change.action for change in changes)
    summary = {
        "Create": summary_counter.get("Create", 0),
        "Update": summary_counter.get("Update", 0),
        "Delete": summary_counter.get("Delete", 0),
        "Move": summary_counter.get("Move", 0),
        "Reorder": summary_counter.get("Reorder", 0),
    }
    return DiffResult(summary=summary, changes=changes)


def _diff_section(
    current_items: list[T],
    desired_items: list[T],
    target_type: str,
    compare_fn: Callable[[T, T], list[DiffChange]],
    *,
    prefer_name_matching: bool,
    allow_ambiguous_name_match: bool,
) -> list[DiffChange]:
    matched_pairs, creates, deletes = _match_items(
        current_items,
        desired_items,
        target_type,
        prefer_name_matching=prefer_name_matching,
        allow_ambiguous_name_match=allow_ambiguous_name_match,
    )
    changes: list[DiffChange] = []

    for desired_item in creates:
        after_payload = _create_payload_for_change(
            desired_item,
            target_type=target_type,
            prefer_name_matching=prefer_name_matching,
        )
        if target_type == "role" and isinstance(desired_item, RoleSchema):
            after_payload = _annotate_role_apply_excluded(
                after_payload,
                role=desired_item,
            )
        changes.append(
            DiffChange(
                action="Create",
                target_type=target_type,  # type: ignore[arg-type]
                target_id=desired_item.id,
                before=None,
                after=after_payload,
                risk="low",
                before_name=None,
                after_name=desired_item.name,
            )
        )

    for current_item in deletes:
        before_payload = _safe_payload(current_item)
        if target_type == "role" and isinstance(current_item, RoleSchema):
            before_payload = _annotate_role_apply_excluded(
                before_payload,
                role=current_item,
            )
        changes.append(
            DiffChange(
                action="Delete",
                target_type=target_type,  # type: ignore[arg-type]
                target_id=current_item.id,
                before=before_payload,
                after=None,
                risk="high",
                before_name=current_item.name,
                after_name=None,
            )
        )

    for current_item, desired_item in matched_pairs:
        changes.extend(compare_fn(current_item, desired_item))

    return changes


def _channels_for_name_matching(
    schema: GuildSchema,
    *,
    prefer_name_matching: bool,
) -> list[ChannelSchema]:
    if not prefer_name_matching:
        return schema.channels

    category_name_by_id = {
        category.id: category.name for category in schema.categories if category.id
    }
    normalized_channels: list[ChannelSchema] = []
    for channel in schema.channels:
        if channel.parent_name is not None:
            normalized_channels.append(channel)
            continue
        if channel.parent_id is None:
            normalized_channels.append(channel)
            continue
        parent_name = category_name_by_id.get(channel.parent_id)
        if parent_name is None:
            normalized_channels.append(channel)
            continue
        normalized_channels.append(replace(channel, parent_name=parent_name))
    return normalized_channels


def _match_items(
    current_items: list[T],
    desired_items: list[T],
    target_type: str,
    *,
    prefer_name_matching: bool,
    allow_ambiguous_name_match: bool,
) -> tuple[list[tuple[T, T]], list[T], list[T]]:
    unmatched_current = set(range(len(current_items)))

    by_id: dict[str, int] = {}
    by_name: defaultdict[str, list[int]] = defaultdict(list)

    for idx, item in enumerate(current_items):
        if item.id:
            by_id[item.id] = idx
        by_name[item.name].append(idx)

    matched: list[tuple[T, T]] = []
    creates: list[T] = []
    validation_errors: list[str] = []

    for desired_item in desired_items:
        matched_idx: int | None = None

        try:
            if prefer_name_matching:
                matched_idx = _find_name_match_index(
                    desired_item=desired_item,
                    current_items=current_items,
                    by_name=by_name,
                    unmatched_current=unmatched_current,
                    target_type=target_type,
                    prefer_name_matching=prefer_name_matching,
                    allow_ambiguous_name_match=allow_ambiguous_name_match,
                )
            else:
                if desired_item.id:
                    matched_idx = _find_id_match_index(
                        desired_item=desired_item,
                        by_id=by_id,
                        unmatched_current=unmatched_current,
                    )
                else:
                    matched_idx = _find_name_match_index(
                        desired_item=desired_item,
                        current_items=current_items,
                        by_name=by_name,
                        unmatched_current=unmatched_current,
                        target_type=target_type,
                        prefer_name_matching=prefer_name_matching,
                        allow_ambiguous_name_match=allow_ambiguous_name_match,
                    )
        except DiffValidationError as exc:
            validation_errors.append(str(exc))
            continue

        if matched_idx is None:
            creates.append(desired_item)
            continue

        unmatched_current.remove(matched_idx)
        matched.append((current_items[matched_idx], desired_item))

    if validation_errors:
        raise _compose_validation_error(validation_errors)

    deletes = [current_items[idx] for idx in sorted(unmatched_current)]
    return matched, creates, deletes


def _find_id_match_index(
    *,
    desired_item: T,
    by_id: dict[str, int],
    unmatched_current: set[int],
) -> int | None:
    if not desired_item.id:
        return None
    candidate = by_id.get(desired_item.id)
    if candidate is None or candidate not in unmatched_current:
        return None
    return candidate


def _find_name_match_index(
    *,
    desired_item: T,
    current_items: list[T],
    by_name: defaultdict[str, list[int]],
    unmatched_current: set[int],
    target_type: str,
    prefer_name_matching: bool,
    allow_ambiguous_name_match: bool,
) -> int | None:
    candidates = [
        idx for idx in by_name.get(desired_item.name, []) if idx in unmatched_current
    ]

    if target_type == "role" and isinstance(desired_item, RoleSchema):
        candidates = _prefer_same_bot_managed_role_candidates(
            current_items=current_items,
            candidates=candidates,
            desired_role=desired_item,
        )

    # Channel names can be duplicated across types; narrow by channel type first.
    if target_type == "channel" and isinstance(desired_item, ChannelSchema):
        desired_channel_type = desired_item.type
        desired_parent_scope = _parent_reference(
            desired_item,
            prefer_name_matching=prefer_name_matching,
        )
        typed_candidates: list[int] = []
        for idx in candidates:
            current_candidate = current_items[idx]
            if not isinstance(current_candidate, ChannelSchema):
                continue
            if current_candidate.type != desired_channel_type:
                continue
            if desired_parent_scope is not None:
                current_parent_scope = _parent_reference(
                    current_candidate,
                    prefer_name_matching=prefer_name_matching,
                )
                if current_parent_scope != desired_parent_scope:
                    continue
            typed_candidates.append(idx)
        if typed_candidates:
            candidates = typed_candidates

    if len(candidates) > 1:
        if allow_ambiguous_name_match:
            # Ambiguous candidates are distinguished internally by stable order.
            return candidates[0]
        raise DiffValidationError(
            f"name-only duplicate match in {target_type}: '{desired_item.name}'"
        )
    if len(candidates) == 1:
        return candidates[0]
    return None


def _compose_validation_error(errors: list[str]) -> DiffValidationError:
    if len(errors) == 1:
        return DiffValidationError(errors[0])
    details = "\n".join(f"- {error}" for error in errors)
    return DiffValidationError(f"multiple validation errors:\n{details}")


def _compare_role(current: RoleSchema, desired: RoleSchema) -> list[DiffChange]:
    changes: list[DiffChange] = []
    before_payload = _safe_payload(current)
    after_payload = _safe_payload(desired)
    is_bot_managed = current.bot_managed or desired.bot_managed

    changed_fields = _changed_fields(
        before_payload,
        after_payload,
        ["name", "color", "hoist", "mentionable", "permissions"],
    )
    if changed_fields:
        before_change, after_change = changed_fields
        if is_bot_managed:
            before_change = _annotate_role_apply_excluded(
                before_change,
                role=current,
            )
            after_change = _annotate_role_apply_excluded(
                after_change,
                role=desired,
            )
        changes.append(
            DiffChange(
                action="Update",
                target_type="role",
                target_id=current.id or desired.id,
                before=before_change,
                after=after_change,
                risk="medium",
                before_name=current.name,
                after_name=desired.name,
            )
        )

    if current.position != desired.position:
        before_position_payload: dict[str, Any] = {"position": current.position}
        after_position_payload: dict[str, Any] = {"position": desired.position}
        if is_bot_managed:
            before_position_payload = _annotate_role_apply_excluded(
                before_position_payload,
                role=current,
            )
            after_position_payload = _annotate_role_apply_excluded(
                after_position_payload,
                role=desired,
            )
        changes.append(
            DiffChange(
                action="Reorder",
                target_type="role",
                target_id=current.id or desired.id,
                before=before_position_payload,
                after=after_position_payload,
                risk="low",
                before_name=current.name,
                after_name=desired.name,
            )
        )

    return changes


def _compare_category(
    current: CategorySchema, desired: CategorySchema
) -> list[DiffChange]:
    changes: list[DiffChange] = []
    target_id = current.id or desired.id

    if current.name != desired.name:
        changes.append(
            DiffChange(
                action="Update",
                target_type="category",
                target_id=target_id,
                before={"name": current.name},
                after={"name": desired.name},
                risk="medium",
                before_name=current.name,
                after_name=desired.name,
            )
        )

    if current.position != desired.position:
        changes.append(
            DiffChange(
                action="Reorder",
                target_type="category",
                target_id=target_id,
                before={"position": current.position},
                after={"position": desired.position},
                risk="low",
                before_name=current.name,
                after_name=desired.name,
            )
        )

    changes.extend(
        _compare_overwrites(
            "category",
            target_id,
            current.overwrites,
            desired.overwrites,
            before_name=current.name,
            after_name=desired.name,
        )
    )
    return changes


def _compare_channel(
    current: ChannelSchema,
    desired: ChannelSchema,
    *,
    prefer_name_matching: bool,
) -> list[DiffChange]:
    changes: list[DiffChange] = []
    target_id = current.id or desired.id

    changed_fields = _changed_fields(
        _safe_payload(current),
        _safe_payload(desired),
        ["name", "type", "topic", "nsfw", "slowmode_delay"],
    )
    if changed_fields:
        changes.append(
            DiffChange(
                action="Update",
                target_type="channel",
                target_id=target_id,
                before=changed_fields[0],
                after=changed_fields[1],
                risk="medium",
                before_name=current.name,
                after_name=desired.name,
            )
        )

    current_parent = _parent_reference(
        current,
        prefer_name_matching=prefer_name_matching,
    )
    desired_parent = _parent_reference(
        desired,
        prefer_name_matching=prefer_name_matching,
    )
    if current_parent != desired_parent:
        changes.append(
            DiffChange(
                action="Move",
                target_type="channel",
                target_id=target_id,
                before={"parent": current_parent},
                after={"parent": desired_parent},
                risk="medium",
                before_name=current.name,
                after_name=desired.name,
            )
        )

    if current.position != desired.position:
        changes.append(
            DiffChange(
                action="Reorder",
                target_type="channel",
                target_id=target_id,
                before={"position": current.position},
                after={"position": desired.position},
                risk="low",
                before_name=current.name,
                after_name=desired.name,
            )
        )

    changes.extend(
        _compare_overwrites(
            "channel",
            target_id,
            current.overwrites,
            desired.overwrites,
            before_name=current.name,
            after_name=desired.name,
        )
    )
    return changes


def _parent_reference(
    channel: ChannelSchema,
    *,
    prefer_name_matching: bool,
) -> str | None:
    if prefer_name_matching:
        return channel.parent_name
    return channel.parent_id or channel.parent_name


def _create_payload_for_change(
    item: T,
    *,
    target_type: str,
    prefer_name_matching: bool,
) -> dict[str, Any]:
    payload = _safe_payload(item)
    if not prefer_name_matching:
        return payload

    payload.pop("id", None)
    if target_type == "channel" and payload.get("parent_name") is not None:
        payload.pop("parent_id", None)
    return payload


def _compare_overwrites(
    owner_type: str,
    owner_id: str | None,
    current_overwrites: list[Any],
    desired_overwrites: list[Any],
    *,
    before_name: str | None,
    after_name: str | None,
) -> list[DiffChange]:
    changes: list[DiffChange] = []

    def to_map(items: list[Any]) -> dict[str, dict[str, Any]]:
        mapped: dict[str, dict[str, Any]] = {}
        for item in items:
            payload = _safe_payload(item)
            key = f"{payload['target']['type']}:{payload['target']['id']}"
            mapped[key] = {
                "allow": sorted(payload.get("allow", [])),
                "deny": sorted(payload.get("deny", [])),
            }
        return mapped

    current_map = to_map(current_overwrites)
    desired_map = to_map(desired_overwrites)

    for key, before in current_map.items():
        if key not in desired_map:
            changes.append(
                DiffChange(
                    action="Delete",
                    target_type="overwrite",
                    target_id=f"{owner_type}:{owner_id}:{key}",
                    before=before,
                    after=None,
                    risk="medium",
                    before_name=before_name,
                    after_name=after_name,
                )
            )

    for key, after in desired_map.items():
        if key not in current_map:
            changes.append(
                DiffChange(
                    action="Create",
                    target_type="overwrite",
                    target_id=f"{owner_type}:{owner_id}:{key}",
                    before=None,
                    after=after,
                    risk="low",
                    before_name=before_name,
                    after_name=after_name,
                )
            )
            continue

        before = current_map[key]
        if before != after:
            changes.append(
                DiffChange(
                    action="Update",
                    target_type="overwrite",
                    target_id=f"{owner_type}:{owner_id}:{key}",
                    before=before,
                    after=after,
                    risk="medium",
                    before_name=before_name,
                    after_name=after_name,
                )
            )

    return changes


def _changed_fields(
    before: dict[str, Any],
    after: dict[str, Any],
    fields: list[str],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    before_diff: dict[str, Any] = {}
    after_diff: dict[str, Any] = {}
    for field in fields:
        if before.get(field) != after.get(field):
            before_diff[field] = before.get(field)
            after_diff[field] = after.get(field)
    if not before_diff:
        return None
    return before_diff, after_diff


def _safe_payload(value: Any) -> dict[str, Any]:
    payload = asdict(value)
    if "permissions" in payload:
        payload["permissions"] = sorted(payload["permissions"])
    if "allow" in payload:
        payload["allow"] = sorted(payload["allow"])
    if "deny" in payload:
        payload["deny"] = sorted(payload["deny"])
    return payload


def _annotate_role_apply_excluded(
    payload: dict[str, Any],
    *,
    role: RoleSchema,
) -> dict[str, Any]:
    if not role.bot_managed:
        return payload
    payload["bot_managed"] = True
    payload[_APPLY_EXCLUDED_REASON_KEY] = _BOT_MANAGED_SKIP_REASON
    return payload


def _prefer_same_bot_managed_role_candidates(
    *,
    current_items: list[T],
    candidates: list[int],
    desired_role: RoleSchema,
) -> list[int]:
    if len(candidates) <= 1:
        return candidates
    preferred: list[int] = []
    for idx in candidates:
        current_item = current_items[idx]
        if not isinstance(current_item, RoleSchema):
            continue
        if current_item.bot_managed != desired_role.bot_managed:
            continue
        preferred.append(idx)
    if preferred:
        return preferred
    return candidates
