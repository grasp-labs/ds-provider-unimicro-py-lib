"""
**File:** ``__init__.py``
**Region:** ``ds_provider_unimicro_py_lib/linked_service``

Unimicro Linked Service

This module defines the Unimicro linked service for the Unimicro provider.

Example:
    >>> from uuid import UUID
    >>> linked_service = UnimicroLinkedService(
    ...     id=UUID("12345678-1234-5678-1234-1234567890ab"),
    ...     name="unimicro-linked-service",
    ...     version="v1.0.0",
    ...     settings=UnimicroLinkedServiceSettings(
    ...         company_key="my-company-id",
    ...         client_id="my-client-id",
    ...         certificate="my-certificate",
    ...         p12_password="my-p12-password",
    ...     ),
    ... )
    >>> linked_service.connect()
    >>> linked_service.test_connection()
"""

from .unimicro import (
    UnimicroLinkedService,
    UnimicroLinkedServiceSettings,
)

__all__ = ["UnimicroLinkedService", "UnimicroLinkedServiceSettings"]
