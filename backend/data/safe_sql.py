"""Fail-closed SQL subset and bounded embedded DuckDB execution.

Defense in depth only: the embedded engine is not a complete security sandbox.
"""

import json
import math
from datetime import date, datetime, time
from decimal import Decimal
from dataclasses import dataclass
from threading import Event, Timer
from typing import Any

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from backend.data.csv_processing import validate_dataframe


class SQLValidationError(ValueError):
    """SQL falls outside the explicitly supported analytical subset."""


class SQLExecutionError(RuntimeError):
    """A validated query could not produce a bounded result."""


class SQLTimeoutError(SQLExecutionError):
    """The query exceeded its execution deadline."""


@dataclass(frozen=True)
class SQLLimits:
    max_rows: int = 200
    timeout_seconds: float = 5.0
    memory_mb: int = 128
    max_result_bytes: int = 128 * 1024

    def __post_init__(self) -> None:
        for name in ("max_rows", "memory_mb", "max_result_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        if not 0 < self.timeout_seconds <= 30:
            raise ValueError("SQL timeout must be between 0 and 30 seconds.")
        if self.max_rows > 1000 or self.memory_mb > 512:
            raise ValueError("SQL row/memory limits exceed the local-phase maximum.")


# Exact expression classes, not base-class checks: new parser constructs fail closed.
SAFE_FUNCTIONS = {
    exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Count,
    exp.Abs, exp.Round, exp.Lower, exp.Upper, exp.Length, exp.Coalesce,
}
SAFE_NODES = SAFE_FUNCTIONS | {
    exp.Select, exp.From, exp.Table, exp.TableAlias, exp.Identifier, exp.Column,
    exp.Alias, exp.Star, exp.Literal, exp.Null, exp.Boolean, exp.Distinct,
    exp.Where, exp.Group, exp.Having, exp.Order, exp.Ordered, exp.Limit, exp.Paren,
    exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.Neg,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.And, exp.Or, exp.Not, exp.Is, exp.Between, exp.In,
    exp.Like, exp.ILike,
}


def validate_sql(query: str, columns: list[str], *, max_rows: int = 200) -> str:
    """Return canonical SQL with a clamped LIMIT, or reject the entire query."""
    if not isinstance(query, str) or not query.strip() or len(query) > 8000:
        raise SQLValidationError("SQL must contain 1 to 8000 characters.")
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or not 1 <= max_rows <= 1000:
        raise ValueError("max_rows must be between 1 and 1000.")
    try:
        statements = [node for node in sqlglot.parse(query, read="duckdb") if node is not None and not (type(node) is exp.Semicolon and not node.args)]
    except (ParseError, TokenError, RecursionError) as exc:
        raise SQLValidationError("SQL syntax is invalid.") from exc
    if len(statements) != 1 or type(statements[0]) is not exp.Select:
        raise SQLValidationError("Exactly one SELECT query is required.")
    tree = statements[0]
    nodes = list(tree.walk())
    if len(nodes) > 256:
        raise SQLValidationError("SQL is too complex for this phase.")
    if any(type(node) not in SAFE_NODES for node in nodes):
        raise SQLValidationError("SQL contains an unsupported function or structure.")
    if sum(type(node) is exp.Select for node in nodes) != 1:
        raise SQLValidationError("Nested SELECT queries are not supported.")
    # Only these top-level clauses are part of our supported grammar.
    supported_clauses = {"expressions", "from_", "where", "group", "having", "order", "limit", "distinct"}
    if any(value and name not in supported_clauses for name, value in tree.args.items()):
        raise SQLValidationError("SQL contains an unsupported SELECT clause.")
    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1:
        raise SQLValidationError("Query must read only the dataset table.")
    table = tables[0]
    if (type(table.this) is not exp.Identifier or table.name.casefold() != "dataset"
            or table.args.get("db") or table.args.get("catalog")):
        raise SQLValidationError("Query must read only the dataset table.")
    if any(value and name not in {"this", "alias"} for name, value in table.args.items()):
        raise SQLValidationError("Unsupported table reference.")
    alias = table.args.get("alias")
    if alias and alias.args.get("columns"):
        raise SQLValidationError("Column aliases on tables are not supported.")
    qualifiers = {"dataset", table.alias.casefold()} - {""}
    known = {name.casefold() for name in columns}
    if len(known) != len(columns):
        raise SQLValidationError("SQL column names must be distinct ignoring case.")
    output_aliases = {node.alias.casefold() for node in tree.expressions if type(node) is exp.Alias}
    for column in tree.find_all(exp.Column):
        if (column.args.get("db") or column.args.get("catalog")
                or (column.table and column.table.casefold() not in qualifiers)):
            raise SQLValidationError("SQL column qualifier does not match the selected dataset.")
        allowed_names = known | output_aliases if column.find_ancestor(exp.Order, exp.Group, exp.Having) else known
        if not column.is_star and column.name.casefold() not in allowed_names:
            raise SQLValidationError("SQL references an unknown column. Inspect the schema and correct it.")
    for node in nodes:
        if type(node) is exp.Star and any(node.args.values()):
            raise SQLValidationError("Star modifiers are not supported.")
        if type(node) is exp.Distinct and node.args.get("on"):
            raise SQLValidationError("DISTINCT ON is not supported.")
        if type(node) is exp.In and any(type(item) is not exp.Literal for item in node.expressions):
            raise SQLValidationError("IN accepts literal values only.")
    limit = tree.args.get("limit")
    requested = max_rows
    if limit is not None:
        value = limit.expression
        if (type(value) is not exp.Literal or value.is_string or not str(value.this).isdigit()
                or int(value.this) < 1 or any(v for k, v in limit.args.items() if k != "expression")):
            raise SQLValidationError("LIMIT must be a positive integer literal.")
        requested = min(int(value.this), max_rows)
    # The only application-supplied SQL value is inserted as an AST integer,
    # never through interpolation of user text. No arbitrary parameters are allowed.
    tree.set("limit", exp.Limit(expression=exp.Literal.number(requested)))
    return tree.sql(dialect="duckdb", comments=False)



def _json_value(value: Any) -> Any:
    """Keep native integer precision; stringify exact decimals rather than round."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return str(value) if value.is_finite() else None
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    raise SQLExecutionError("SQL result contains an unsupported value type.")


def execute_safe_sql(
    frame: pd.DataFrame, query: str, *, limits: SQLLimits | None = None,
) -> dict[str, Any]:
    """Validate then run against only this frame, with external access disabled."""
    validate_dataframe(frame)
    limits = limits if limits is not None else SQLLimits()
    sql = validate_sql(query, list(frame.columns), max_rows=limits.max_rows)
    connection = None
    timer = None
    expired = Event()
    try:
        connection = duckdb.connect(":memory:", config={
            "enable_external_access": "false",
            "allow_unsigned_extensions": "false",
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
            "memory_limit": f"{limits.memory_mb}MB",
            "threads": "1",
            "max_temp_directory_size": "0B",
            "temp_directory": "",
            "lock_configuration": "true",
        })
        connection.register("dataset", frame)

        def interrupt() -> None:
            expired.set()
            connection.interrupt()

        timer = Timer(limits.timeout_seconds, interrupt)
        timer.daemon = True
        timer.start()
        cursor = connection.execute(sql)
        columns = [description[0] for description in cursor.description]
        # fetchdf converts DuckDB HUGEINT aggregates to float64, losing large
        # integer precision. Native values preserve the engine's actual result.
        rows = [[_json_value(value) for value in row] for row in cursor.fetchmany(limits.max_rows)]
        if expired.is_set():
            raise SQLTimeoutError("SQL query exceeded its execution time limit.")
        payload = json.dumps(rows, allow_nan=False)
        if len(payload.encode("utf-8")) > limits.max_result_bytes:
            raise SQLExecutionError("SQL result is too large. Select fewer columns or rows.")
        if expired.is_set():
            raise SQLTimeoutError("SQL query exceeded its execution time limit.")
        return {"sql": sql, "columns": columns, "rows": rows, "row_count": len(rows)}
    except SQLExecutionError:
        raise
    except duckdb.Error as exc:
        if expired.is_set() or isinstance(exc, duckdb.InterruptException):
            raise SQLTimeoutError("SQL query exceeded its execution time limit.") from exc
        raise SQLExecutionError("SQL could not execute within the supported types and resource limits.") from exc
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        if connection is not None:
            connection.close()
