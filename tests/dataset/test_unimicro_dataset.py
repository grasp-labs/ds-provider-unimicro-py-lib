"""
**File:** ``test_unimicro_dataset.py``
**Region:** ``tests/dataset/test_unimicro_dataset``

Dataset tests for the generic Unimicro biz dataset.
"""

from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from ds_resource_plugin_py_lib.common.resource.dataset.errors import ReadError
from ds_resource_plugin_py_lib.common.resource.errors import NotSupportedError

from ds_provider_unimicro_py_lib.dataset.products import trial_balance
from ds_provider_unimicro_py_lib.dataset.unimicro import (
    UnimicroDataset,
    UnimicroDatasetSettings,
    UnimicroReadSettings,
)
from ds_provider_unimicro_py_lib.enums import ResourceType


def make_dataset(
    *,
    fields=None,
    filters=None,
    record_id=None,
    checkpoint=None,
    data_product="Customers",
    page_size=2,
    params=None,
):
    dataset = object.__new__(UnimicroDataset)
    dataset.settings = UnimicroDatasetSettings(
        data_product=data_product,
        company_key="test-company-key",
        read=UnimicroReadSettings(
            id=record_id,
            page_size=page_size,
            fields=fields,
            filters=filters,
            params=params,
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


@pytest.mark.parametrize("data_product", ["Customers", "trialbalance"])
def test_dataset_type_and_checkpoint_support(data_product):
    dataset = make_dataset(data_product=data_product)

    assert dataset.type == ResourceType.UNIMICRO_DATASET
    assert dataset.supports_checkpoint is True


def test_read_fetches_data_using_linked_service_connection():
    dataset = make_dataset()
    session = Mock()
    dataset.linked_service.connection = session
    dataset._fetch_data = Mock()

    dataset.read()

    dataset._fetch_data.assert_called_once_with(session=session)


def test_read_routes_trialbalance_to_its_product(monkeypatch):
    dataset = make_dataset(data_product="TrialBalance")
    session = Mock()
    dataset.linked_service.connection = session
    dataset._fetch_data = Mock()
    fetch = Mock()
    monkeypatch.setattr(trial_balance, "fetch", fetch)

    dataset.read()

    fetch.assert_called_once_with(dataset, session)
    dataset._fetch_data.assert_not_called()


def test_fetch_data_rejects_trialbalance_action_on_entity_reader():
    dataset = make_dataset(data_product="accounts", params={"action": "trialbalance", "financialyear": 2026})
    session = Mock()

    with pytest.raises(ReadError, match="data_product='trialbalance'"):
        UnimicroDataset._fetch_data(dataset, session)

    session.get.assert_not_called()


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


def test_build_url_merges_params_into_query():
    dataset = make_dataset(params={"hateoas": "true"})

    url = UnimicroDataset._build_url_with_filters(dataset, 1000, 0, None)
    query = parse_qs(urlsplit(url).query)

    assert query["top"] == ["1000"]
    assert query["skip"] == ["0"]
    assert query["hateoas"] == ["true"]


def test_build_url_with_filters_never_lets_params_override_paging_keys():
    dataset = make_dataset(
        fields=["Name"],
        filters="Status eq 'Open'",
        params={"top": 5, "skip": 99, "select": "Other", "filter": "Other eq 1", "hateoas": "true"},
    )

    url = UnimicroDataset._build_url_with_filters(dataset, 2, 4, "2024-01-01T00:00:00+00:00")
    query = parse_qs(urlsplit(url).query)

    assert query["top"] == ["2"]
    assert query["skip"] == ["4"]
    assert set(query["select"][0].split(",")) == {"Name", "CreatedAt", "UpdatedAt"}
    assert "CreatedAt gt '2024-01-01T00:00:00+00:00'" in query["filter"][0]
    assert "Other eq 1" not in query["filter"][0]
    assert query["hateoas"] == ["true"]


@pytest.mark.parametrize("reserved_key", ["top", "skip", "select", "filter"])
def test_fetch_data_rejects_reserved_params(reserved_key):
    checkpoint = {"incremental": {"value": "2024-01-01T00:00:00+00:00"}, "pagination": {"value": 4}}
    dataset = make_dataset(params={reserved_key: "x", "hateoas": "true"}, checkpoint=checkpoint)
    session = Mock()

    with pytest.raises(ReadError, match=reserved_key) as exc_info:
        UnimicroDataset._fetch_data(dataset, session)

    assert exc_info.value.details["reserved_params"] == [reserved_key]
    session.get.assert_not_called()
    # A configuration error is not a failed page, so the checkpoint is left alone.
    assert dataset.checkpoint == checkpoint


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


def test_fetch_data_projects_output_to_requested_fields():
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


def test_fetch_data_rejects_non_list_payload_without_rewrapping_and_still_writes_checkpoint():
    dataset = make_dataset()
    session = Mock()
    session.get.return_value = make_response({"error": "nope"})

    with pytest.raises(ReadError, match="expected list") as exc_info:
        UnimicroDataset._fetch_data(dataset, session)

    # The shape error is re-raised as is, so its own details survive instead of living on __cause__.
    assert exc_info.value.details == {"payload_type": "dict"}
    assert exc_info.value.__cause__ is None
    # A bad page is still a failed read, so the checkpoint is written.
    assert dataset.checkpoint == {
        "incremental": {"value": None},
        "pagination": {"value": 0},
    }


def test_build_url_with_filters_omits_skip_when_records_to_skip_is_none():
    dataset = make_dataset()

    url = UnimicroDataset._build_url_with_filters(dataset, 10, None, None)
    query = parse_qs(urlsplit(url).query)

    assert query["top"] == ["10"]
    assert "skip" not in query


def test_build_url_with_filters_does_not_duplicate_timestamp_fields():
    dataset = make_dataset(fields=["Name", "CreatedAt", "UpdatedAt"])

    url = UnimicroDataset._build_url_with_filters(dataset, 2, 0, None)
    query = parse_qs(urlsplit(url).query)

    assert set(query["select"][0].split(",")) == {"Name", "CreatedAt", "UpdatedAt"}


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
