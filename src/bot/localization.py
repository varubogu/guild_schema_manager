from __future__ import annotations

import threading
from importlib import resources
from typing import Any, Literal, cast

import i18n as i18n_module  # pyright: ignore[reportMissingTypeStubs]
import yaml

SupportedLocale = Literal["ja", "en"]
SUPPORTED_LOCALES: tuple[SupportedLocale, ...] = ("ja", "en")
MESSAGE_LOCALE_SUFFIXES = frozenset(SUPPORTED_LOCALES)
_I18N = cast(Any, i18n_module)

REQUIRED_MESSAGE_IDS: tuple[str, ...] = (
    "schema.group.description",
    "schema.command.export.description",
    "schema.command.diff.description",
    "schema.command.apply.description",
    "schema.argument.file.description",
    "schema.argument.file_trust_mode.description",
    "schema.argument.export.include_name.description",
    "schema.argument.export.include_permissions.description",
    "schema.argument.export.include_role_overwrites.description",
    "schema.argument.export.include_other_settings.description",
    "ui.button.guild_id_override.approve",
    "ui.button.cancel",
    "ui.button.confirm_apply",
    "ui.error.invoker_only_confirmation_response",
    "ui.guild_id_override.approved",
    "ui.guild_id_override.canceled",
    "ui.error.guild_required",
    "ui.error.apply_unexpected",
    "ui.guild_id_override.prompt",
    "ui.guild_id_override.timed_out",
    "ui.error.validation",
    "security.error.guild_admin_required",
    "security.error.invoker_only_apply",
    "service.export.summary",
    "service.export.filtered_suffix",
    "service.apply.no_changes",
    "service.apply.confirmation_token",
    "service.apply.session_not_found",
    "service.apply.session_expired",
    "service.apply.session_forbidden",
    "service.apply.session_error",
    "render.diff.title",
    "render.diff.summary_line",
    "render.diff.column.action",
    "render.diff.column.target_type",
    "render.diff.column.target_id",
    "render.diff.column.before_name",
    "render.diff.column.after_name",
    "render.diff.column.risk",
    "render.diff.column.before",
    "render.diff.column.after",
    "render.apply.title",
    "render.apply.summary_line",
    "render.apply.section.failed",
    "render.apply.section.skipped",
    "render.apply.item.failed",
    "render.apply.item.skipped",
    "render.action.create",
    "render.action.update",
    "render.action.delete",
    "render.action.move",
    "render.action.reorder",
    "render.target_type.role",
    "render.target_type.category",
    "render.target_type.channel",
    "render.target_type.overwrite",
    "render.risk.low",
    "render.risk.medium",
    "render.risk.high",
)

_init_lock = threading.Lock()
_initialized = False


def resolve_user_locale(raw_locale: object | None) -> SupportedLocale:
    if raw_locale is None:
        return "en"
    normalized = str(raw_locale).lower().replace("_", "-")
    if normalized.startswith("ja"):
        return "ja"
    return "en"


def t(message_id: str, locale: SupportedLocale, **kwargs: object) -> str:
    initialize_localization()
    translated = str(_I18N.t(message_id, locale=locale, **kwargs))
    if translated != message_id:
        return translated
    if locale != "en":
        fallback = str(_I18N.t(message_id, locale="en", **kwargs))
        if fallback != message_id:
            return fallback
    return translated


def has_message_id(message_id: str) -> bool:
    initialize_localization()
    return all(
        bool(_I18N.translations.has(message_id, locale=locale))
        for locale in SUPPORTED_LOCALES
    )


def initialize_localization() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        catalog = _load_message_catalog()
        _configure_i18n()
        _register_catalog(catalog)
        _validate_required_message_ids(catalog)
        _initialized = True


def _load_message_catalog() -> dict[str, dict[SupportedLocale, str]]:
    raw_text = (
        resources.files("bot").joinpath("messages.yaml").read_text(encoding="utf-8")
    )
    raw_catalog_obj = yaml.safe_load(raw_text)
    if not isinstance(raw_catalog_obj, dict):
        raise RuntimeError("messages.yaml must be a mapping")
    raw_catalog = cast(dict[object, object], raw_catalog_obj)

    catalog: dict[str, dict[SupportedLocale, str]] = {}
    for key_obj, value_obj in raw_catalog.items():
        if not isinstance(key_obj, str):
            raise RuntimeError("message id must be a string")
        if not isinstance(value_obj, dict):
            raise RuntimeError(f"message '{key_obj}' must define locale map")
        raw_locale_map = cast(dict[object, object], value_obj)

        unexpected_locales = set(raw_locale_map) - MESSAGE_LOCALE_SUFFIXES
        if unexpected_locales:
            names = ", ".join(sorted(str(item) for item in unexpected_locales))
            raise RuntimeError(
                f"message '{key_obj}' has unsupported locale keys: {names}"
            )

        locale_map: dict[SupportedLocale, str] = {}
        for locale in SUPPORTED_LOCALES:
            translated_obj = raw_locale_map.get(locale)
            if not isinstance(translated_obj, str) or translated_obj == "":
                raise RuntimeError(
                    f"message '{key_obj}.{locale}' must be a non-empty string"
                )
            locale_map[locale] = translated_obj
        catalog[key_obj] = locale_map

    return catalog


def _configure_i18n() -> None:
    _I18N.set("fallback", "en")
    _I18N.set("enable_memoization", False)
    _I18N.set("available_locales", list(SUPPORTED_LOCALES))
    _I18N.translations.container.clear()


def _register_catalog(catalog: dict[str, dict[SupportedLocale, str]]) -> None:
    for message_id, locale_map in catalog.items():
        for locale in SUPPORTED_LOCALES:
            _I18N.translations.add(message_id, locale_map[locale], locale=locale)


def _validate_required_message_ids(
    catalog: dict[str, dict[SupportedLocale, str]],
) -> None:
    missing = sorted(set(REQUIRED_MESSAGE_IDS) - set(catalog))
    if missing:
        raise RuntimeError(f"messages.yaml missing keys: {', '.join(missing)}")


initialize_localization()
