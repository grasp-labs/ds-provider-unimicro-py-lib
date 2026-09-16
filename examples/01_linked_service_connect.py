"""
**File:** ``01_linked_service_connect.py``
**Region:** ``examples/01_linked_service_connect``

Example 01: Connecting a Unimicro linked service.

This example demonstrates how to create and connect a Unimicro linked service
using the `UnimicroLinkedService` class.
It includes the necessary settings for authentication and
connection to the Unimicro API.

Prerequisites:
    Set environment variables for PowerOfficeGo API authentication:
    - `UNIMICRO_CLIENT_ID`: Your Unimicro client ID.
    - `UNIMICRO_COMPANY_KEY`: Your Unimicro company key.
    - `UNIMICRO_CERTIFICATE`: Your base64-encoded Unimicro certificate.
    - `UNIMICRO_P12_PASSWORD`: Your Unimicro PKCS#12 password.
"""

from __future__ import annotations

import os
import logging
from uuid import uuid4

from ds_common_logger_py_lib import Logger
from ds_provider_unimicro_py_lib.linked_service.unimicro import UnimicroLinkedService, UnimicroLinkedServiceSettings

Logger.configure(level=logging.DEBUG)
logger = Logger.get_logger(__name__)


def main() -> None:
    # Load settings from environment variables
    client_id = os.getenv("UNIMICRO_CLIENT_ID", "your-client-id")
    company_key = os.getenv("UNIMICRO_COMPANY_KEY", "your-company-key")
    certificate = os.getenv("UNIMICRO_CERTIFICATE", "your-base64-encoded-certificate")
    p12_password = os.getenv("UNIMICRO_P12_PASSWORD", "your-p12-password")

    # Create linked service settings
    settings = UnimicroLinkedServiceSettings(
        client_id=client_id,
        company_key=company_key,
        certificate=certificate,
        p12_password=p12_password,
    )

    # Create linked service instance
    linked_service = UnimicroLinkedService(
        id=uuid4(),
        name="example-unimicro-linked-service",
        version="v1.0.0",
        settings=settings,
    )

    try:
        # Connect the linked service
        logger.info("Testing connection to Unimicro linked service...")
        linked_service.connect()

    except ConnectionError as exc:
        logger.error("Failed to connect to Unimicro: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        raise


if __name__ == "__main__":
    main()
