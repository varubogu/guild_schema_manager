from __future__ import annotations

from typing import Any

from .errors import AuthorizationError


def require_guild_admin(is_admin: bool) -> None:
    if not is_admin:
        raise AuthorizationError("Guild administrator permission is required")


def ensure_invoker_only(actual_user_id: int, expected_user_id: int) -> None:
    if actual_user_id != expected_user_id:
        raise AuthorizationError("Only the original invoker can confirm this apply")


def member_is_guild_admin(member: Any) -> bool:
    guild_permissions = getattr(member, "guild_permissions", None)
    if guild_permissions is None:
        return False
    return bool(getattr(guild_permissions, "administrator", False))
