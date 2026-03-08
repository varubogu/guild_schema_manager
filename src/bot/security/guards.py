from __future__ import annotations

from typing import Any

from bot.localization import SupportedLocale, t

from .errors import AuthorizationError


def require_guild_admin(is_admin: bool, *, locale: SupportedLocale = "en") -> None:
    if not is_admin:
        raise AuthorizationError(t("security.error.guild_admin_required", locale))


def ensure_invoker_only(
    actual_user_id: int,
    expected_user_id: int,
    *,
    locale: SupportedLocale = "en",
) -> None:
    if actual_user_id != expected_user_id:
        raise AuthorizationError(t("security.error.invoker_only_apply", locale))


def member_is_guild_admin(member: Any) -> bool:
    guild_permissions = getattr(member, "guild_permissions", None)
    if guild_permissions is None:
        return False
    return bool(getattr(guild_permissions, "administrator", False))
