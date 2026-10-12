import pandas as pd
import pytest

from backend.data.csv_processing import DatasetError
from backend.data.duckdb_store import AnalyticsError, DuckDBDataset


def test_retail_aggregation(retail_frame):
    with DuckDBDataset(retail_frame) as dataset:
        assert dataset.aggregate("revenue")["value"].iloc[0] == 530
        grouped = dataset.aggregate("revenue", group_by="category")
        assert dict(zip(grouped["category"], grouped["value"])) == {
            "Electronics": 260, "Home": 150, "Stationery": 120,
        }


@pytest.mark.parametrize(
    ("operation", "expected"), [("sum", 60), ("avg", 20), ("min", 10), ("max", 30), ("count", 3)]
)
def test_aggregation_operations(operation, expected):
    with DuckDBDataset(pd.DataFrame({"amount": [10, 20, 30, None]})) as dataset:
        assert dataset.aggregate("amount", operation)["value"].iloc[0] == expected


def test_filtering_and_limit(retail_frame):
    with DuckDBDataset(retail_frame) as dataset:
        result = dataset.filter_rows("quantity", 5, operator=">=")
        assert sorted(result["quantity"]) == [5, 6, 10]
        assert len(dataset.filter_rows("category", "Electronics", limit=2)) == 2
        assert dataset.filter_rows("category", "does not exist").empty


@pytest.mark.parametrize(("operator", "expected"), [("=", 1), ("!=", 2), (">", 1), (">=", 2), ("<", 1), ("<=", 2)])
def test_comparison_operators(operator, expected):
    with DuckDBDataset(pd.DataFrame({"n": [1, 2, 3]})) as dataset:
        assert len(dataset.filter_rows("n", 2, operator=operator)) == expected


def test_null_filtering():
    with DuckDBDataset(pd.DataFrame({"n": [1, None]})) as dataset:
        assert len(dataset.filter_rows("n", None)) == 1
        assert len(dataset.filter_rows("n", None, operator="!=")) == 1
        with pytest.raises(AnalyticsError, match="Missing values"):
            dataset.filter_rows("n", None, operator=">")


def test_isolation_and_snapshot():
    frame = pd.DataFrame({"n": [1, 2]})
    with DuckDBDataset(frame) as first, DuckDBDataset(pd.DataFrame({"n": [100]})) as second:
        frame.loc[0, "n"] = 500
        assert first.aggregate("n")["value"].iloc[0] == 3
        assert second.aggregate("n")["value"].iloc[0] == 100


def test_closes_on_exception(retail_frame):
    dataset = DuckDBDataset(retail_frame)
    with pytest.raises(RuntimeError):
        with dataset:
            raise RuntimeError("test")
    dataset.close()
    with pytest.raises(AnalyticsError, match="closed"):
        dataset.aggregate("revenue")


def test_rejects_empty_dataframe():
    with pytest.raises(DatasetError):
        DuckDBDataset(pd.DataFrame())


def test_rejects_invalid_operations(retail_frame):
    with DuckDBDataset(retail_frame) as dataset:
        with pytest.raises(AnalyticsError, match="Unsupported aggregation"):
            dataset.aggregate("revenue", "sum); DROP TABLE dataset; --")
        with pytest.raises(AnalyticsError, match="Unknown column"):
            dataset.aggregate("missing")
        with pytest.raises(AnalyticsError, match="Unknown column"):
            dataset.aggregate("revenue", group_by="missing")
        with pytest.raises(AnalyticsError, match="numeric"):
            dataset.aggregate("category")
        with pytest.raises(AnalyticsError, match="Unsupported comparison"):
            dataset.filter_rows("quantity", 1, operator="OR 1=1")
        for limit in [0, 1001, True, 1.5]:
            with pytest.raises(AnalyticsError, match="Limit"):
                dataset.filter_rows("quantity", 1, limit=limit)


def test_quotes_identifiers_and_binds_values():
    column = 'odd"column; --'
    malicious_value = "x' OR 1=1; --"
    frame = pd.DataFrame({column: [malicious_value, "normal"], "amount": [1, 2]})
    with DuckDBDataset(frame) as dataset:
        result = dataset.filter_rows(column, malicious_value)
        assert len(result) == 1
        assert result["amount"].iloc[0] == 1
        assert dataset.aggregate("amount", group_by=column)["value"].sum() == 3


def test_database_errors_are_clear():
    with DuckDBDataset(pd.DataFrame({"amount": [1, 2]})) as dataset:
        with pytest.raises(AnalyticsError, match="Analysis failed"):
            dataset.filter_rows("amount", "not a number")
