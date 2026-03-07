from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeAlias, cast

import discord

from bot.planner.models import ApplyOperation

from .errors import SkipOperationError


DUSTBOX_CATEGORY_NAME = "GSM-Dustbox"
OverwriteTarget: TypeAlias = discord.Role | discord.Member
OverwriteKey: TypeAlias = OverwriteTarget | discord.Object
ManagedChannel: TypeAlias = (
    discord.TextChannel
    | discord.VoiceChannel
    | discord.StageChannel
    | discord.ForumChannel
)
PermissionOwner: TypeAlias = ManagedChannel | discord.CategoryChannel


class DiscordGuildExecutor:
    def __init__(self, guild: discord.Guild) -> None:
        self._guild = guild

    async def execute(self, operation: ApplyOperation) -> None:
        if operation.target_type == "role":
            await self._execute_role(operation)
            return
        if operation.target_type == "category":
            await self._execute_category(operation)
            return
        if operation.target_type == "channel":
            await self._execute_channel(operation)
            return
        if operation.target_type == "overwrite":
            await self._execute_overwrite(operation)
            return

        raise SkipOperationError(f"unsupported target_type: {operation.target_type}")

    async def _execute_role(self, operation: ApplyOperation) -> None:
        if operation.action == "Create":
            payload = operation.after or {}
            role = await self._guild.create_role(
                name=str(payload.get("name", "new-role")),
                colour=discord.Colour(int(payload.get("color", 0))),
                hoist=bool(payload.get("hoist", False)),
                mentionable=bool(payload.get("mentionable", False)),
                permissions=self._permissions_from_names(
                    payload.get("permissions", [])
                ),
            )
            if "position" in payload:
                await role.edit(position=int(payload["position"]))
            return

        role = self._find_role(operation)
        if role is None:
            raise SkipOperationError("role not found")

        if operation.action == "Delete":
            raise SkipOperationError(
                "role delete is disabled; delete the role manually"
            )

        if operation.action == "Reorder":
            position = int((operation.after or {}).get("position", role.position))
            await role.edit(position=position)
            return

        if operation.action == "Update":
            payload = operation.after or {}
            edit_kwargs: dict[str, Any] = {}
            if "name" in payload:
                edit_kwargs["name"] = payload["name"]
            if "color" in payload:
                edit_kwargs["colour"] = discord.Colour(int(payload["color"]))
            if "hoist" in payload:
                edit_kwargs["hoist"] = bool(payload["hoist"])
            if "mentionable" in payload:
                edit_kwargs["mentionable"] = bool(payload["mentionable"])
            if "permissions" in payload:
                edit_kwargs["permissions"] = self._permissions_from_names(
                    payload["permissions"]
                )
            if edit_kwargs:
                await role.edit(**edit_kwargs)
            return

        raise SkipOperationError(f"unsupported role action: {operation.action}")

    async def _execute_category(self, operation: ApplyOperation) -> None:
        if operation.action == "Create":
            payload = operation.after or {}
            await self._guild.create_category(
                name=str(payload.get("name", "new-category")),
                position=int(payload.get("position", 0)),
                overwrites=self._overwrites_from_payload(payload.get("overwrites", [])),
            )
            return

        category = self._find_category(operation)
        if category is None:
            raise SkipOperationError("category not found")

        if operation.action == "Delete":
            dustbox = await self._ensure_dustbox_category()
            for child in list(category.channels):
                movable = self._as_managed_channel(child)
                if movable is None:
                    continue
                await movable.edit(category=dustbox, reason="schema apply dustbox move")
            archived_name = self._truncate_name(f"GSM-DeleteMe-{category.name}")
            await category.edit(
                name=archived_name,
                overwrites=self._admin_only_overwrites(),
                reason="schema apply dustbox archive",
            )
            return

        if operation.action == "Reorder":
            position = int((operation.after or {}).get("position", category.position))
            await category.edit(position=position)
            return

        if operation.action == "Update":
            payload = operation.after or {}
            edit_kwargs: dict[str, Any] = {}
            if "name" in payload:
                edit_kwargs["name"] = payload["name"]
            if edit_kwargs:
                await category.edit(**edit_kwargs)
            return

        raise SkipOperationError(f"unsupported category action: {operation.action}")

    async def _execute_channel(self, operation: ApplyOperation) -> None:
        if operation.action == "Create":
            payload = operation.after or {}
            await self._create_channel(payload)
            return

        channel = self._find_channel(operation)
        if channel is None:
            raise SkipOperationError("channel not found")

        if operation.action == "Delete":
            dustbox = await self._ensure_dustbox_category()
            await channel.edit(category=dustbox, reason="schema apply dustbox move")
            return

        if operation.action == "Move":
            parent_ref = (operation.after or {}).get("parent")
            category = self._resolve_category_ref(parent_ref)
            await channel.edit(category=category)
            return

        if operation.action == "Reorder":
            position = int(
                (operation.after or {}).get("position", getattr(channel, "position", 0))
            )
            await channel.edit(position=position)
            return

        if operation.action == "Update":
            payload = operation.after or {}
            if "type" in payload:
                raise SkipOperationError("channel type update is not supported")

            edit_kwargs: dict[str, Any] = {}
            if "name" in payload:
                edit_kwargs["name"] = payload["name"]
            if "topic" in payload and hasattr(channel, "topic"):
                edit_kwargs["topic"] = payload["topic"]
            if "nsfw" in payload and hasattr(channel, "nsfw"):
                edit_kwargs["nsfw"] = bool(payload["nsfw"])
            if "slowmode_delay" in payload and hasattr(channel, "slowmode_delay"):
                edit_kwargs["slowmode_delay"] = int(payload["slowmode_delay"])
            if edit_kwargs:
                await channel.edit(**edit_kwargs)
            return

        raise SkipOperationError(f"unsupported channel action: {operation.action}")

    async def _execute_overwrite(self, operation: ApplyOperation) -> None:
        owner_type, owner_id, target_type, target_id = self._parse_overwrite_target(
            operation.target_id
        )
        owner = self._resolve_owner(owner_type, owner_id)
        if owner is None:
            raise SkipOperationError("overwrite owner not found")

        target = self._resolve_overwrite_target(target_type, target_id)
        if target is None:
            raise SkipOperationError("overwrite target not found")

        if operation.action == "Delete":
            await owner.set_permissions(target, overwrite=None, reason="schema apply")
            return

        payload = operation.after or {}
        overwrite = self._permission_overwrite_from_payload(payload)
        await owner.set_permissions(target, overwrite=overwrite, reason="schema apply")

    async def _create_channel(self, payload: dict[str, Any]) -> None:
        channel_type = str(payload.get("type", "text"))
        name = str(payload.get("name", "new-channel"))
        parent = self._resolve_category_ref(
            payload.get("parent_id") or payload.get("parent_name")
        )
        common_kwargs: dict[str, Any] = {
            "position": int(payload.get("position", 0)),
            "overwrites": self._overwrites_from_payload(payload.get("overwrites", [])),
            "category": parent,
        }
        text_kwargs = self._text_channel_kwargs(payload)

        if channel_type == "text":
            await self._guild.create_text_channel(
                name=name,
                **text_kwargs,
                **common_kwargs,
            )
            return

        if channel_type == "news":
            await self._guild.create_text_channel(
                name=name,
                news=True,
                **text_kwargs,
                **common_kwargs,
            )
            return

        if channel_type == "voice":
            await self._guild.create_voice_channel(name=name, **common_kwargs)
            return

        if channel_type == "stage_voice":
            await self._guild.create_stage_channel(
                name=name,
                nsfw=bool(payload.get("nsfw", False)),
                **common_kwargs,
            )
            return

        if channel_type == "forum":
            await self._guild.create_forum(
                name=name,
                **self._forum_channel_kwargs(payload),
                **common_kwargs,
            )
            return

        if channel_type == "media":
            await self._guild.create_forum(
                name=name,
                **self._forum_channel_kwargs(payload, media=True),
                **common_kwargs,
            )
            return

        raise SkipOperationError(f"unsupported channel type: {channel_type}")

    def _find_role(self, operation: ApplyOperation) -> discord.Role | None:
        if operation.target_id and str(operation.target_id).isdigit():
            role = self._guild.get_role(int(operation.target_id))
            if role is not None:
                return role

        names = [
            (operation.after or {}).get("name"),
            (operation.before or {}).get("name"),
        ]
        for name in names:
            if not name:
                continue
            role = discord.utils.get(self._guild.roles, name=name)
            if role is not None:
                return role
        return None

    def _find_category(
        self, operation: ApplyOperation
    ) -> discord.CategoryChannel | None:
        if operation.target_id and str(operation.target_id).isdigit():
            channel = self._guild.get_channel(int(operation.target_id))
            if isinstance(channel, discord.CategoryChannel):
                return channel

        names = [
            (operation.after or {}).get("name"),
            (operation.before or {}).get("name"),
        ]
        for name in names:
            if not name:
                continue
            category = discord.utils.get(self._guild.categories, name=name)
            if category is not None:
                return category
        return None

    def _find_channel(self, operation: ApplyOperation) -> ManagedChannel | None:
        if operation.target_id and str(operation.target_id).isdigit():
            channel = self._guild.get_channel(int(operation.target_id))
            managed = self._as_managed_channel(channel)
            if managed is not None:
                return managed

        names = [
            (operation.after or {}).get("name"),
            (operation.before or {}).get("name"),
        ]
        for name in names:
            if not name:
                continue
            channel = discord.utils.get(self._guild.channels, name=name)
            managed = self._as_managed_channel(channel)
            if managed is not None:
                return managed
        return None

    def _resolve_category_ref(self, ref: Any) -> discord.CategoryChannel | None:
        if ref is None:
            return None

        ref_text = str(ref)
        if ref_text.isdigit():
            channel = self._guild.get_channel(int(ref_text))
            if isinstance(channel, discord.CategoryChannel):
                return channel
            return None

        return discord.utils.get(self._guild.categories, name=ref_text)

    def _resolve_owner(self, owner_type: str, owner_id: str) -> PermissionOwner | None:
        if not owner_id or owner_id == "None" or not owner_id.isdigit():
            return None
        channel = self._guild.get_channel(int(owner_id))
        if owner_type == "category" and isinstance(channel, discord.CategoryChannel):
            return channel
        if owner_type == "channel":
            managed = self._as_managed_channel(channel)
            if managed is not None:
                return managed
        return None

    async def _ensure_dustbox_category(self) -> discord.CategoryChannel:
        existing = discord.utils.get(self._guild.categories, name=DUSTBOX_CATEGORY_NAME)
        if existing is not None:
            return existing

        return await self._guild.create_category(
            name=DUSTBOX_CATEGORY_NAME,
            overwrites=self._admin_only_overwrites(),
            reason="schema apply dustbox setup",
        )

    def _admin_only_overwrites(
        self,
    ) -> dict[OverwriteKey, discord.PermissionOverwrite]:
        overwrites: dict[OverwriteKey, discord.PermissionOverwrite] = {}

        everyone = self._guild.default_role
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=False)

        for role in self._guild.roles:
            if getattr(role.permissions, "administrator", False):
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_message_history=True,
                    send_messages=True,
                )

        me = self._guild.me
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            manage_channels=True,
        )

        return overwrites

    def _truncate_name(self, value: str, max_length: int = 100) -> str:
        if len(value) <= max_length:
            return value
        return value[:max_length]

    def _resolve_overwrite_target(
        self, target_type: str, target_id: str
    ) -> OverwriteTarget | None:
        if not target_id or not target_id.isdigit():
            return None
        if target_type == "role":
            return self._guild.get_role(int(target_id))
        if target_type == "member":
            return self._guild.get_member(int(target_id))
        return None

    def _parse_overwrite_target(
        self, target_id: str | None
    ) -> tuple[str, str, str, str]:
        if not target_id:
            raise SkipOperationError("overwrite target id is empty")
        parts = target_id.split(":")
        if len(parts) != 4:
            raise SkipOperationError(f"invalid overwrite target id: {target_id}")
        owner_type, owner_id, target_type, resolved_target_id = parts
        return owner_type, owner_id, target_type, resolved_target_id

    def _as_managed_channel(self, channel: object) -> ManagedChannel | None:
        if isinstance(
            channel,
            (
                discord.TextChannel,
                discord.VoiceChannel,
                discord.StageChannel,
                discord.ForumChannel,
            ),
        ):
            return channel
        return None

    def _text_channel_kwargs(self, payload: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "nsfw": bool(payload.get("nsfw", False)),
            "slowmode_delay": int(payload.get("slowmode_delay", 0)),
        }
        topic = payload.get("topic")
        if isinstance(topic, str):
            kwargs["topic"] = topic
        return kwargs

    def _forum_channel_kwargs(
        self, payload: dict[str, Any], *, media: bool = False
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "nsfw": bool(payload.get("nsfw", False)),
            "slowmode_delay": int(payload.get("slowmode_delay", 0)),
        }
        topic = payload.get("topic")
        if isinstance(topic, str):
            kwargs["topic"] = topic
        if media:
            kwargs["media"] = True
        return kwargs

    def _permissions_from_names(self, names: object) -> discord.Permissions:
        permissions = discord.Permissions.none()
        for name in _string_values(names):
            if hasattr(permissions, name):
                setattr(permissions, name, True)
        return permissions

    def _permission_overwrite_from_payload(
        self, payload: Mapping[str, object]
    ) -> discord.PermissionOverwrite:
        overwrite = discord.PermissionOverwrite()
        for name in _string_values(payload.get("allow")):
            setattr(overwrite, name, True)
        for name in _string_values(payload.get("deny")):
            setattr(overwrite, name, False)
        return overwrite

    def _overwrites_from_payload(
        self, payload: object
    ) -> dict[OverwriteKey, discord.PermissionOverwrite]:
        if not isinstance(payload, list):
            return {}
        entries = cast(list[object], payload)

        result: dict[OverwriteKey, discord.PermissionOverwrite] = {}
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                continue
            entry = cast(dict[str, object], raw_entry)
            target_obj = entry.get("target")
            if not isinstance(target_obj, dict):
                continue
            target = cast(dict[str, object], target_obj)
            target_type = str(target.get("type", ""))
            target_id = str(target.get("id", ""))
            resolved = self._resolve_overwrite_target(target_type, target_id)
            if resolved is None:
                continue
            result[resolved] = self._permission_overwrite_from_payload(entry)
        return result


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
    return result
