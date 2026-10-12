"""Run from the repository root: python -m examples.inspect_retail."""

import json
from pathlib import Path

from backend.data.csv_processing import inspect_dataset, load_csv
from backend.data.duckdb_store import DuckDBDataset


def main() -> None:
    sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "retail_sales.csv"
    frame = load_csv(sample)
    print(json.dumps(inspect_dataset(frame), indent=2, allow_nan=False))
    with DuckDBDataset(frame) as dataset:
        print("\nRevenue by category:")
        print(dataset.aggregate("revenue", group_by="category").to_string(index=False))
        print("\nSales with quantity >= 5:")
        print(dataset.filter_rows("quantity", 5, operator=">=").to_string(index=False))


if __name__ == "__main__":
    main()
