"""
**File:** ``ranges.py``
**Region:** ``ds_provider_unimicro_py_lib/utils/ranges``

Helpers for expanding integer query-parameter specifications into concrete lists.
"""

import itertools

from ds_resource_plugin_py_lib.common.resource.dataset.errors import ReadError


def expand_int_values(value: int | str | list[int], *, field_name: str) -> list[int]:
    """Normalize an int, ``start-end`` range string, or list of ints into a list of ints."""
    if isinstance(value, list):
        if not value:
            raise ReadError(
                message=f"{field_name} must not be empty.",
                details={"field": field_name, "value": value},
            )
        return [int(item) for item in value]

    if isinstance(value, int):
        return [value]

    text = str(value).strip()
    if not text:
        raise ReadError(
            message=f"{field_name} must not be empty.",
            details={"field": field_name, "value": value},
        )

    if "-" in text:
        start_text, end_text = text.split("-", 1)
        try:
            start, end = int(start_text), int(end_text)
        except ValueError as exc:
            raise ReadError(
                message=f"Invalid {field_name} range {value!r}; expected start-end integers.",
                details={"field": field_name, "value": value},
            ) from exc
        if end < start:
            raise ReadError(
                message=f"Invalid {field_name} range {value!r}; end must be >= start.",
                details={"field": field_name, "value": value},
            )
        return list(range(start, end + 1))

    try:
        return [int(text)]
    except ValueError as exc:
        raise ReadError(
            message=f"Invalid {field_name} value {value!r}; expected an int, list, or start-end range.",
            details={"field": field_name, "value": value},
        ) from exc


def expand_combinations(expand: dict[str, list[int] | int | str] | None) -> list[dict[str, int]]:
    """
    Build the cartesian product of the ``expand`` values.

    Args:
        expand: Mapping of parameter name to an int, list of ints, or ``start-end`` range string.

    Returns:
        list[dict[str, int]]: One parameter mapping per request. ``[{}]`` when ``expand`` is empty or ``None``,
        so callers always make at least one request.
    """
    spec = expand or {}
    keys = list(spec)
    value_lists = [expand_int_values(spec[key], field_name=key) for key in keys]
    return [dict(zip(keys, values, strict=True)) for values in itertools.product(*value_lists)]
