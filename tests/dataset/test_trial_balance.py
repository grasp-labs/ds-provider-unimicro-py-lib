"""
**File:** ``test_trial_balance.py``
**Region:** ``tests/dataset/test_trial_balance``

Tests for the ``trialbalance`` data product.
"""

from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from ds_resource_plugin_py_lib.common.resource.dataset.errors import ReadError

from ds_provider_unimicro_py_lib.dataset.products import trial_balance
from ds_provider_unimicro_py_lib.dataset.unimicro import (
    UnimicroDataset,
    UnimicroDatasetSettings,
    UnimicroReadSettings,
)


def make_dataset(*, params=None, fields=None, filters=None, record_id=None, checkpoint=None):
    dataset = object.__new__(UnimicroDataset)
    dataset.settings = UnimicroDatasetSettings(
        data_product="trialbalance",
        company_key="test-company-key",
        read=UnimicroReadSettings(id=record_id, fields=fields, filters=filters, params=params),
    )
    dataset.linked_service = Mock(settings=Mock(host="https://api.example.com/"))
    dataset.checkpoint = checkpoint
    return dataset


def make_response(records):
    response = Mock()
    response.json.return_value = records
    return response


def queries(session):
    return [parse_qs(urlsplit(call.args[0]).query) for call in session.get.call_args_list]


@pytest.mark.parametrize(
    ("data_product", "expected"),
    [("trialbalance", True), ("TrialBalance", True), ("accounts", False), ("Customers", False)],
)
def test_handles_matches_trialbalance_case_insensitively(data_product, expected):
    assert trial_balance.handles(data_product) is expected


def test_fetch_fans_out_over_years_and_periods_and_stamps_rows():
    dataset = make_dataset(
        params={"financialyear": "2025-2026", "period": "1-2"},
        fields=["financialyear", "period", "AccountNumber", "Balance"],
    )
    session = Mock()
    session.get.side_effect = [make_response([{"AccountNumber": 1500, "Balance": float(n)}]) for n in range(4)]

    trial_balance.fetch(dataset, session)

    assert [(q["financialyear"][0], q["period"][0]) for q in queries(session)] == [
        ("2025", "1"),
        ("2025", "2"),
        ("2026", "1"),
        ("2026", "2"),
    ]
    for query in queries(session):
        assert query["action"] == ["trialbalance"]
        assert not {"top", "skip", "select", "filter"} & set(query)
    assert urlsplit(session.get.call_args.args[0]).path == "/api/biz/accounts"
    assert session.get.call_args.kwargs["headers"] == {"CompanyKey": "test-company-key"}
    assert list(dataset.output.columns) == ["financialyear", "period", "AccountNumber", "Balance"]
    assert dataset.output["financialyear"].tolist() == [2025, 2025, 2026, 2026]
    assert dataset.output["period"].tolist() == [1, 2, 1, 2]


def test_fetch_defaults_to_all_twelve_periods_and_passes_other_params_through():
    dataset = make_dataset(params={"financialyear": 2026, "hateoas": "false"})
    session = Mock()
    session.get.return_value = make_response([])

    trial_balance.fetch(dataset, session)

    assert [q["period"][0] for q in queries(session)] == [str(n) for n in range(1, 13)]
    assert all(q["hateoas"] == ["false"] for q in queries(session))


def test_fetch_resets_checkpoint_on_success():
    dataset = make_dataset(params={"financialyear": 2026, "period": 1}, checkpoint={"pagination": {"value": 7}})
    session = Mock()
    session.get.return_value = make_response([{"AccountNumber": 1500}])

    trial_balance.fetch(dataset, session)

    assert dataset.checkpoint == {"incremental": {"value": None}, "pagination": {"value": 0}}


def test_fetch_requires_financialyear():
    dataset = make_dataset(params={"period": 1})
    session = Mock()

    with pytest.raises(ReadError, match="financialyear is required"):
        trial_balance.fetch(dataset, session)

    session.get.assert_not_called()


@pytest.mark.parametrize(
    ("overrides", "rejected"),
    [
        ({"record_id": 1}, "read.id"),
        ({"filters": "Status eq 'Open'"}, "read.filters"),
        ({"params": {"financialyear": 2026, "action": "other"}}, "read.params.action"),
        ({"params": {"financialyear": 2026, "top": 5}}, "read.params.top"),
        ({"params": {"financialyear": 2026, "skip": 5}}, "read.params.skip"),
        ({"params": {"financialyear": 2026, "select": "Name"}}, "read.params.select"),
        ({"params": {"financialyear": 2026, "filter": "Status eq 'Open'"}}, "read.params.filter"),
    ],
)
def test_fetch_rejects_settings_it_cannot_honour(overrides, rejected):
    dataset = make_dataset(**{"params": {"financialyear": 2026}, **overrides})
    session = Mock()

    with pytest.raises(ReadError, match="not supported for trialbalance") as exc_info:
        trial_balance.fetch(dataset, session)

    assert rejected in exc_info.value.details
    session.get.assert_not_called()


def test_fetch_rejects_non_list_payload_without_rewrapping():
    checkpoint = {"incremental": {"value": None}, "pagination": {"value": 0}}
    dataset = make_dataset(params={"financialyear": 2026, "period": "1-2"}, checkpoint=checkpoint)
    session = Mock()
    session.get.return_value = make_response({"error": "nope"})

    with pytest.raises(ReadError, match="expected list") as exc_info:
        trial_balance.fetch(dataset, session)

    assert exc_info.value.details == {"payload_type": "dict", "financialyear": 2026, "period": 1}
    assert exc_info.value.__cause__ is None
    assert dataset.checkpoint == checkpoint


def test_fetch_wraps_request_errors_with_the_failing_combination():
    dataset = make_dataset(params={"financialyear": 2026, "period": "1-3"})
    session = Mock()
    session.get.side_effect = [make_response([{"AccountNumber": 1500}]), RuntimeError("API unavailable")]

    with pytest.raises(ReadError, match="API unavailable") as exc_info:
        trial_balance.fetch(dataset, session)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert exc_info.value.details["period"] == 2
    assert exc_info.value.details["successfully_fetched_records"] == 1
