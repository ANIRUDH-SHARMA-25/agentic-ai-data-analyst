import json
from threading import Event

import duckdb
import pandas as pd
import pytest

from backend.data.safe_sql import (
    SQLExecutionError, SQLLimits, SQLTimeoutError, SQLValidationError,
    execute_safe_sql, validate_sql,
)


def test_verified_retail_totals(retail_frame):
    result = execute_safe_sql(retail_frame, "SELECT category, SUM(revenue) AS total FROM dataset GROUP BY category ORDER BY total DESC")
    assert result["columns"] == ["category", "total"]
    assert result["rows"] == [["Electronics", 260], ["Home", 150], ["Stationery", 120]]
    assert sum(row[1] for row in result["rows"]) == retail_frame["revenue"].sum() == 530


@pytest.mark.parametrize(("query", "expected"), [
    ("SELECT COUNT(*) FROM dataset", 12),
    ("SELECT SUM(quantity) FROM dataset WHERE category = 'Stationery'", 25),
    ("SELECT MAX(revenue) FROM dataset", 90),
    ("SELECT MIN(revenue) FROM dataset", 20),
    ("SELECT ROUND(AVG(revenue), 2) FROM dataset", 44.17),
    ("SELECT COUNT(DISTINCT category) FROM dataset", 3),
    ("SELECT SUM(quantity * unit_price) FROM dataset", 530),
    ("SELECT COUNT(*) FROM dataset WHERE quantity BETWEEN 2 AND 4", 7),
    ("SELECT COUNT(*) FROM dataset WHERE category IN ('Home', 'Stationery')", 8),
    ("SELECT COUNT(*) FROM dataset WHERE product LIKE '%Mouse%'", 2),
    ("SELECT COUNT(*) FROM dataset WHERE NOT quantity < 5", 3),
    ("SELECT COUNT(*) FROM dataset WHERE category ILIKE 'home'", 4),
    ("SELECT LENGTH(UPPER(LOWER(category))) FROM dataset LIMIT 1", 11),
    ("SELECT ABS(-quantity) FROM dataset LIMIT 1", 2),
])
def test_safe_sql_operations(retail_frame, query, expected):
    assert execute_safe_sql(retail_frame, query)["rows"][0][0] == expected


def test_having_aliases_and_qualified_columns(retail_frame):
    result = execute_safe_sql(retail_frame, "SELECT d.category, SUM(d.revenue) AS total FROM dataset AS d GROUP BY d.category HAVING total > 200 ORDER BY total DESC")
    assert result["rows"] == [["Electronics", 260]]


def test_nulls_json_and_quoted_identifiers():
    frame = pd.DataFrame({'odd"column': [1.0, float('inf'), None], "text": [None, "a", "b"]})
    result = execute_safe_sql(frame, 'SELECT "odd""column", COALESCE(text, \'unknown\') FROM dataset')
    assert result["rows"] == [[1.0, "unknown"], [None, "a"], [None, "b"]]
    json.dumps(result, allow_nan=False)
    assert execute_safe_sql(frame, 'SELECT COUNT(*) FROM dataset WHERE "odd""column" IS NULL')["rows"] == [[1]]


@pytest.mark.parametrize("query", [
    "", "SELECT FROM", "SELECT ( FROM dataset", "SELECT * FROM dataset; SELECT * FROM dataset",
    "DELETE FROM dataset", "DROP TABLE dataset", "UPDATE dataset SET revenue=0",
    "INSERT INTO dataset VALUES (1)", "CREATE TABLE other (n INT)", "COPY dataset TO 'secret.csv'",
    "ATTACH 'other.db'", "PRAGMA database_list", "SET enable_external_access=true",
    "INSTALL httpfs", "LOAD httpfs", "CALL checkpoint()", "EXPORT DATABASE 'x'",
    "SELECT * FROM other", "SELECT * FROM main.dataset", "SELECT * FROM db.main.dataset",
    "SELECT * FROM read_csv_auto('secret.csv')", "SELECT * FROM read_parquet('secret.parquet')",
    "SELECT * FROM range(1000000000)", "SELECT read_text('secret.txt') FROM dataset",
    "SELECT getenv('OPENAI_API_KEY') FROM dataset", "SELECT current_setting('home_directory') FROM dataset",
    "SELECT * FROM dataset UNION SELECT * FROM dataset",
    "SELECT * FROM dataset JOIN dataset d ON true", "SELECT * FROM dataset, dataset d",
    "WITH d AS (SELECT * FROM dataset) SELECT * FROM d",
    "SELECT (SELECT SUM(revenue) FROM dataset) FROM dataset",
    "SELECT * FROM (SELECT * FROM dataset) d",
    "SELECT * FROM dataset WHERE revenue IN (SELECT revenue FROM dataset)",
    "SELECT ROW_NUMBER() OVER () FROM dataset", "SELECT missing FROM dataset",
    "SELECT o.revenue FROM dataset", "SELECT * EXCLUDE revenue FROM dataset",
    "SELECT * REPLACE (0 AS revenue) FROM dataset", "SELECT category FROM dataset OFFSET 1",
    "SELECT CAST(date AS DATE) FROM dataset", "SELECT RANDOM() FROM dataset",
    "SELECT REPEAT(category, 100000000) FROM dataset", "SELECT * FROM dataset LIMIT -1",
    "SELECT * FROM dataset LIMIT 0", "SELECT * FROM dataset LIMIT 1.5",
    "SELECT * FROM dataset LIMIT ?", "SELECT * FROM dataset LIMIT ALL",
    "SELECT * FROM dataset TABLESAMPLE 10", "SELECT * FROM dataset AS d(x,y,z)",
    "SELECT * FROM 'D:/secret.csv'", "SELECT $$secret$$ FROM read_csv('x')",
    "SELECT * FROM dataset WHERE quantity IN (quantity, 2)",
    "SELECT missing AS missing FROM dataset", "SELECT 1 AS x FROM dataset ORDER BY unknown",
])
def test_rejects_unsupported_sql_before_connect(retail_frame, query, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected SQL must never reach DuckDB.")
    monkeypatch.setattr(duckdb, "connect", forbidden)
    with pytest.raises(SQLValidationError):
        execute_safe_sql(retail_frame, query)


def test_comment_and_case_handling(retail_frame):
    result = execute_safe_sql(retail_frame, "/* DROP TABLE dataset */ SeLeCt SuM(revenue) FROM DATASET; -- harmless")
    assert result["rows"] == [[530]]
    assert "DROP" not in result["sql"]


def test_result_row_limits(retail_frame):
    for query in ["SELECT * FROM dataset", "SELECT * FROM dataset LIMIT 999999"]:
        result = execute_safe_sql(retail_frame, query, limits=SQLLimits(max_rows=3))
        assert result["row_count"] == len(result["rows"]) == 3
        assert result["sql"].endswith("LIMIT 3")
    assert execute_safe_sql(retail_frame, "SELECT * FROM dataset LIMIT 1")["row_count"] == 1


def test_result_byte_limit(retail_frame):
    with pytest.raises(SQLExecutionError, match="too large"):
        execute_safe_sql(retail_frame, "SELECT * FROM dataset", limits=SQLLimits(max_result_bytes=10))


def test_sql_text_and_complexity_limits():
    with pytest.raises(SQLValidationError, match="8000"):
        validate_sql("SELECT " + "1" * 8000, ["n"])
    with pytest.raises(SQLValidationError, match="complex"):
        validate_sql("SELECT " + "+".join(["1"] * 130) + " FROM dataset", ["n"])


def test_actual_interrupt_timer_and_sanitized_errors(retail_frame, monkeypatch):
    interrupted = Event()
    closed = []
    configuration = {}

    class SlowConnection:
        def register(self, *args):
            pass
        def execute(self, sql):
            assert interrupted.wait(2), "Interrupt timer did not run"
            raise duckdb.InterruptException("private path and trace")
        def interrupt(self):
            interrupted.set()
        def close(self):
            closed.append(True)

    def connect(*args, **kwargs):
        configuration.update(kwargs["config"])
        return SlowConnection()

    monkeypatch.setattr(duckdb, "connect", connect)
    with pytest.raises(SQLTimeoutError, match="time limit"):
        execute_safe_sql(retail_frame, "SELECT * FROM dataset", limits=SQLLimits(timeout_seconds=0.01))
    assert closed == [True]
    assert configuration["enable_external_access"] == "false"
    assert configuration["autoinstall_known_extensions"] == "false"
    assert configuration["autoload_known_extensions"] == "false"
    assert configuration["allow_unsigned_extensions"] == "false"
    assert configuration["threads"] == "1"
    assert configuration["max_temp_directory_size"] == "0B"
    assert configuration["temp_directory"] == ""
    assert configuration["lock_configuration"] == "true"


def test_binder_error_sanitized(retail_frame):
    with pytest.raises(SQLExecutionError) as caught:
        execute_safe_sql(retail_frame, "SELECT SUM(category) FROM dataset")
    assert "Binder" not in str(caught.value)


@pytest.mark.parametrize("kwargs", [{"max_rows": 0}, {"max_rows": 1001}, {"memory_mb": 513}, {"timeout_seconds": 0}, {"max_result_bytes": True}])
def test_invalid_sql_limits(kwargs):
    with pytest.raises(ValueError):
        SQLLimits(**kwargs)


def test_native_big_integer_aggregation_is_exact():
    value = 9007199254740993
    frame = pd.DataFrame({"n": [value, value]})
    result = execute_safe_sql(frame, "SELECT SUM(n) AS total FROM dataset")
    assert result["rows"] == [[18014398509481986]]
    assert isinstance(result["rows"][0][0], int)


def test_exact_decimal_serialization():
    from decimal import Decimal
    frame = pd.DataFrame({"n": [Decimal("123456789.123456789"), Decimal("0.000000001")]})
    result = execute_safe_sql(frame, "SELECT SUM(n) AS total FROM dataset")
    assert Decimal(result["rows"][0][0]) == Decimal("123456789.123456790")
    assert isinstance(result["rows"][0][0], str)


def test_ambiguous_case_columns_rejected():
    with pytest.raises(SQLValidationError, match="distinct ignoring case"):
        execute_safe_sql(pd.DataFrame({"n": [1], "N": [99]}), "SELECT n FROM dataset")


def test_external_file_access_disabled_in_actual_connection(retail_frame, tmp_path, monkeypatch):
    from backend.data import safe_sql
    original_connect = duckdb.connect
    path = tmp_path / "external.csv"
    path.write_text("n\n1\n", encoding="utf-8")
    denied = []

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        with pytest.raises(duckdb.Error):
            connection.execute("SELECT * FROM read_csv(?)", [str(path)]).fetchall()
        denied.append(True)
        return connection

    monkeypatch.setattr(safe_sql.duckdb, "connect", connect)
    assert execute_safe_sql(retail_frame, "SELECT COUNT(*) FROM dataset")["rows"] == [[12]]
    assert denied == [True]


def test_filter_result_against_independent_pandas(retail_frame):
    result = execute_safe_sql(retail_frame, "SELECT COUNT(*) FROM dataset WHERE quantity BETWEEN 2 AND 4")
    assert result["rows"][0][0] == int(retail_frame["quantity"].between(2, 4).sum())
