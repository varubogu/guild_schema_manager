from __future__ import annotations

from dataclasses import dataclass

from bot.usecases.planner import ApplyReport


@dataclass(slots=True)
class FilePayload:
    filename: str
    content: bytes


@dataclass(slots=True)
class ExportResponse:
    markdown: str
    file: FilePayload


@dataclass(slots=True)
class DiffResponse:
    markdown: str


@dataclass(slots=True, frozen=True)
class ExportFieldSelection:
    include_name: bool = True
    include_permissions: bool = True
    include_role_overwrites: bool = True
    include_other_settings: bool = True


@dataclass(slots=True)
class ApplyPreviewResponse:
    markdown: str
    confirmation_token: str | None


@dataclass(slots=True)
class ApplyExecutionResponse:
    markdown: str
    backup_file: FilePayload | None
    report: ApplyReport | None


__all__ = [
    "ApplyExecutionResponse",
    "ApplyPreviewResponse",
    "DiffResponse",
    "ExportFieldSelection",
    "ExportResponse",
    "FilePayload",
]
