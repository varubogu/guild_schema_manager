from __future__ import annotations

from bot.usecases.diff import DiffValidationError
from bot.usecases.schema_model.errors import SchemaValidationError
from bot.usecases.schema_model.models import GuildSchema
from bot.usecases.schema_model.parser import parse_schema_patch_yaml, parse_schema_yaml


def parse_uploaded_schema(
    uploaded: bytes,
    *,
    current: GuildSchema | None = None,
    file_trust_mode: bool = False,
    prefer_name_matching: bool = False,
) -> GuildSchema:
    try:
        if file_trust_mode:
            return parse_schema_yaml(uploaded)
        if current is not None:
            return parse_schema_patch_yaml(
                uploaded,
                current,
                prefer_name_matching=prefer_name_matching,
            )
        return parse_schema_yaml(uploaded)
    except (SchemaValidationError, DiffValidationError) as exc:
        raise ValueError(str(exc)) from exc


__all__ = ["parse_uploaded_schema"]
