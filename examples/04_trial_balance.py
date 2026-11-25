"""
**File:** ``04_trial_balance.py``
**Region:** ``examples/04_trial_balance``

Example 04: Fetch account balances (one row per account x period) with the generic dataset.

Uses Unimicro's native trial-balance action::

    GET /api/biz/accounts?action=trialbalance&financialyear={year}&period={n}

The action returns the whole result in one response, so ``paginate`` is turned off, and
``expand`` fans the request out over fiscal years x periods (one request per combination).
The expanded values are added to every row as ``financialyear`` and ``period`` columns.

Run from the repository root::

    uv run --extra dev python examples/04_trial_balance.py
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from dotenv import load_dotenv
from ds_common_logger_py_lib import Logger

from ds_provider_unimicro_py_lib.dataset.unimicro import (
    UnimicroDataset,
    UnimicroDatasetSettings,
    UnimicroReadSettings,
)
from ds_provider_unimicro_py_lib.linked_service.unimicro import (
    UnimicroLinkedService,
    UnimicroLinkedServiceSettings,
)

load_dotenv()

Logger.configure(level=logging.DEBUG)
logger = Logger.get_logger(__name__)


def main() -> None:
    client_id = os.environ["UNIMICRO_CLIENT_ID"]
    certificate = os.environ["UNIMICRO_CERTIFICATE"]
    certificate_password = os.environ["UNIMICRO_CERTIFICATE_PASSWORD"]
    company_key = os.environ["UNIMICRO_COMPANY_KEY"]
    host = os.getenv("UNIMICRO_HOST", "https://app.unimicro.no")
    auth_url = os.getenv("UNIMICRO_AUTH_URL", "https://login.unimicro.no")

    linked_service = UnimicroLinkedService(
        id=uuid4(),
        name="example-unimicro-linked-service",
        version="v1.0.0",
        settings=UnimicroLinkedServiceSettings(
            client_id=client_id,
            certificate=certificate,
            certificate_password=certificate_password,
            company_key=company_key,
            host=host,
            auth_url=auth_url,
        ),
    )

    dataset = UnimicroDataset(
        id=uuid4(),
        name="unimicro-trial-balance-dataset",
        version="v1.0.0",
        linked_service=linked_service,
        settings=UnimicroDatasetSettings(
            data_product="accounts",
            company_key=company_key,
            read=UnimicroReadSettings(
                params={"action": "trialbalance"},
                paginate=False,
                expand={"financialyear": 2026, "period": "1-9"},
                fields=["financialyear", "period", "AccountNumber", "AccountName", "Balance"],
            ),
        ),
    )

    try:
        dataset.linked_service.connect()
        logger.info("Reading trial balance financialyear=2026 periods=1-9...")
        dataset.read()

        if dataset.output is not None and not dataset.output.empty:
            logger.info("Read %d account balance rows", len(dataset.output))
            logger.info("Columns: %s", list(dataset.output.columns))
            logger.info("Output:\n%s", dataset.output.head(20).to_string())
        else:
            logger.info("No account balance data returned")
    finally:
        dataset.linked_service.close()


if __name__ == "__main__":
    main()
