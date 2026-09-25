"""
**File:** ``unimicro.py``
**Region:** ``ds_provider_unimicro_py_lib/dataset/unimicro``

This module contains dataset-related classes and functions for the Unimicro provider.

Example:
    >>> import ds_provider_unimicro_py_lib.dataset.unimicro
"""

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import pandas as pd
from ds_common_logger_py_lib import Logger
from ds_resource_plugin_py_lib.common.resource.dataset import DatasetSettings, DatasetStorageFormatType, TabularDataset
from ds_resource_plugin_py_lib.common.resource.dataset.errors import (
    ReadError,
)
from ds_resource_plugin_py_lib.common.resource.errors import NotSupportedError
from ds_resource_plugin_py_lib.common.serde.deserialize import PandasDeserializer
from ds_resource_plugin_py_lib.common.serde.serialize import PandasSerializer

from ..enums import ResourceType
from ..linked_service.unimicro import UnimicroLinkedService

logger = Logger.get_logger(__name__, package=True)


@dataclass(kw_only=True)
class UnimicroReadSettings:
    """
    Read settings specific to the Unimicro provider.
    """

    id: int | None = None
    """The unique identifier of the record to read from the Unimicro dataset. Optional."""

    page_size: int = 1000
    """The number of records to fetch per page from the Unimicro dataset. Default is 1000."""

    fields: list[str] | None = None
    """The specific fields to read from the Unimicro dataset. Optional."""

    filters: str | None = None
    """Custom filters to apply when reading from the Unimicro dataset. Knowledge of the filter syntax is required. Optional."""


@dataclass(kw_only=True)
class UnimicroUpdateSettings:
    """
    Update settings specific to the Unimicro provider.
    """

    id: int
    """The unique identifier of the record to update in the Unimicro dataset."""


@dataclass(kw_only=True)
class UnimicroDeleteSettings:
    """
    Delete settings specific to the Unimicro provider.
    """

    id: int
    """The unique identifier of the record to delete in the Unimicro dataset."""


@dataclass(kw_only=True)
class UnimicroDatasetSettings(DatasetSettings):
    """
    Dataset settings specific to the Unimicro provider.
    """

    data_product: str
    """The specific data product within the Unimicro provider."""

    read: UnimicroReadSettings = field(default_factory=UnimicroReadSettings)
    """Read settings for the Unimicro dataset."""

    update: UnimicroUpdateSettings
    """Update settings for the Unimicro dataset."""

    delete: UnimicroDeleteSettings
    """Delete settings for the Unimicro dataset."""


UnimicroDatasetSettingsType = TypeVar("UnimicroDatasetSettingsType", bound=UnimicroDatasetSettings)
UnimicroLinkedServiceType = TypeVar("UnimicroLinkedServiceType", bound=UnimicroLinkedService[Any])


@dataclass(kw_only=True)
class UnimicroDataset(
    TabularDataset[UnimicroLinkedServiceType, UnimicroDatasetSettingsType, PandasSerializer, PandasDeserializer],
    Generic[UnimicroLinkedServiceType, UnimicroDatasetSettingsType],
):
    """
    UnimicroDataset represents a dataset specific to the Unimicro provider.
    """

    linked_service: UnimicroLinkedServiceType
    settings: UnimicroDatasetSettingsType

    serializer: PandasSerializer | None = field(default_factory=lambda: PandasSerializer(format=DatasetStorageFormatType.JSON))
    deserializer: PandasDeserializer | None = field(
        default_factory=lambda: PandasDeserializer(format=DatasetStorageFormatType.JSON)
    )

    @property
    def type(self) -> ResourceType:
        return ResourceType.UNIMICRO_DATASET

    @property
    def supports_checkpoint(self) -> bool:
        """
        Whether this provider supports incremental loads via ``self.checkpoint``.

        The checkpoint is a dictionary that tracks pagination and incremental state:

        - On a full load, ``self.checkpoint`` is expected to be empty (``{}``) or ``None``.
          In this case, :meth:`read` starts from page ``1``.
        - After each successfully read page, ``self.checkpoint`` is updated with at least ``{"last_page": page, ...}``.
        - If incremental loading is possible (i.e., the data contains a ``lastChangedDateTimeOffset`` field),
          the checkpoint will also include an ``incremental`` key with the latest observed value:
           ``{"incremental": {"last_modified_date": ...}}``.
        - On a subsequent run, if ``self.checkpoint`` contains a ``"last_page"`` entry,
          :meth:`read` resumes from ``last_page + 1`` and continues fetching data from the PowerOfficeGo API.
        - If ``self.checkpoint`` contains an ``incremental`` key, the loader will use the stored ``last_modified_date``
          to filter for new/changed records.

        This allows consumers to perform incremental loads by persisting and reusing
        the checkpoint between executions, avoiding re-reading pages that were already processed successfully.
        The checkpoint structure is designed to support both paginated and incremental (watermark-based) loading.

        Returns:
            bool: True if checkpointing is supported, False otherwise.
        """
        return True

    def read(self) -> None:
        """
        Reads data from the Unimicro dataset.

        This method should implement the logic to fetch data from the Unimicro API,
        respecting the current checkpoint for incremental loading.

        Returns:
            None
        """
        logger.info(f"Reading data from Unimicro dataset with settings: {self.settings}")
        session = self.linked_service.connection
        self._fetch_data(session=session)

    def create(self) -> None:
        raise NotSupportedError("Method create is not supported by Unimicro provider.")

    def delete(self) -> None:
        raise NotSupportedError("Method delete is not supported by Unimicro provider.")

    def update(self) -> None:
        raise NotSupportedError("Method update is not supported by Unimicro provider.")

    def rename(self) -> None:
        raise NotSupportedError("Method rename is not supported by Unimicro provider.")

    def list(self) -> None:
        raise NotSupportedError("Method list is not supported by Unimicro provider.")

    def upsert(self) -> None:
        raise NotSupportedError("Method upsert is not supported by Unimicro provider.")

    def purge(self) -> None:
        raise NotSupportedError("Method purge is not supported by Unimicro provider.")

    def _fetch_data(self, session: Any) -> None:
        """
        Fetches data from the Unimicro API using the provided session.

        Args:
            session (Any): The session object used to make API requests.

        Returns:
            None
        """
        logger.info(f"Fetching data from Unimicro API for data product: {self.settings.data_product}.")
        last_modified_date = None
        if self.checkpoint and "incremental" in self.checkpoint:
            logger.info(f"Resuming from checkpoint with from_date: {self.checkpoint['incremental']['value']}")
            last_modified_date = self.checkpoint["incremental"]["value"]

        records_to_skip = self.checkpoint.get("pagination", {}).get("value", 0) if self.checkpoint else 0
        # TODO: Add a good logging statement for records_to_skip

        all_records: list[dict[str, Any]] = []

        successfully_fetched_records = 0

        try:
            while True:
                records_to_skip += successfully_fetched_records
                url = self._build_url_with_filters(
                    page_size=self.settings.read.page_size,
                    records_to_skip=records_to_skip,
                    last_modified_date=last_modified_date,
                )
                logger.debug(f"Making API request to {url}.")
                response = session.get(url)
                data = response.json()

                all_records.extend(data)
                logger.info(f"Fetched {len(data)} records from the API.")
                successfully_fetched_records += len(data)

                if not data:
                    break

        except Exception as exc:
            logger.error(f"Error occurred while fetching data: {exc}")
            self.checkpoint = self._build_checkpoint(successfully_fetched_records, last_modified_date)
            raise ReadError(
                message=f"Error occurred while fetching data: {exc}",
                details={
                    "successfully_fetched_records": successfully_fetched_records,
                    "data_product": self.settings.data_product,
                    "settings": self.settings,
                },
            ) from exc
        else:
            logger.info(f"Total successfully fetched records: {successfully_fetched_records}")
            # convert to dataframe
            self.output = pd.json_normalize(all_records, sep="_")
            # find the greatest incremental value
            greatest_incremental_value = self.greatest_incremental_value(self.output)
            # remove CreatedAt and/or UpdatedAt columns from the dataframe if fields are defined in the settings
            if self.settings.read.fields and (
                "CreatedAt" not in self.settings.read.fields or "UpdatedAt" not in self.settings.read.fields
            ):
                self.output.drop(columns=[col for col in ("CreatedAt", "UpdatedAt") if col in self.output.columns], inplace=True)
            # build checkpoint
            self.checkpoint = self._build_checkpoint(last_loaded_records=0, last_modified_date=greatest_incremental_value)

    def greatest_incremental_value(self, all_records: pd.DataFrame) -> str | None:
        """
        Determine the greatest incremental value (last modified date) from the fetched records.

        Args:
            all_records (pd.DataFrame): The dataframe of all fetched records.

        Returns:
            str | None: The greatest incremental value found, or None if no records exist.
        """
        timestamp_columns = [column for column in ("CreatedAt", "UpdatedAt") if column in all_records]

        if not timestamp_columns:
            return None

        timestamps = pd.concat(
            [pd.to_datetime(all_records[column], utc=True, errors="coerce") for column in timestamp_columns],
            ignore_index=True,
        ).dropna()

        if timestamps.empty:
            return None

        return timestamps.max().isoformat()

    def _build_checkpoint(self, last_loaded_records: int | None, last_modified_date: str | None) -> dict[str, Any]:
        """
        Build a checkpoint dictionary to track the last successfully read page.

        Include last_modified_date from read settings.

        Args:
            last_loaded_records (int | None): The number of records that were successfully read.
            last_modified_date (str | None): The last modified date to include in the checkpoint.
        Returns:
            dict[str, Any]: A checkpoint dictionary containing the last loaded records information.
        """
        checkpoint = {
            "incremental": {"value": last_modified_date},  # or None
            "pagination": {"value": last_loaded_records},  # amount of records read so far (records to skip)
        }
        logger.debug(f"Built checkpoint: {checkpoint}")
        return checkpoint

    def _build_incremental_filter(self, last_modified_date: str) -> str:
        """Build the provider-specific incremental filter."""
        # TODO: Test in Unimicro API environment to ensure correct filter syntax
        return f"(CreatedAt gt '{last_modified_date}' or UpdatedAt gt '{last_modified_date}')"

    def _build_url_with_filters(self, page_size: int, records_to_skip: int | None, last_modified_date: str | None) -> str:
        """
        Constructs the filter string for the Unimicro API request based on the current settings.

        Args:
            page_size (int): The number of records per page for pagination.
            records_to_skip (int | None): The number of records to skip for pagination.
            last_modified_date (str | None): The last modified date to filter the data.

        Returns:
            str: The constructed filter string.
        """
        base_url = self._build_url()
        url = f"{base_url}?top={page_size}"
        if records_to_skip is not None:
            url += f"&skip={records_to_skip}"
        if self.settings.read.fields:
            selected_fields = set(self.settings.read.fields)
            # Add check on if CreatedAt and UpdatedAt fields are included in the selected fields
            if "CreatedAt" not in selected_fields:
                selected_fields.add("CreatedAt")
            if "UpdatedAt" not in selected_fields:
                selected_fields.add("UpdatedAt")
            url += f"&select={','.join(selected_fields)}"

        filter_clauses = []
        if last_modified_date:
            filter_clauses.append(self._build_incremental_filter(last_modified_date))
        if self.settings.read.filters:
            filter_clauses.append(self.settings.read.filters)

        if filter_clauses:
            url += f"&filter={' and '.join(filter_clauses)}"

        return url

    def _build_url(self) -> str:
        """
        Constructs the URL for accessing the Unimicro API.

        Returns:
            str: The constructed URL.
        """
        base_url = self.linked_service.settings.host.rstrip("/") + "/"
        url = f"{base_url}/api/biz/{self.settings.data_product}"
        return url
