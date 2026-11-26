"""
**File:** ``trial_balance.py``
**Region:** ``ds_provider_unimicro_py_lib/dataset/products/trial_balance``

TrialBalance product helpers.

Unimicro's ``GET /api/biz/accounts?action=trialbalance&financialyear={year}&period={n}`` returns the whole
balance for one fiscal year and period in a single response and ignores ``top``/``skip``, so it cannot go
through the paginated reader. History is built by repeating that call for every ``financialyear`` x ``period``
combination taken from ``read.params``; both values are stamped on every row because the response has no
such columns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import pandas as pd
from ds_common_logger_py_lib import Logger
from ds_resource_plugin_py_lib.common.resource.dataset.errors import ReadError

from ...enums import DataProduct, TrialBalanceParam
from ...utils.dataframe import project_fields
from ...utils.incremental import build_checkpoint
from ...utils.params import RESERVED_PARAMS
from ...utils.ranges import expand_combinations

if TYPE_CHECKING:
    from ..unimicro import UnimicroDataset, UnimicroDatasetSettings

logger = Logger.get_logger(__name__, package=True)

ENTITY = "accounts"
ACTION = "trialbalance"
DEFAULT_PERIODS = "1-12"


def handles(data_product: str) -> bool:
    """True when ``data_product`` selects the trial balance product."""
    return data_product.lower() == DataProduct.TRIAL_BALANCE


def reject_if_misused(settings: UnimicroDatasetSettings) -> None:
    """Raise if the trial balance action is requested through the paginated entity reader."""
    action = (settings.read.params or {}).get("action")
    if isinstance(action, str) and action.lower() == ACTION:
        raise ReadError(
            message=(
                f"read.params action={ACTION} is not paginated; "
                f"use data_product={DataProduct.TRIAL_BALANCE.value!r} with financialyear/period in read.params instead."
            ),
            details={"data_product": settings.data_product, "params": settings.read.params},
        )


def _validate(settings: UnimicroDatasetSettings) -> None:
    """Reject settings the trial balance endpoint cannot honour, instead of silently ignoring them."""
    read = settings.read
    unsupported = {name: value for name, value in (("read.id", read.id), ("read.filters", read.filters)) if value is not None}
    params = read.params or {}
    for key in sorted((RESERVED_PARAMS | {"action"}) & set(params)):
        unsupported[f"read.params.{key}"] = params[key]
    if unsupported:
        raise ReadError(
            message=f"{', '.join(unsupported)} not supported for {DataProduct.TRIAL_BALANCE}.",
            details={"data_product": settings.data_product, **unsupported},
        )
    if TrialBalanceParam.FINANCIAL_YEAR not in (read.params or {}):
        raise ReadError(
            message=f"read.params.{TrialBalanceParam.FINANCIAL_YEAR} is required for {DataProduct.TRIAL_BALANCE}.",
            details={"data_product": settings.data_product, "params": read.params},
        )


def fetch(dataset: UnimicroDataset[Any, Any], session: Any) -> None:
    """
    Fetch the trial balance once per ``financialyear`` x ``period``; stamp each row with both values.

    ``financialyear`` (required) and ``period`` (default ``1-12``) accept an int or a ``start-end`` range.
    Any other ``read.params`` are passed through unchanged. ``read.fields`` projects the output.

    The read is always a full load: the checkpoint is never used as a starting point, is reset on success,
    and is left untouched on failure.
    """
    settings = dataset.settings
    _validate(settings)

    extra_params = dict(settings.read.params or {})
    year_key, period_key = TrialBalanceParam.FINANCIAL_YEAR.value, TrialBalanceParam.PERIOD.value
    combinations = expand_combinations(
        {
            year_key: extra_params.pop(year_key),
            period_key: extra_params.pop(period_key, DEFAULT_PERIODS),
        }
    )
    url = f"{dataset.linked_service.settings.host.rstrip('/')}/api/biz/{ENTITY}"
    logger.info("TrialBalance read: %d request(s).", len(combinations))

    all_records: list[dict[str, Any]] = []
    current: dict[str, int] = combinations[0]
    try:
        for combination in combinations:
            current = combination
            query = {**extra_params, "action": ACTION, **combination}
            logger.debug("Making API request to %s with params: %s", url, query)
            response = session.get(f"{url}?{urlencode(query)}", headers={"CompanyKey": settings.company_key})
            data = response.json()
            if not isinstance(data, list):
                raise ReadError(
                    message="Unexpected Unimicro trial balance response shape (expected list).",
                    details={"payload_type": type(data).__name__, **combination},
                )
            all_records.extend({**record, **combination} for record in data)
            logger.info("Fetched %d trial balance rows for %s.", len(data), combination)
    except ReadError:
        raise
    except Exception as exc:
        logger.error("Error occurred while fetching the trial balance: %s", exc)
        raise ReadError(
            message=f"Error occurred while fetching the trial balance: {exc}",
            details={
                "successfully_fetched_records": len(all_records),
                "data_product": settings.data_product,
                **current,
            },
        ) from exc

    dataset.output = project_fields(pd.json_normalize(all_records, sep="_"), settings.read.fields)
    dataset.checkpoint = build_checkpoint(last_loaded_records=0, last_modified_date=None)
