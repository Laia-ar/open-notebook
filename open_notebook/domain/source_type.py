from typing import ClassVar

from pydantic import field_validator

from open_notebook.domain.base import ObjectModel


class SourceType(ObjectModel):
    table_name: ClassVar[str] = "source_type"

    name: str
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Source type name cannot be empty")

        return value