"""
**File:** ``incremental.py``
**Region:** ``ds_provider_unimicro_py_lib/utils/incremental``

Helpers for incremental loading: watermark detection, incremental filters and checkpoints.
"""

from typing import Any

import pandas as pd
from ds_common_logger_py_lib import Logger

logger = Logger.get_logger(__name__, package=True)

TIMESTAMP_COLUMNS = ("CreatedAt", "UpdatedAt")


def greatest_incremental_value(records: pd.DataFrame) -> str | None:
    """
    Determine the greatest incremental value (last modified date) from the fetched records.

    Args:
        records (pd.DataFrame): The dataframe of all fetched records.

    Returns:
        str | None: The greatest ISO-8601 timestamp found in ``CreatedAt``/``UpdatedAt``,
        or None if there are no valid timestamps.
    """
    timestamp_columns = [column for column in TIMESTAMP_COLUMNS if column in records]

    if not timestamp_columns:
        return None

    timestamps = pd.concat(
        [pd.to_datetime(records[column], utc=True, errors="coerce") for column in timestamp_columns],
        ignore_index=True,
    ).dropna()

    if timestamps.empty:
        return None

    return timestamps.max().isoformat()


def build_incremental_filter(last_modified_date: str) -> str:
    """
    Build the provider-specific incremental filter.

    Args:
        last_modified_date: Watermark; only records created or updated after it are selected.

    Returns:
        str: Filter clause matching records with ``CreatedAt`` or ``UpdatedAt`` after the watermark.
    """
    return f"(CreatedAt gt '{last_modified_date}' or UpdatedAt gt '{last_modified_date}')"


def build_checkpoint(last_loaded_records: int | None, last_modified_date: str | None) -> dict[str, Any]:
    """
    Build a checkpoint dictionary to track the last successfully read page.

    Args:
        last_loaded_records (int | None): The number of records that were successfully read (records to skip).
        last_modified_date (str | None): The last modified date to include in the checkpoint.

    Returns:
        dict[str, Any]: A checkpoint dictionary containing the incremental and pagination values.
    """
    checkpoint = {
        "incremental": {"value": last_modified_date},  # or None
        "pagination": {"value": last_loaded_records},  # amount of records read so far (records to skip)
    }
    logger.debug("Built checkpoint: %s", checkpoint)
    return checkpoint
