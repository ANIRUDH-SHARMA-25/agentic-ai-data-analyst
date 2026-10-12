import json

import numpy as np
import pandas as pd
import pytest

from backend.data.csv_processing import (
    DatasetError,
    dataset_preview,
    inspect_dataset,
    load_csv,
    validate_dataframe,
)


def write_csv(tmp_path, content, name="input.csv"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def test_load_sample(retail_frame):
    assert retail_frame.shape == (12, 6)
    assert retail_frame["quantity"].sum() == 41
    assert retail_frame["revenue"].sum() == 530


@pytest.mark.parametrize("content", ["", " \n\t", "date,revenue\n", "\n\n"])
def test_empty_csv(tmp_path, content):
    with pytest.raises(DatasetError, match="empty|no data|non-empty"):
        load_csv(write_csv(tmp_path, content))


@pytest.mark.parametrize(
    "content",
    [
        "a,b\n1,2,3\n",
        "a,b\n1\n",
        'a,b\n1,"unterminated\n',
        'a,b\n1,"x"bad\n',
        "a,b\n1,2\n3,4,5\n",
        "a,b\n1,2\n3\n",
    ],
)
def test_malformed_records(tmp_path, content):
    with pytest.raises(DatasetError, match="Malformed CSV"):
        load_csv(write_csv(tmp_path, content))


@pytest.mark.parametrize("header", ["a,a", "a,", " ,b"])
def test_invalid_headers(tmp_path, header):
    with pytest.raises(DatasetError, match="column names"):
        load_csv(write_csv(tmp_path, header + "\n1,2\n"))


def test_format_and_size_limits(tmp_path):
    with pytest.raises(DatasetError, match="Only .csv"):
        load_csv(write_csv(tmp_path, "a\n1\n", "input.txt"))
    path = write_csv(tmp_path, "a\n1\n")
    assert len(load_csv(path, max_bytes=path.stat().st_size)) == 1
    with pytest.raises(DatasetError, match="size limit"):
        load_csv(path, max_bytes=path.stat().st_size - 1)


@pytest.mark.parametrize("max_bytes", [0, -1, True, 1.5])
def test_invalid_size_configuration(tmp_path, max_bytes):
    with pytest.raises(DatasetError, match="positive integer"):
        load_csv(write_csv(tmp_path, "a\n1\n"), max_bytes=max_bytes)


def test_unreadable_file(tmp_path):
    with pytest.raises(DatasetError, match="Could not read"):
        load_csv(tmp_path / "missing.csv")
    directory = tmp_path / "directory.csv"
    directory.mkdir()
    with pytest.raises(DatasetError, match="Could not read"):
        load_csv(directory)


def test_invalid_encoding_and_null_bytes(tmp_path):
    path = tmp_path / "input.csv"
    path.write_bytes(b"a\n\xff\n")
    with pytest.raises(DatasetError, match="UTF-8"):
        load_csv(path)
    path.write_bytes(b"a\nx\x00y\n")
    with pytest.raises(DatasetError, match="null bytes"):
        load_csv(path)


def test_quoted_fields_bom_and_blank_lines(tmp_path):
    frame = load_csv(write_csv(tmp_path, '\ufeffname,value\n\n"a,b",2\n"line\nbreak",3\n', "INPUT.CSV"))
    assert list(frame.columns) == ["name", "value"]
    assert frame["name"].tolist() == ["a,b", "line\nbreak"]


def test_missing_values_and_statistics(tmp_path):
    frame = load_csv(write_csv(tmp_path, "name,revenue,quantity\na,10,1\nb,,2\n,30,\n"))
    summary = inspect_dataset(frame, preview_rows=2)
    assert summary["row_count"] == 3
    assert summary["column_count"] == 3
    assert summary["missing_values"] == {"name": 1, "revenue": 1, "quantity": 1}
    assert summary["dtypes"]["revenue"] == "float64"
    assert summary["statistics"]["revenue"]["mean"] == 20
    assert summary["statistics"]["revenue"]["count"] == 2
    assert summary["statistics"]["name"]["unique"] == 2
    assert len(summary["preview"]) == 2
    assert summary["preview"][1]["revenue"] is None
    json.dumps(summary, allow_nan=False)


def test_all_missing_and_nonfinite_values():
    frame = pd.DataFrame({"empty": [np.nan, np.nan], "value": [np.inf, 1.0]})
    summary = inspect_dataset(frame)
    assert summary["missing_values"]["empty"] == 2
    assert summary["statistics"]["value"]["mean"] == 1.0
    assert summary["statistics"]["value"]["count"] == 1
    assert summary["preview"][0] == {"empty": None, "value": None}
    json.dumps(summary, allow_nan=False)


def test_single_column_and_missing_record(tmp_path):
    frame = load_csv(write_csv(tmp_path, "a\n1\n2\n"))
    assert frame.shape == (2, 1)
    frame = load_csv(write_csv(tmp_path, "a,b\n,\n"))
    assert frame.shape == (1, 2)
    assert frame.isna().all().all()


@pytest.mark.parametrize("rows", [0, 21, True, 1.5])
def test_preview_limits(retail_frame, rows):
    with pytest.raises(DatasetError, match="between 1 and 20"):
        dataset_preview(retail_frame, rows=rows)


def test_preview_caps_at_available_rows(retail_frame):
    assert len(dataset_preview(retail_frame)) == 5
    assert len(dataset_preview(retail_frame, rows=20)) == 12


@pytest.mark.parametrize(
    "frame",
    [pd.DataFrame(), pd.DataFrame(columns=["a"]), pd.DataFrame([[1, 2]], columns=["a", "a"]),
     pd.DataFrame([[1]], columns=[""]), pd.DataFrame([[1]], columns=[1]), None],
)
def test_dataframe_validation(frame):
    with pytest.raises(DatasetError):
        validate_dataframe(frame)
