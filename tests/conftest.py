from pathlib import Path

import pytest

from backend.data.csv_processing import load_csv


@pytest.fixture
def retail_frame():
    sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "retail_sales.csv"
    return load_csv(sample)
