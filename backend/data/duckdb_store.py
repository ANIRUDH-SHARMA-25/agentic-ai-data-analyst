"""Isolated in-memory analytics with predefined SQL operations only."""

from types import TracebackType
from typing import Any, Literal

import duckdb
import pandas as pd
from pandas.api.types import is_numeric_dtype

from backend.data.csv_processing import DatasetError, validate_dataframe

Aggregation = Literal["sum", "avg", "min", "max", "count"]
Comparison = Literal["=", "!=", ">", ">=", "<", "<="]


class AnalyticsError(ValueError):
    """An analytical operation could not be completed."""


class DuckDBDataset:
    """Register a private snapshot of a validated DataFrame for one session.

    Use a context manager to close the database deterministically. No public
    method accepts SQL; the later safe SQL layer must be designed separately.
    """

    def __init__(self, frame: pd.DataFrame) -> None:
        validate_dataframe(frame)
        self._frame = frame.copy(deep=True)
        self._connection = duckdb.connect(":memory:")
        self._closed = False
        try:
            self._connection.register("dataset", self._frame)
        except duckdb.Error as exc:
            self.close()
            raise AnalyticsError(f"Could not register dataset: {exc}") from exc

    def __enter__(self) -> "DuckDBDataset":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def _column(self, name: str) -> str:
        if name not in self._frame.columns:
            raise AnalyticsError(f"Unknown column: {name}")
        return '"' + name.replace('"', '""') + '"'

    def _execute(self, sql: str, parameters: list[Any] | None = None) -> pd.DataFrame:
        if self._closed:
            raise AnalyticsError("Dataset session is closed.")
        try:
            return self._connection.execute(sql, parameters or []).fetchdf()
        except duckdb.Error as exc:
            raise AnalyticsError(f"Analysis failed: {exc}") from exc

    def aggregate(
        self, column: str, operation: Aggregation = "sum", *, group_by: str | None = None
    ) -> pd.DataFrame:
        """Aggregate a column, optionally grouped; count excludes missing cells."""
        if operation not in {"sum", "avg", "min", "max", "count"}:
            raise AnalyticsError("Unsupported aggregation operation.")
        target = self._column(column)
        if operation != "count" and not is_numeric_dtype(self._frame[column]):
            raise AnalyticsError("This aggregation requires a numeric column.")
        expression = f'{operation.upper()}({target}) AS "value"'
        if group_by is None:
            return self._execute(f"SELECT {expression} FROM dataset")
        grouping = self._column(group_by)
        return self._execute(
            f"SELECT {grouping}, {expression} FROM dataset "
            f"GROUP BY {grouping} ORDER BY {grouping}"
        )

    def filter_rows(
        self, column: str, value: Any, *, operator: Comparison = "=", limit: int = 100
    ) -> pd.DataFrame:
        """Filter with a bound value and cap the result at 1,000 rows.

        None supports equality/inequality via SQL IS NULL / IS NOT NULL.
        Result row ordering is unspecified.
        """
        target = self._column(column)
        if operator not in {"=", "!=", ">", ">=", "<", "<="}:
            raise AnalyticsError("Unsupported comparison operator.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise AnalyticsError("Limit must be an integer between 1 and 1000.")
        if value is None:
            if operator not in {"=", "!="}:
                raise AnalyticsError("Missing values support only equality or inequality.")
            predicate = f"{target} IS {'NOT ' if operator == '!=' else ''}NULL"
            parameters = [limit]
        else:
            predicate = f"{target} {operator} ?"
            parameters = [value, limit]
        return self._execute(f"SELECT * FROM dataset WHERE {predicate} LIMIT ?", parameters)
