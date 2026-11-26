"""
**File:** ``test_ranges.py``
**Region:** ``tests/utils/test_ranges``

Tests for the integer range/list expansion helper.
"""

import pytest
from ds_resource_plugin_py_lib.common.resource.dataset.errors import ReadError

from ds_provider_unimicro_py_lib.utils.ranges import expand_combinations, expand_int_values


def test_expand_int_values_accepts_int_list_and_range():
    assert expand_int_values(2024, field_name="financialyear") == [2024]
    assert expand_int_values([2023, 2025], field_name="financialyear") == [2023, 2025]
    assert expand_int_values("1-3", field_name="period") == [1, 2, 3]
    assert expand_int_values("7", field_name="period") == [7]


def test_expand_int_values_rejects_inverted_range():
    with pytest.raises(ReadError, match="end must be >= start"):
        expand_int_values("12-1", field_name="period")


def test_expand_int_values_rejects_empty_list():
    with pytest.raises(ReadError, match="must not be empty"):
        expand_int_values([], field_name="financialyear")


def test_expand_int_values_rejects_blank_string():
    with pytest.raises(ReadError, match="must not be empty"):
        expand_int_values("   ", field_name="period")


def test_expand_int_values_rejects_non_integer_range():
    with pytest.raises(ReadError, match="expected start-end integers"):
        expand_int_values("a-3", field_name="period")


def test_expand_int_values_rejects_non_integer_value():
    with pytest.raises(ReadError, match="expected an int, list, or start-end range"):
        expand_int_values("abc", field_name="period")


def test_expand_combinations_without_expand_is_a_single_empty_combination():
    assert expand_combinations(None) == [{}]
    assert expand_combinations({}) == [{}]


def test_expand_combinations_is_cartesian_product():
    assert expand_combinations({"financialyear": "2023-2024", "period": "11-12"}) == [
        {"financialyear": 2023, "period": 11},
        {"financialyear": 2023, "period": 12},
        {"financialyear": 2024, "period": 11},
        {"financialyear": 2024, "period": 12},
    ]


def test_expand_combinations_propagates_invalid_values():
    with pytest.raises(ReadError, match="end must be >= start"):
        expand_combinations({"period": "12-1"})
