"""Typed API responses; multipart File and UUID path parameters type requests."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    detail: str


class UploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: UUID
    row_count: int = Field(ge=1)
    column_count: int = Field(ge=1)
    columns: list[str]
    dtypes: dict[str, str]
    preview: list[dict[str, JsonValue]]


class DatasetResponse(UploadResponse):
    missing_values: dict[str, int]
    statistics: dict[str, dict[str, JsonValue]]
