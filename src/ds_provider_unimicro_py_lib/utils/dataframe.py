"""
**File:** ``dataframe.py``
**Region:** ``ds_provider_unimicro_py_lib/utils/dataframe``

Helpers for shaping dataset output frames.
"""

import pandas as pd


def project_fields(output: pd.DataFrame, fields: list[str] | None) -> pd.DataFrame:
    """
    Restrict the output to ``fields`` (ignoring names that are not present), if configured.

    Args:
        output: The normalized output dataframe.
        fields: Column names to keep, in the requested order. ``None`` or empty keeps everything.

    Returns:
        pd.DataFrame: The projected dataframe, or the input unchanged when ``fields`` is not set.
        If none of the requested fields exist, an empty frame with the same index is returned.
    """
    if not fields:
        return output
    keep = [col for col in fields if col in output.columns]
    return output.loc[:, keep] if keep else output.iloc[:, 0:0]
