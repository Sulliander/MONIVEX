from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Id = Annotated[int, Field(gt=0)]
Priority = Literal["low", "normal", "high", "critical"]


class Links(BaseModel):
    group_id: Id | None = None
    resource_id: Id | None = None
    tag_ids: list[Id] = Field(default_factory=list, max_length=50)
    priority: Priority = "normal"


class GroupInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    parent_id: Id | None = None
    revision: int | None = Field(default=None, ge=1)


class TagInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    revision: int | None = Field(default=None, ge=1)


class ResourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    address: str = Field(default="", max_length=253, pattern=r"^[A-Za-z0-9.:_-]*$")
    kind: Literal["server", "network", "website", "service", "other"] = "server"
    operating_system: str = Field(default="", max_length=100)
    environment: str = Field(default="", max_length=50)
    group_id: Id | None = None
    tag_ids: list[Id] = Field(default_factory=list, max_length=50)
    revision: int | None = Field(default=None, ge=1)


class BulkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monitor_ids: list[Id] = Field(min_length=1, max_length=100)
    revisions: dict[int, int]
    operation: Literal["configure", "pause", "resume", "delete"]
    interval: int | None = Field(default=None, ge=10, le=86400)
    timeout: float | None = Field(default=None, ge=0.1, le=30)
    failure_threshold: int | None = Field(default=None, ge=1, le=20)
    recovery_threshold: int | None = Field(default=None, ge=1, le=20)
    priority: Priority | None = None
    group_id: Id | None = None
    resource_id: Id | None = None
    tag_ids: list[Id] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def distinct(self):
        if (
            len(set(self.monitor_ids)) != len(self.monitor_ids)
            or set(self.revisions) != set(self.monitor_ids)
            or any(v < 1 for v in self.revisions.values())
        ):
            raise ValueError("Nieprawidłowa lista monitorów lub rewizji.")
        if self.operation == "configure" and not self.model_fields_set.intersection(
            {
                "interval",
                "timeout",
                "failure_threshold",
                "recovery_threshold",
                "priority",
                "group_id",
                "resource_id",
                "tag_ids",
            }
        ):
            raise ValueError("Wybierz ustawienia do zmiany.")
        if self.operation != "configure" and self.model_fields_set.intersection(
            {
                "interval",
                "timeout",
                "failure_threshold",
                "recovery_threshold",
                "priority",
                "group_id",
                "resource_id",
                "tag_ids",
            }
        ):
            raise ValueError("Ustawienia można podać tylko dla operacji konfiguracji.")
        for key in {
            "interval",
            "timeout",
            "failure_threshold",
            "recovery_threshold",
            "priority",
            "tag_ids",
        } & self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError("Pole nie może być puste.")
        return self
