from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


OverwriteTargetType = Literal["role", "member"]
ChannelType = Literal["text", "voice", "news", "stage_voice", "forum", "media"]


@dataclass(slots=True)
class OverwriteTarget:
    type: OverwriteTargetType
    id: str


@dataclass(slots=True)
class PermissionOverwrite:
    target: OverwriteTarget
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GuildInfo:
    id: str
    name: str


@dataclass(slots=True)
class RoleSchema:
    name: str
    id: str | None = None
    color: int = 0
    hoist: bool = False
    mentionable: bool = False
    permissions: list[str] = field(default_factory=list)
    position: int = 0


@dataclass(slots=True)
class CategorySchema:
    name: str
    id: str | None = None
    position: int = 0
    overwrites: list[PermissionOverwrite] = field(default_factory=list)


@dataclass(slots=True)
class ChannelSchema:
    name: str
    type: ChannelType
    id: str | None = None
    parent_id: str | None = None
    parent_name: str | None = None
    position: int = 0
    topic: str | None = None
    nsfw: bool = False
    slowmode_delay: int = 0
    overwrites: list[PermissionOverwrite] = field(default_factory=list)


@dataclass(slots=True)
class GuildSchema:
    version: int
    guild: GuildInfo
    roles: list[RoleSchema] = field(default_factory=list)
    categories: list[CategorySchema] = field(default_factory=list)
    channels: list[ChannelSchema] = field(default_factory=list)
