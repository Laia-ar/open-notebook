import re
from typing import ClassVar, Optional
from pydantic import field_validator
from open_notebook.domain.base import ObjectModel


class User(ObjectModel):
    table_name: ClassVar[str] = "app_user"

    name: str
    email: str
    avatar_url: Optional[str] = None
    is_active: bool = True
    last_login: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("User name cannot be empty")

        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise ValueError("User email cannot be empty")

        # Validacion de email (no se agregar una dependencia nueva)
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if not re.match(email_pattern, value):
            raise ValueError("Invalid user email")

        return value