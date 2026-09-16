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
