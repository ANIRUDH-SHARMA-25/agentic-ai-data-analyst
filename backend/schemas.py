"""Typed API responses; multipart File and UUID path parameters type requests."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


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


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: UUID
    question: str = Field(min_length=1, max_length=2000, strict=True)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value or not any(character.isalnum() for character in value):
            raise ValueError("Question must contain meaningful text.")
        if any(ord(character) < 32 and character not in "\n\t" for character in value):
            raise ValueError("Question contains unsupported control characters.")
        return value


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=16000)
    sql: str | None = None
    columns: list[str]
    rows: list[list[JsonValue]]
    row_count: int = Field(ge=0, le=1000)
    tools_used: list[str] = Field(default_factory=list, max_length=10)
