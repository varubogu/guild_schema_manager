from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import cast

from bot.usecases.diff import DiffInformationalChange
from bot.usecases.diff.models import DiffInformationalAction, DiffTargetType
from bot.usecases.schema_model.models import (
    CategorySchema,
    ChannelSchema,
    GuildSchema,
    PermissionOverwrite,
    RoleSchema,
)

from .uploaded_payload import category_name_by_id_from_payload


def build_informational_changes(
    current: GuildSchema,
    desired: GuildSchema,
    *,
    file_trust_mode: bool,
    prefer_name_matching: bool,
    uploaded_payload: dict[str, object] | None,
) -> list[DiffInformationalChange]:
    informational: list[DiffInformationalChange] = []
    current_category_name_by_id = _category_name_by_id(current.categories)
    desired_category_name_by_id = _category_name_by_id(desired.categories)

    role_pairs = _match_named_entities(
        current.roles,
        desired.roles,
        prefer_name_matching=prefer_name_matching,
    )
    role_defined = (
        set(range(len(current.roles)))
        if file_trust_mode
        else _defined_named_entity_indices(
            current.roles,
            uploaded_payload,
            "roles",
            prefer_name_matching=prefer_name_matching,
        )
    )
    informational.extend(
        _informational_for_roles(
            current.roles,
            desired.roles,
            role_pairs,
            role_defined,
        )
    )

    category_pairs = _match_named_entities(
        current.categories,
        desired.categories,
        prefer_name_matching=prefer_name_matching,
    )
    category_defined = (
        set(range(len(current.categories)))
        if file_trust_mode
        else _defined_named_entity_indices(
            current.categories,
            uploaded_payload,
            "categories",
            prefer_name_matching=prefer_name_matching,
        )
    )
    informational.extend(
        _informational_for_categories(
            current.categories,
            desired.categories,
            category_pairs,
            category_defined,
        )
    )

    channel_pairs = _match_channels(
        current.channels,
        desired.channels,
        prefer_name_matching=prefer_name_matching,
        current_category_name_by_id=current_category_name_by_id,
        desired_category_name_by_id=desired_category_name_by_id,
    )
    channel_defined = (
        set(range(len(current.channels)))
        if file_trust_mode
        else _defined_channel_indices(
            current.channels,
            uploaded_payload,
            prefer_name_matching=prefer_name_matching,
            current_category_name_by_id=current_category_name_by_id,
        )
    )
    informational.extend(
        _informational_for_channels(
            current.channels,
            desired.channels,
            channel_pairs,
            channel_defined,
            prefer_name_matching=prefer_name_matching,
            current_category_name_by_id=current_category_name_by_id,
            desired_category_name_by_id=desired_category_name_by_id,
        )
    )
    return informational


def _match_named_entities(
    current_items: Sequence[RoleSchema | CategorySchema],
    desired_items: Sequence[RoleSchema | CategorySchema],
    *,
    prefer_name_matching: bool,
) -> list[tuple[int, int]]:
    unmatched_current = set(range(len(current_items)))
    by_id: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for idx, item in enumerate(current_items):
        if item.id:
            by_id[item.id] = idx
        by_name.setdefault(item.name, []).append(idx)

    pairs: list[tuple[int, int]] = []
    for desired_idx, desired_item in enumerate(desired_items):
        current_idx: int | None = None
        if prefer_name_matching:
            current_idx = _first_matching_named_entity_index(
                current_items,
                by_name.get(desired_item.name, []),
                unmatched_current,
                desired_item,
            )
        else:
            if desired_item.id:
                candidate = by_id.get(desired_item.id)
                if candidate is not None and candidate in unmatched_current:
                    current_idx = candidate
            if current_idx is None:
                current_idx = _first_matching_named_entity_index(
                    current_items,
                    by_name.get(desired_item.name, []),
                    unmatched_current,
                    desired_item,
                )
        if current_idx is None:
            continue
        unmatched_current.remove(current_idx)
        pairs.append((current_idx, desired_idx))
    return pairs


def _match_channels(
    current_channels: Sequence[ChannelSchema],
    desired_channels: Sequence[ChannelSchema],
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    desired_category_name_by_id: dict[str, str],
) -> list[tuple[int, int]]:
    unmatched_current = set(range(len(current_channels)))
    by_id: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for idx, channel in enumerate(current_channels):
        if channel.id:
            by_id[channel.id] = idx
        by_name.setdefault(channel.name, []).append(idx)

    pairs: list[tuple[int, int]] = []
    for desired_idx, desired_channel in enumerate(desired_channels):
        current_idx: int | None = None
        if prefer_name_matching:
            current_idx = _first_matching_channel_index(
                current_channels,
                by_name.get(desired_channel.name, []),
                unmatched_current,
                desired_channel,
                prefer_name_matching=prefer_name_matching,
                current_category_name_by_id=current_category_name_by_id,
                desired_category_name_by_id=desired_category_name_by_id,
            )
        else:
            if desired_channel.id:
                candidate = by_id.get(desired_channel.id)
                if candidate is not None and candidate in unmatched_current:
                    current_idx = candidate
            if current_idx is None:
                current_idx = _first_matching_channel_index(
                    current_channels,
                    by_name.get(desired_channel.name, []),
                    unmatched_current,
                    desired_channel,
                    prefer_name_matching=prefer_name_matching,
                    current_category_name_by_id=current_category_name_by_id,
                    desired_category_name_by_id=desired_category_name_by_id,
                )

        if current_idx is None:
            continue
        unmatched_current.remove(current_idx)
        pairs.append((current_idx, desired_idx))
    return pairs


def _first_matching_channel_index(
    current_channels: Sequence[ChannelSchema],
    candidates: Sequence[int],
    unmatched_current: set[int],
    desired_channel: ChannelSchema,
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    desired_category_name_by_id: dict[str, str],
) -> int | None:
    desired_parent_scope = _channel_parent_scope(
        desired_channel,
        prefer_name_matching=prefer_name_matching,
        category_name_by_id=desired_category_name_by_id,
    )
    scoped_candidates: list[int] = []
    for candidate in candidates:
        if candidate not in unmatched_current:
            continue
        current_channel = current_channels[candidate]
        if current_channel.type != desired_channel.type:
            continue
        if desired_parent_scope is not None:
            current_parent_scope = _channel_parent_scope(
                current_channel,
                prefer_name_matching=prefer_name_matching,
                category_name_by_id=current_category_name_by_id,
            )
            if current_parent_scope != desired_parent_scope:
                continue
        scoped_candidates.append(candidate)

    if scoped_candidates:
        return scoped_candidates[0]
    return _first_unmatched_index(candidates, unmatched_current)


def _defined_named_entity_indices(
    current_items: Sequence[RoleSchema | CategorySchema],
    uploaded_payload: dict[str, object] | None,
    section: str,
    *,
    prefer_name_matching: bool,
) -> set[int]:
    if uploaded_payload is None:
        return set()
    raw_items = uploaded_payload.get(section)
    if not isinstance(raw_items, list):
        return set()

    by_id: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for idx, item in enumerate(current_items):
        if item.id:
            by_id[item.id] = idx
        by_name.setdefault(item.name, []).append(idx)

    unmatched_current = set(range(len(current_items)))
    defined: set[int] = set()
    for raw_item in cast(list[object], raw_items):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, object], raw_item)
        idx: int | None = None
        if prefer_name_matching:
            name = item.get("name")
            if isinstance(name, str) and name:
                idx = _first_matching_payload_named_entity_index(
                    current_items,
                    by_name.get(name, []),
                    unmatched_current,
                    item,
                    section=section,
                )
        else:
            raw_id = item.get("id")
            if isinstance(raw_id, str) and raw_id:
                candidate = by_id.get(raw_id)
                if candidate is not None and candidate in unmatched_current:
                    idx = candidate
            if idx is None:
                name = item.get("name")
                if isinstance(name, str) and name:
                    idx = _first_matching_payload_named_entity_index(
                        current_items,
                        by_name.get(name, []),
                        unmatched_current,
                        item,
                        section=section,
                    )
        if idx is None:
            continue
        defined.add(idx)
        unmatched_current.remove(idx)
    return defined


def _defined_channel_indices(
    current_channels: Sequence[ChannelSchema],
    uploaded_payload: dict[str, object] | None,
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
) -> set[int]:
    if uploaded_payload is None:
        return set()
    raw_channels = uploaded_payload.get("channels")
    if not isinstance(raw_channels, list):
        return set()

    by_id: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for idx, channel in enumerate(current_channels):
        if channel.id:
            by_id[channel.id] = idx
        by_name.setdefault(channel.name, []).append(idx)

    uploaded_category_name_by_id = category_name_by_id_from_payload(uploaded_payload)
    unmatched_current = set(range(len(current_channels)))
    defined: set[int] = set()

    for raw_channel in cast(list[object], raw_channels):
        if not isinstance(raw_channel, dict):
            continue
        channel_payload = cast(dict[str, object], raw_channel)
        idx: int | None = None
        if prefer_name_matching:
            idx = _match_current_channel_from_payload(
                current_channels,
                channel_payload,
                by_name,
                unmatched_current,
                prefer_name_matching=prefer_name_matching,
                current_category_name_by_id=current_category_name_by_id,
                uploaded_category_name_by_id=uploaded_category_name_by_id,
            )
        else:
            raw_id = channel_payload.get("id")
            if isinstance(raw_id, str) and raw_id:
                candidate = by_id.get(raw_id)
                if candidate is not None and candidate in unmatched_current:
                    idx = candidate
            if idx is None:
                idx = _match_current_channel_from_payload(
                    current_channels,
                    channel_payload,
                    by_name,
                    unmatched_current,
                    prefer_name_matching=prefer_name_matching,
                    current_category_name_by_id=current_category_name_by_id,
                    uploaded_category_name_by_id=uploaded_category_name_by_id,
                )
        if idx is None:
            continue
        defined.add(idx)
        unmatched_current.remove(idx)
    return defined


def _match_current_channel_from_payload(
    current_channels: Sequence[ChannelSchema],
    channel_payload: dict[str, object],
    by_name: dict[str, list[int]],
    unmatched_current: set[int],
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    uploaded_category_name_by_id: dict[str, str],
) -> int | None:
    name = channel_payload.get("name")
    if not isinstance(name, str) or not name:
        return None

    payload_type = channel_payload.get("type")
    payload_parent_scope = _channel_parent_scope_from_payload(
        channel_payload,
        prefer_name_matching=prefer_name_matching,
        category_name_by_id=uploaded_category_name_by_id,
    )

    for candidate in by_name.get(name, []):
        if candidate not in unmatched_current:
            continue
        current_channel = current_channels[candidate]
        if (
            isinstance(payload_type, str)
            and payload_type
            and current_channel.type != payload_type
        ):
            continue
        if payload_parent_scope is not None:
            current_parent_scope = _channel_parent_scope(
                current_channel,
                prefer_name_matching=prefer_name_matching,
                category_name_by_id=current_category_name_by_id,
            )
            if current_parent_scope != payload_parent_scope:
                continue
        return candidate
    return None


def _informational_for_roles(
    current_roles: Sequence[RoleSchema],
    desired_roles: Sequence[RoleSchema],
    pairs: Sequence[tuple[int, int]],
    defined_indices: set[int],
) -> list[DiffInformationalChange]:
    rows: list[DiffInformationalChange] = []
    for current_idx, desired_idx in pairs:
        current_role = current_roles[current_idx]
        desired_role = desired_roles[desired_idx]
        if not _role_exact(current_role, desired_role):
            continue
        rows.append(
            _informational_change(
                target_type="role",
                target_id=current_role.id or desired_role.id,
                before_name=current_role.name,
                after_name=desired_role.name,
                before=_safe_schema_payload(current_role),
                after=_safe_schema_payload(desired_role),
                file_defined=current_idx in defined_indices,
            )
        )
    return rows


def _informational_for_categories(
    current_categories: Sequence[CategorySchema],
    desired_categories: Sequence[CategorySchema],
    pairs: Sequence[tuple[int, int]],
    defined_indices: set[int],
) -> list[DiffInformationalChange]:
    rows: list[DiffInformationalChange] = []
    for current_idx, desired_idx in pairs:
        current_category = current_categories[current_idx]
        desired_category = desired_categories[desired_idx]
        if not _category_exact(current_category, desired_category):
            continue
        rows.append(
            _informational_change(
                target_type="category",
                target_id=current_category.id or desired_category.id,
                before_name=current_category.name,
                after_name=desired_category.name,
                before=_safe_schema_payload(current_category),
                after=_safe_schema_payload(desired_category),
                file_defined=current_idx in defined_indices,
            )
        )
    return rows


def _informational_for_channels(
    current_channels: Sequence[ChannelSchema],
    desired_channels: Sequence[ChannelSchema],
    pairs: Sequence[tuple[int, int]],
    defined_indices: set[int],
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    desired_category_name_by_id: dict[str, str],
) -> list[DiffInformationalChange]:
    rows: list[DiffInformationalChange] = []
    for current_idx, desired_idx in pairs:
        current_channel = current_channels[current_idx]
        desired_channel = desired_channels[desired_idx]
        if not _channel_exact(
            current_channel,
            desired_channel,
            prefer_name_matching=prefer_name_matching,
            current_category_name_by_id=current_category_name_by_id,
            desired_category_name_by_id=desired_category_name_by_id,
        ):
            continue
        rows.append(
            _informational_change(
                target_type="channel",
                target_id=current_channel.id or desired_channel.id,
                before_name=current_channel.name,
                after_name=desired_channel.name,
                before=_safe_schema_payload(current_channel),
                after=_safe_schema_payload(desired_channel),
                file_defined=current_idx in defined_indices,
            )
        )
    return rows


def _informational_change(
    *,
    target_type: DiffTargetType,
    target_id: str | None,
    before_name: str | None,
    after_name: str | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    file_defined: bool,
) -> DiffInformationalChange:
    action: DiffInformationalAction = (
        "UnchangedExact" if file_defined else "UnchangedFileUndefined"
    )
    return DiffInformationalChange(
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
        before_name=before_name,
        after_name=after_name,
    )


def _role_exact(current: RoleSchema, desired: RoleSchema) -> bool:
    return (
        current.name == desired.name
        and current.bot_managed == desired.bot_managed
        and current.color == desired.color
        and current.hoist == desired.hoist
        and current.mentionable == desired.mentionable
        and sorted(current.permissions) == sorted(desired.permissions)
        and current.position == desired.position
    )


def _category_exact(current: CategorySchema, desired: CategorySchema) -> bool:
    return (
        current.name == desired.name
        and current.position == desired.position
        and _overwrites_equal(current.overwrites, desired.overwrites)
    )


def _channel_exact(
    current: ChannelSchema,
    desired: ChannelSchema,
    *,
    prefer_name_matching: bool,
    current_category_name_by_id: dict[str, str],
    desired_category_name_by_id: dict[str, str],
) -> bool:
    return (
        current.name == desired.name
        and current.type == desired.type
        and current.topic == desired.topic
        and current.nsfw == desired.nsfw
        and current.slowmode_delay == desired.slowmode_delay
        and current.position == desired.position
        and _channel_parent_scope(
            current,
            prefer_name_matching=prefer_name_matching,
            category_name_by_id=current_category_name_by_id,
        )
        == _channel_parent_scope(
            desired,
            prefer_name_matching=prefer_name_matching,
            category_name_by_id=desired_category_name_by_id,
        )
        and _overwrites_equal(current.overwrites, desired.overwrites)
    )


def _overwrites_equal(
    current_overwrites: Sequence[PermissionOverwrite],
    desired_overwrites: Sequence[PermissionOverwrite],
) -> bool:
    return _overwrite_map(current_overwrites) == _overwrite_map(desired_overwrites)


def _overwrite_map(
    overwrites: Sequence[PermissionOverwrite],
) -> dict[str, tuple[list[str], list[str]]]:
    mapped: dict[str, tuple[list[str], list[str]]] = {}
    for overwrite in overwrites:
        key = f"{overwrite.target.type}:{overwrite.target.id}"
        mapped[key] = (sorted(overwrite.allow), sorted(overwrite.deny))
    return mapped


def _safe_schema_payload(
    value: RoleSchema | CategorySchema | ChannelSchema,
) -> dict[str, object]:
    payload = cast(dict[str, object], asdict(value))
    if "permissions" in payload:
        permissions = payload.get("permissions")
        if isinstance(permissions, list):
            payload["permissions"] = sorted(
                str(item) for item in cast(list[object], permissions)
            )
    if "overwrites" in payload:
        raw_overwrites = payload.get("overwrites")
        if isinstance(raw_overwrites, list):
            normalized: list[dict[str, object]] = []
            for raw_overwrite in cast(list[object], raw_overwrites):
                if not isinstance(raw_overwrite, dict):
                    continue
                overwrite = dict(cast(dict[str, object], raw_overwrite))
                allow = overwrite.get("allow")
                deny = overwrite.get("deny")
                if isinstance(allow, list):
                    overwrite["allow"] = sorted(
                        str(item) for item in cast(list[object], allow)
                    )
                if isinstance(deny, list):
                    overwrite["deny"] = sorted(
                        str(item) for item in cast(list[object], deny)
                    )
                normalized.append(overwrite)
            payload["overwrites"] = sorted(
                normalized,
                key=_overwrite_sort_key,
            )
    return payload


def _overwrite_sort_key(item: dict[str, object]) -> str:
    target = item.get("target")
    if not isinstance(target, dict):
        return ":"
    target_payload = cast(dict[str, object], target)
    return f"{target_payload.get('type', '')}:{target_payload.get('id', '')}"


def _category_name_by_id(categories: Sequence[CategorySchema]) -> dict[str, str]:
    return {category.id: category.name for category in categories if category.id}


def _channel_parent_scope(
    channel: ChannelSchema,
    *,
    prefer_name_matching: bool,
    category_name_by_id: dict[str, str],
) -> str | None:
    if prefer_name_matching:
        if channel.parent_name:
            return channel.parent_name
        if channel.parent_id:
            return category_name_by_id.get(channel.parent_id)
        return None
    return channel.parent_id or channel.parent_name


def _channel_parent_scope_from_payload(
    payload: dict[str, object],
    *,
    prefer_name_matching: bool,
    category_name_by_id: dict[str, str],
) -> str | None:
    if prefer_name_matching:
        parent_name = payload.get("parent_name")
        if isinstance(parent_name, str) and parent_name:
            return parent_name
        parent_id = payload.get("parent_id")
        if isinstance(parent_id, str) and parent_id:
            return category_name_by_id.get(parent_id)
        return None

    parent_id = payload.get("parent_id")
    if isinstance(parent_id, str) and parent_id:
        return parent_id
    parent_name = payload.get("parent_name")
    if isinstance(parent_name, str) and parent_name:
        return parent_name
    return None


def _first_unmatched_index(
    candidates: Sequence[int],
    unmatched_current: set[int],
) -> int | None:
    for candidate in candidates:
        if candidate in unmatched_current:
            return candidate
    return None


def _first_matching_named_entity_index(
    current_items: Sequence[RoleSchema | CategorySchema],
    candidates: Sequence[int],
    unmatched_current: set[int],
    desired_item: RoleSchema | CategorySchema,
) -> int | None:
    unmatched_candidates = [
        candidate for candidate in candidates if candidate in unmatched_current
    ]
    if not unmatched_candidates:
        return None
    if isinstance(desired_item, RoleSchema):
        preferred: list[int] = []
        for candidate in unmatched_candidates:
            current_item = current_items[candidate]
            if not isinstance(current_item, RoleSchema):
                continue
            if current_item.bot_managed != desired_item.bot_managed:
                continue
            preferred.append(candidate)
        if preferred:
            return preferred[0]
    return unmatched_candidates[0]


def _first_matching_payload_named_entity_index(
    current_items: Sequence[RoleSchema | CategorySchema],
    candidates: Sequence[int],
    unmatched_current: set[int],
    payload: dict[str, object],
    *,
    section: str,
) -> int | None:
    unmatched_candidates = [
        candidate for candidate in candidates if candidate in unmatched_current
    ]
    if not unmatched_candidates:
        return None
    if section == "roles":
        desired_bot_managed = payload.get("bot_managed")
        if isinstance(desired_bot_managed, bool):
            preferred: list[int] = []
            for candidate in unmatched_candidates:
                current_item = current_items[candidate]
                if not isinstance(current_item, RoleSchema):
                    continue
                if current_item.bot_managed != desired_bot_managed:
                    continue
                preferred.append(candidate)
            if preferred:
                return preferred[0]
    return unmatched_candidates[0]


__all__ = ["build_informational_changes"]
