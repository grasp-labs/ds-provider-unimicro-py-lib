"""
**File:** ``test_incremental.py``
**Region:** ``tests/utils/test_incremental``

Tests for the incremental loading helpers.
"""

import pandas as pd

from ds_provider_unimicro_py_lib.utils.incremental import (
    build_checkpoint,
    build_incremental_filter,
    greatest_incremental_value,
)


def test_greatest_incremental_value_returns_latest_timestamp_across_columns():
    records = pd.DataFrame(
        {
            "CreatedAt": ["2024-01-01T00:00:00Z", "2024-05-01T00:00:00Z"],
            "UpdatedAt": ["2024-03-01T00:00:00Z", None],
        }
    )

    assert greatest_incremental_value(records) == "2024-05-01T00:00:00+00:00"


def test_greatest_incremental_value_returns_none_without_timestamp_columns():
    assert greatest_incremental_value(pd.DataFrame({"Name": ["Ada"]})) is None


def test_greatest_incremental_value_returns_none_without_valid_timestamps():
    assert greatest_incremental_value(pd.DataFrame({"CreatedAt": ["not-a-date"]})) is None


def test_build_incremental_filter_matches_created_or_updated_after_watermark():
    assert build_incremental_filter("2024-01-01T00:00:00+00:00") == (
        "(CreatedAt gt '2024-01-01T00:00:00+00:00' or UpdatedAt gt '2024-01-01T00:00:00+00:00')"
    )


def test_build_checkpoint_has_incremental_and_pagination_values():
    assert build_checkpoint(5, "2024-01-01T00:00:00+00:00") == {
        "incremental": {"value": "2024-01-01T00:00:00+00:00"},
        "pagination": {"value": 5},
    }
    assert build_checkpoint(0, None) == {
        "incremental": {"value": None},
        "pagination": {"value": 0},
    }
