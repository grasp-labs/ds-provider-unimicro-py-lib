"""
**File:** ``params.py``
**Region:** ``ds_provider_unimicro_py_lib/utils/params``

Query-parameter names owned by the provider.
"""

# Query keys the dataset sets itself on paginated reads; ``read.params`` may not override them.
RESERVED_PARAMS = frozenset({"top", "skip", "select", "filter"})
