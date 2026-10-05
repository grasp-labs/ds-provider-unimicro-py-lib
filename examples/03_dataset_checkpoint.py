"""
**File:** ``03_dataset_checkpoint.py``
**Region:** ``examples/03_dataset_checkpoint.py``

Example 03: Reading data from Unimicro with checkpoint support.

This example demonstrates:
- Creating a Unimicro and connecting.
- Creating a Dataset for a data product.
- Reading customer data from Unimicro.
- Handle pagination when reading data.
- Demonstrates using checkpoints for incremental data loads.
"""
import logging
import os
from uuid import uuid4

from ds_common_logger_py_lib import Logger
from ds_provider_unimicro_py_lib.linked_service.unimicro import UnimicroLinkedService, UnimicroLinkedServiceSettings
from ds_provider_unimicro_py_lib.dataset.unimicro import UnimicroDataset, UnimicroDatasetSettings, UnimicroReadSettings

Logger.configure(level=logging.DEBUG)
logger = Logger.get_logger(__name__)


def main() -> None:
    # Load settings from environment variables
    client_id = os.getenv("UNIMICRO_CLIENT_ID", "your-client-id")
    company_key = os.getenv("UNIMICRO_COMPANY_KEY", "your-company-key")
    certificate = os.getenv("UNIMICRO_CERTIFICATE", "your-base64-encoded-certificate")
    certificate_password = os.getenv("UNIMICRO_CERTIFICATE_PASSWORD", "your-certificate-password")

    checkpoint = {
        "incremental": {"value": "2025-01-19T22:20:00+00:00"},
        "pagination": {"value": 0},
    }

    # Create linked service settings
    settings = UnimicroLinkedServiceSettings(
        client_id=client_id,
        company_key=company_key,
        certificate=certificate,
        certificate_password=certificate_password,
    )

    # Create linked service instance
    linked_service = UnimicroLinkedService(
        id=uuid4(),
        name="example-unimicro-linked-service",
        version="v1.0.0",
        settings=settings,
    )
    # Create a Dataset for a data product customer
    dataset_settings = UnimicroDatasetSettings(
        data_product="Customers",
        company_key=company_key,
        read=UnimicroReadSettings(
            page_size=1000,
        )
    )
    dataset = UnimicroDataset(
        id=uuid4(),
        name="unimicro-customer-dataset",
        version="v1.0.0",
        linked_service=linked_service,
        settings=dataset_settings,
        checkpoint=checkpoint,
    )

    try:
        linked_service.connect()

        logger.info("Reading customer data from Unimicro.")
        dataset.read()

        # Access the results
        if dataset.output is not None and not dataset.output.empty:
            logger.info("✓ Read %d customers", len(dataset.output))
            logger.debug("Columns: %s", list(dataset.output.columns))
            logger.debug("First few rows:\n%s", dataset.output.head())
        else:
            logger.info("No customer data returned")

        # The checkpoint can be persisted for incremental loads
        if dataset.supports_checkpoint and dataset.checkpoint:
            logger.debug("Checkpoint for next run: %s", dataset.checkpoint)

    except Exception as exc:
        logger.error("Failed to read data: %s", exc)
        raise

    finally:
        # Clean up
        linked_service.close()
        logger.info("Connection closed")


if __name__ == "__main__":
    main()
