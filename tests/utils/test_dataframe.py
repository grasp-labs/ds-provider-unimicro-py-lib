"""
**File:** ``test_dataframe.py``
**Region:** ``tests/utils/test_dataframe``

Tests for the output frame helpers.
"""

import pandas as pd

from ds_provider_unimicro_py_lib.utils.dataframe import project_fields


def make_frame() -> pd.DataFrame:
    return pd.DataFrame({"Name": ["Ada", "Lin"], "Balance": [1.0, 2.0], "Extra": [None, None]})


def test_project_fields_returns_input_unchanged_without_fields():
    frame = make_frame()

    assert project_fields(frame, None) is frame
    assert project_fields(frame, []) is frame


def test_project_fields_keeps_requested_columns_in_requested_order():
    projected = project_fields(make_frame(), ["Balance", "Name"])

    assert list(projected.columns) == ["Balance", "Name"]


def test_project_fields_ignores_missing_columns():
    projected = project_fields(make_frame(), ["Name", "Missing"])

    assert list(projected.columns) == ["Name"]


def test_project_fields_returns_empty_columns_when_nothing_matches():
    projected = project_fields(make_frame(), ["Missing"])

    assert list(projected.columns) == []
    assert len(projected) == 2
