"""Strict, bounded UTF-8 CSV loading and JSON-compatible dataset inspection."""

import csv
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_MAX_BYTES = 10 * 1024 * 1024


class DatasetError(ValueError):
    """A dataset cannot be loaded or inspected."""


def validate_dataframe(frame: pd.DataFrame) -> None:
    """Reject empty datasets and ambiguous or unusable column names."""
    if not isinstance(frame, pd.DataFrame):
        raise DatasetError("Expected a Pandas DataFrame.")
    if frame.empty:
        raise DatasetError("Dataset must contain at least one row and one column.")
    names = list(frame.columns)
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise DatasetError("Column names must be non-empty strings.")
    if len(set(names)) != len(names):
        raise DatasetError("Column names must be unique.")


def load_csv(path: str | Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> pd.DataFrame:
    """Load a local comma-delimited CSV, rejecting malformed records before Pandas.

    Only UTF-8 (optionally with a BOM) is accepted. Blank physical lines are
    ignored; missing cells in records are retained. Dates stay as strings.
    """
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise DatasetError("max_bytes must be a positive integer.")
    source = Path(path)
    if source.suffix.lower() != ".csv":
        raise DatasetError("Only .csv files are supported.")
    try:
        # A bounded read also protects against files growing after a size check.
        with source.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
    except OSError as exc:
        raise DatasetError(f"Could not read CSV file: {exc}") from exc
    if len(payload) > max_bytes:
        raise DatasetError(f"CSV exceeds the {max_bytes}-byte size limit.")
    try:
        content = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetError("CSV must use UTF-8 encoding.") from exc
    if not content.strip():
        raise DatasetError("CSV is empty.")
    if "\x00" in content:
        raise DatasetError("CSV contains invalid null bytes.")

    try:
        records = csv.reader(io.StringIO(content, newline=""), strict=True)
        header = next((row for row in records if row), None)
        if header is None or any(not name.strip() for name in header):
            raise DatasetError("CSV must have non-empty column names.")
        if len(set(header)) != len(header):
            raise DatasetError("CSV column names must be unique.")
        row_count = 0
        for row in records:
            if not row:
                continue
            if len(row) != len(header):
                raise DatasetError(
                    f"Malformed CSV at line {records.line_num}: expected "
                    f"{len(header)} fields, found {len(row)}."
                )
            row_count += 1
        if row_count == 0:
            raise DatasetError("CSV has a header but no data rows.")
        frame = pd.read_csv(io.StringIO(content), on_bad_lines="error")
    except (csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DatasetError(f"Malformed CSV: {exc}") from exc
    validate_dataframe(frame)
    return frame


def dataset_preview(frame: pd.DataFrame, *, rows: int = 5) -> list[dict[str, Any]]:
    """Return up to 20 rows, converting missing/nonfinite values to JSON null."""
    validate_dataframe(frame)
    if isinstance(rows, bool) or not isinstance(rows, int) or not 1 <= rows <= 20:
        raise DatasetError("Preview rows must be an integer between 1 and 20.")
    return json.loads(frame.head(rows).to_json(orient="records", date_format="iso"))


def inspect_dataset(frame: pd.DataFrame, *, preview_rows: int = 5) -> dict[str, Any]:
    """Report dimensions, inferred types, missing values, and descriptive stats.

    Numeric columns include mean, standard deviation, and quartiles; other
    columns include unique values and the most frequent value. Missing and infinite numeric values
    are excluded from descriptive statistics and reported separately.
    """
    validate_dataframe(frame)
    return {
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": list(frame.columns),
        "dtypes": {name: str(dtype) for name, dtype in frame.dtypes.items()},
        "missing_values": {name: int(count) for name, count in frame.isna().sum().items()},
        "statistics": json.loads(frame.replace([np.inf, -np.inf], np.nan).describe(include="all").to_json(date_format="iso")),
        "preview": dataset_preview(frame, rows=preview_rows),
    }
