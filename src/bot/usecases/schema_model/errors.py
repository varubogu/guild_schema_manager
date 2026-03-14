from __future__ import annotations


class SchemaValidationError(ValueError):
    def __init__(self, message: str, field_path: str = "") -> None:
        self.message = message
        self.field_path = field_path
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.field_path:
            return f"{self.field_path}: {self.message}"
        return self.message
