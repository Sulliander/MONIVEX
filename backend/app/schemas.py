from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, Field, field_validator

Username = Annotated[
    str, Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
]


class LoginInput(BaseModel):
    username: Username
    password: str = Field(min_length=1, max_length=256)


class SetupInput(LoginInput):
    password: str = Field(min_length=12, max_length=256)
    installation_name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="Europe/Warsaw", max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Nieprawidłowa strefa czasowa")
        return value


class PasswordInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)
