"""
**File:** ``enums.py``
**Region:** ``ds_provider_unimicro_py_lib/enums``

Enums for Unimicro provider.
"""

from enum import StrEnum


class ResourceType(StrEnum):
    """
    Resource types for Unimicro provider.
    """

    UNIMICRO_LINKED_SERVICE = "ds.resource.linked-service.unimicro"
    UNIMICRO_DATASET = "ds.resource.dataset.unimicro"


class DataProduct(StrEnum):
    """
    Provider-defined data products that do not map one-to-one to a native biz entity.

    Any other ``data_product`` value is treated as a native biz entity and read with offset pagination.
    """

    TRIAL_BALANCE = "trialbalance"


class TrialBalanceParam(StrEnum):
    """
    ``read.params`` keys that scope a ``trialbalance`` read.
    """

    FINANCIAL_YEAR = "financialyear"
    PERIOD = "period"
