"""
**File:** ``unimicro.py``
**Region:** ``ds_provider_unimicro_py_lib/dataset/unimicro``

Generic Unimicro biz-dataset reader (``/api/biz/{data_product}``).
"""

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar
from urllib.parse import urlencode

import pandas as pd
from ds_common_logger_py_lib import Logger
from ds_common_serde_py_lib import Serializable
from ds_resource_plugin_py_lib.common.resource.dataset import DatasetSettings, DatasetStorageFormatType, TabularDataset
from ds_resource_plugin_py_lib.common.resource.dataset.errors import (
    ReadError,
)
from ds_resource_plugin_py_lib.common.resource.errors import NotSupportedError
from ds_resource_plugin_py_lib.common.serde.deserialize import PandasDeserializer
from ds_resource_plugin_py_lib.common.serde.serialize import PandasSerializer

from ..enums import ResourceType
from ..linked_service.unimicro import UnimicroLinkedService
from ..utils.dataframe import project_fields
from ..utils.incremental import build_checkpoint, build_incremental_filter, greatest_incremental_value
from ..utils.ranges import expand_combinations

logger = Logger.get_logger(__name__, package=True)


@dataclass(kw_only=True)
class UnimicroReadSettings(Serializable):
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

    params: dict[str, str | int] | None = None
    """Extra query parameters merged into the request URL. Optional."""

    paginate: bool = True
    """
    Whether to page through results with ``top``/``skip`` until an empty page is returned. Default is True.

    Set to False for endpoints that return the full result in one response (e.g. ``accounts`` with
    ``params={"action": "trialbalance", ...}``). In this mode a single request is made per expansion
    combination; ``top``, ``skip``, ``select`` and ``filter`` are not sent (pass anything the endpoint needs via
    ``params``), incremental filtering is disabled, and the checkpoint is neither read nor written.
    The ``fields`` projection is still applied to the output.
    """

    expand: dict[str, list[int] | int | str] | None = None
    """
    Query parameters to fan out over, one request per combination (cartesian product). Optional.

    Each value is an int, a list of ints, or a ``start-end`` range string, e.g.
    ``{"financialyear": "2023-2026", "period": "1-12"}``. The expanded values are sent as query parameters
    (overriding the same key in ``params``) and added as columns to every returned row.
    Requires ``paginate=False``.
    """


@dataclass(kw_only=True)
class UnimicroDatasetSettings(DatasetSettings):
    """
    Dataset settings specific to the Unimicro provider.
    """

    data_product: str
    """Native Unimicro biz entity name (e.g. ``Customers``, ``accounts``)."""

    company_key: str
    """The company key used for fetching data from the Unimicro provider."""

    read: UnimicroReadSettings = field(default_factory=UnimicroReadSettings)
    """Read settings for the Unimicro dataset."""


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
        Whether this provider supports checkpointing for incremental reads.

        The checkpoint has this structure::

            {
                "incremental": {"value": <timestamp or None>},
                "pagination": {"value": <record offset>},
            }

        During a read, ``pagination.value`` is used as the initial API ``skip``
        offset (defaulting to 0). Pagination is handled within the read call:
        each subsequent request skips the initial offset plus the number of
        records already fetched during that call.

        When ``incremental.value`` is set, requests filter for records whose
        ``CreatedAt`` or ``UpdatedAt`` timestamp is greater than that value.
        After a successful read, the checkpoint is replaced with the latest
        valid timestamp found in the returned records, and ``pagination.value``
        is reset to 0. If no valid timestamps are found, the incremental value
        is None.

        If a request fails, the checkpoint is updated with the number of
        records fetched during that read attempt and retains the prior
        incremental value. Consumers should persist checkpoints separately for
        each dataset and company.

        Checkpointing applies to paginated reads only. With ``paginate=False`` the
        whole result is fetched in one go, so there is nothing to resume or filter on.

        Returns:
            bool: True when ``settings.read.paginate`` is enabled, otherwise False.
        """
        return self.settings.read.paginate

    def read(self) -> None:
        """
        Reads data from the Unimicro dataset.

        This method should implement the logic to fetch data from the Unimicro API,
        respecting the current checkpoint for incremental loading.

        Returns:
            None
        """
        logger.info("Reading data from Unimicro dataset with settings: %s", self.settings)
        session = self.linked_service.connection
        self._fetch_data(session=session)

    def _fetch_data(self, session: Any) -> None:
        """
        Fetches data from the Unimicro API using the provided session.

        Args:
            session (Any): The session object used to make API requests.

        Returns:
            None
        """
        if not self.settings.read.paginate:
            self._fetch_data_unpaginated(session)
            return

        if self.settings.read.expand:
            raise ReadError(
                message="read.expand requires read.paginate to be False.",
                details={"expand": self.settings.read.expand, "paginate": self.settings.read.paginate},
            )

        logger.info("Fetching data from Unimicro API for data product: %s.", self.settings.data_product)
        last_modified_date = None
        if self.checkpoint and "incremental" in self.checkpoint:
            logger.info("Resuming from checkpoint with from_date: %s", self.checkpoint["incremental"]["value"])
            last_modified_date = self.checkpoint["incremental"]["value"]

        starting_records_to_skip = self.checkpoint.get("pagination", {}).get("value", 0) if self.checkpoint else 0
        logger.info("Starting pagination from record number: %s.", starting_records_to_skip)

        all_records: list[dict[str, Any]] = []
        successfully_fetched_records = 0

        try:
            while True:
                records_to_skip = starting_records_to_skip + successfully_fetched_records
                url = self._build_url_with_filters(
                    page_size=self.settings.read.page_size,
                    records_to_skip=records_to_skip,
                    last_modified_date=last_modified_date,
                )
                logger.debug("Making API request to %s.", url)
                response = session.get(url, headers={"CompanyKey": self.settings.company_key})
                data = response.json()
                if not isinstance(data, list):
                    raise ReadError(
                        message="Unexpected Unimicro biz response shape (expected list).",
                        details={"payload_type": type(data).__name__},
                    )

                all_records.extend(data)
                logger.info("Fetched %d records from the API.", len(data))
                successfully_fetched_records += len(data)

                if not data:
                    break

        except Exception as exc:
            logger.error("Error occurred while fetching data: %s", exc)
            self.checkpoint = build_checkpoint(starting_records_to_skip, last_modified_date)
            raise ReadError(
                message=f"Error occurred while fetching data: {exc}",
                details={
                    "successfully_fetched_records": successfully_fetched_records,
                    "data_product": self.settings.data_product,
                    "settings": self.settings,
                },
            ) from exc

        logger.info("Total successfully fetched records: %d", successfully_fetched_records)
        self.output = pd.json_normalize(all_records, sep="_")
        latest_incremental_value = greatest_incremental_value(self.output)
        self.output = project_fields(self.output, self.settings.read.fields)
        self.checkpoint = build_checkpoint(
            last_loaded_records=0,
            last_modified_date=latest_incremental_value or last_modified_date,
        )

    def _fetch_data_unpaginated(self, session: Any) -> None:
        """
        Fetch data with one plain request per ``read.expand`` combination (or a single request without ``expand``).

        No ``top``/``skip``/``select``/``filter`` is sent, and the checkpoint is left untouched.
        The expanded parameter values are added to every returned row as columns.

        Args:
            session (Any): The session object used to make API requests.

        Returns:
            None
        """
        combinations = expand_combinations(self.settings.read.expand)
        logger.info(
            "Fetching data from Unimicro API for data product: %s (%d request(s), unpaginated).",
            self.settings.data_product,
            len(combinations),
        )

        all_records: list[dict[str, Any]] = []
        try:
            for combination in combinations:
                url = self._build_unpaginated_url(combination)
                logger.debug("Making API request to %s.", url)
                response = session.get(url, headers={"CompanyKey": self.settings.company_key})
                data = response.json()
                if not isinstance(data, list):
                    raise ReadError(
                        message="Unexpected Unimicro biz response shape (expected list).",
                        details={"payload_type": type(data).__name__, "expand": combination},
                    )

                for record in data:
                    record.update(combination)
                    all_records.append(record)
                logger.info("Fetched %d records from the API for %s.", len(data), combination or "request")
        except Exception as exc:
            logger.error("Error occurred while fetching data: %s", exc)
            raise ReadError(
                message=f"Error occurred while fetching data: {exc}",
                details={
                    "successfully_fetched_records": len(all_records),
                    "data_product": self.settings.data_product,
                    "settings": self.settings,
                },
            ) from exc

        logger.info("Total successfully fetched records: %d", len(all_records))
        self.output = project_fields(pd.json_normalize(all_records, sep="_"), self.settings.read.fields)

    def _build_unpaginated_url(self, extra_params: dict[str, int] | None = None) -> str:
        """
        Build a plain request URL from ``read.params`` plus the given expansion values.

        Args:
            extra_params: Expansion values; these override the same keys in ``read.params``.

        Returns:
            str: Fully qualified request URL, with a query string only if there are parameters.
        """
        query_params: dict[str, str | int] = {**(self.settings.read.params or {}), **(extra_params or {})}
        base_url = self._build_url()
        return f"{base_url}?{urlencode(query_params)}" if query_params else base_url

    def _build_url_with_filters(self, page_size: int, records_to_skip: int | None, last_modified_date: str | None) -> str:
        """
        Build the Unimicro request URL for the current read settings.

        Args:
            page_size: OData ``top`` page size.
            records_to_skip: OData ``skip`` offset.
            last_modified_date: Incremental watermark for CreatedAt/UpdatedAt filter.

        Returns:
            Fully qualified request URL including query string.
        """
        base_url = self._build_url()
        query_params: dict[str, str | int] = {"top": page_size}
        if records_to_skip is not None:
            query_params["skip"] = records_to_skip
        if self.settings.read.fields:
            selected_fields = set(self.settings.read.fields)
            if "CreatedAt" not in selected_fields:
                selected_fields.add("CreatedAt")
            if "UpdatedAt" not in selected_fields:
                selected_fields.add("UpdatedAt")
            query_params["select"] = ",".join(selected_fields)

        filter_clauses = []
        if last_modified_date:
            filter_clauses.append(build_incremental_filter(last_modified_date))
        if self.settings.read.filters:
            filter_clauses.append(self.settings.read.filters)
        if filter_clauses:
            query_params["filter"] = " and ".join(filter_clauses)

        if self.settings.read.params:
            query_params.update(self.settings.read.params)

        return f"{base_url}?{urlencode(query_params)}"

    def _build_url(self) -> str:
        """
        Constructs the URL for accessing the Unimicro API.

        Returns:
            str: The constructed URL.
        """
        base_url = self.linked_service.settings.host.rstrip("/")
        url = f"{base_url}/api/biz/{self.settings.data_product}"
        if self.settings.read.id:
            url += f"/{self.settings.read.id}"
        return url

    def close(self) -> None:
        """
        Release any resources held by the dataset.

        Connection lifecycle is managed by the linked service.
        """

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
