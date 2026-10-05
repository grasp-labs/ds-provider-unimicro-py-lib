"""
**File:** ``test_unimicro_dataset.py``
**Region:** ``tests/dataset/test_unimicro_dataset``

Dataset tests for Unimicro provider.
"""

from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
from ds_resource_plugin_py_lib.common.resource.dataset.errors import ReadError
from ds_resource_plugin_py_lib.common.resource.errors import NotSupportedError

from ds_provider_unimicro_py_lib.dataset.unimicro import UnimicroDataset, UnimicroDatasetSettings, UnimicroReadSettings
from ds_provider_unimicro_py_lib.enums import ResourceType


def make_dataset(*, fields=None, filters=None, record_id=None, checkpoint=None):
    dataset = object.__new__(UnimicroDataset)
    dataset.settings = UnimicroDatasetSettings(
        data_product="Customers",
        company_key="test-company-key",
        read=UnimicroReadSettings(
            id=record_id,
            page_size=2,
            fields=fields,
            filters=filters,
        ),
    )
    dataset.linked_service = Mock(settings=Mock(host="https://api.example.com/"))
    dataset.checkpoint = checkpoint
    return dataset


def make_response(records):
    response = Mock()
    response.json.return_value = records
    return response


def test_read_settings_deserialize_from_nested_payload():
    settings = UnimicroDatasetSettings.deserialize(
        {
            "data_product": "Customers",
            "company_key": "test-company-key",
            "read": {"page_size": 50, "fields": ["Name"], "filters": "Status eq 'Open'"},
        }
    )

    assert isinstance(settings.read, UnimicroReadSettings)
    assert settings.read.page_size == 50
    assert settings.read.fields == ["Name"]
    assert settings.read.filters == "Status eq 'Open'"


def test_dataset_type_and_checkpoint_support():
    dataset = make_dataset()

    assert dataset.type == ResourceType.UNIMICRO_DATASET
    assert dataset.supports_checkpoint is True


def test_read_fetches_data_using_linked_service_connection():
    dataset = make_dataset()
    session = Mock()
    dataset.linked_service.connection = session
    dataset._fetch_data = Mock()

    dataset.read()

    dataset._fetch_data.assert_called_once_with(session=session)


@pytest.mark.parametrize("method_name", ["create", "delete", "update", "rename", "list", "upsert", "purge"])
def test_unsupported_operations_raise_not_supported_error(method_name):
    dataset = make_dataset()

    with pytest.raises(NotSupportedError):
        getattr(dataset, method_name)()


def test_build_url_includes_record_id():
    dataset = make_dataset(record_id=42)

    url = UnimicroDataset._build_url(dataset)

    assert urlsplit(url).path == "/api/biz/Customers/42"


def test_build_url_with_filters_includes_paging_fields_and_filters():
    dataset = make_dataset(
        fields=["Name"],
        filters="Status eq 'Open'",
    )

    url = UnimicroDataset._build_url_with_filters(dataset, 2, 4, "2024-01-01T00:00:00+00:00")
    query = parse_qs(urlsplit(url).query)

    assert query["top"] == ["2"]
    assert query["skip"] == ["4"]
    assert set(query["select"][0].split(",")) == {"Name", "CreatedAt", "UpdatedAt"}
    assert query["filter"][0] == (
        "(CreatedAt gt '2024-01-01T00:00:00+00:00' or UpdatedAt gt '2024-01-01T00:00:00+00:00') and Status eq 'Open'"
    )


def test_greatest_incremental_value_returns_latest_timestamp():
    dataset = make_dataset()
    records = pd.DataFrame(
        {
            "CreatedAt": ["2024-01-01T00:00:00Z"],
            "UpdatedAt": ["2024-03-01T00:00:00Z"],
        }
    )

    result = UnimicroDataset.greatest_incremental_value(dataset, records)

    assert result == "2024-03-01T00:00:00+00:00"


def test_greatest_incremental_value_returns_none_without_valid_timestamps():
    dataset = make_dataset()
    records = pd.DataFrame({"CreatedAt": ["not-a-date"]})

    assert UnimicroDataset.greatest_incremental_value(dataset, records) is None


def test_fetch_data_reads_pages_and_builds_output_and_checkpoint():
    dataset = make_dataset()
    session = Mock()
    session.get.side_effect = [
        make_response([{"Name": "Ada", "UpdatedAt": "2024-01-01T00:00:00Z"}]),
        make_response([{"Name": "Lin", "UpdatedAt": "2024-02-01T00:00:00Z"}]),
        make_response([]),
    ]

    UnimicroDataset._fetch_data(dataset, session)

    requested_skips = [parse_qs(urlsplit(call.args[0]).query)["skip"][0] for call in session.get.call_args_list]
    assert requested_skips == ["0", "1", "2"]
    assert dataset.output["Name"].tolist() == ["Ada", "Lin"]
    assert dataset.checkpoint["incremental"]["value"] == "2024-02-01T00:00:00+00:00"


def test_fetch_data_removes_unselected_timestamp_columns():
    dataset = make_dataset(fields=["Name"])
    session = Mock()
    session.get.side_effect = [
        make_response(
            [
                {
                    "Name": "Ada",
                    "CreatedAt": "2024-01-01T00:00:00Z",
                    "UpdatedAt": "2024-02-01T00:00:00Z",
                }
            ]
        ),
        make_response([]),
    ]

    UnimicroDataset._fetch_data(dataset, session)

    assert dataset.output.columns.tolist() == ["Name"]
    assert dataset.checkpoint["incremental"]["value"] == "2024-02-01T00:00:00+00:00"


def test_fetch_data_resumes_from_checkpoint():
    dataset = make_dataset(
        checkpoint={
            "pagination": {"value": 4},
            "incremental": {"value": "2024-01-01T00:00:00+00:00"},
        }
    )
    session = Mock()
    session.get.return_value = make_response([])

    UnimicroDataset._fetch_data(dataset, session)

    url = session.get.call_args.args[0]
    query = parse_qs(urlsplit(url).query)
    assert query["skip"] == ["4"]
    assert "CreatedAt gt '2024-01-01T00:00:00+00:00'" in query["filter"][0]


def test_fetch_data_wraps_request_errors_in_read_error():
    dataset = make_dataset()
    session = Mock()
    session.get.side_effect = RuntimeError("API unavailable")

    with pytest.raises(ReadError, match="API unavailable"):
        UnimicroDataset._fetch_data(dataset, session)

    assert dataset.checkpoint == {
        "incremental": {"value": None},
        "pagination": {"value": 0},
    }
