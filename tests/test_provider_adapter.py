import pytest

from models import Transaction
from provider_adapter import ProviderAdapterError, SandboxPaymentAdapter


def make_transaction(**overrides):
    values = {
        "transaction_id": "SANDBOX-TEST-001",
        "sender": "customer-001",
        "receiver": "merchant-001",
        "asset": "NGN",
        "amount": 1500.00,
        "channel": "sandbox_test",
        "country": "NG",
        "device_id": "device-001",
    }
    values.update(overrides)
    return Transaction(**values)


def test_prepare_returns_sandbox_request_without_submitting():
    adapter = SandboxPaymentAdapter()
    prepared = adapter.prepare(make_transaction())

    assert prepared["provider"] == "trustng-sandbox"
    assert prepared["sandbox"] is True
    assert prepared["request"]["transaction_id"] == "SANDBOX-TEST-001"
    assert prepared["request"]["asset"] == "NGN"
    assert prepared["request"]["amount"] == "1500"
    assert prepared["idempotency_key"].startswith("tn-sandbox-")
    assert "status" not in prepared


def test_idempotency_key_is_stable_for_same_transaction_id():
    adapter = SandboxPaymentAdapter()

    first = adapter.prepare(make_transaction())
    second = adapter.prepare(make_transaction(amount=1500))

    assert first["idempotency_key"] == second["idempotency_key"]


def test_submit_is_explicitly_simulated():
    result = SandboxPaymentAdapter().submit(make_transaction())

    assert result["status"] == "SIMULATED_SUCCESS"
    assert result["sandbox"] is True
    assert result["outcome_uncertain"] is False
    assert "no funds were moved" in result["message"]


def test_duplicate_submission_replays_saved_result():
    adapter = SandboxPaymentAdapter()
    transaction = make_transaction()

    first = adapter.submit(transaction)
    second = adapter.submit(transaction)

    assert first["status"] == "SIMULATED_SUCCESS"
    assert first["replayed"] is False
    assert second["replayed"] is True
    assert second["idempotency_key"] == first["idempotency_key"]


def test_same_transaction_id_with_changed_payload_is_rejected():
    adapter = SandboxPaymentAdapter()

    adapter.submit(make_transaction())
    changed = adapter.submit(make_transaction(amount=1600))

    assert changed["status"] == "IDEMPOTENCY_CONFLICT"
    assert changed["outcome_uncertain"] is False


def test_uncertain_outcome_requires_reconciliation_and_is_not_retried():
    adapter = SandboxPaymentAdapter()
    transaction = make_transaction()

    first = adapter.submit(
        transaction, simulate_uncertain_outcome=True
    )
    second = adapter.submit(transaction)

    assert first["status"] == "RECONCILIATION_REQUIRED"
    assert first["outcome_uncertain"] is True
    assert second["status"] == "RECONCILIATION_REQUIRED"
    assert second["replayed"] is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": 0},
        {"amount": -10},
        {"amount": float("nan")},
        {"amount": float("inf")},
        {"sender": ""},
        {"receiver": ""},
        {"sender": "same-party", "receiver": "same-party"},
        {"asset": ""},
    ],
)
def test_invalid_transaction_is_rejected(overrides):
    with pytest.raises((ProviderAdapterError, ValueError)):
        SandboxPaymentAdapter().prepare(make_transaction(**overrides))


def test_non_sandbox_mode_is_rejected():
    with pytest.raises(ProviderAdapterError):
        SandboxPaymentAdapter(sandbox=False)


def test_adapter_has_no_saved_record_until_submit():
    adapter = SandboxPaymentAdapter()
    transaction = make_transaction()

    adapter.prepare(transaction)
    result = adapter.submit(transaction)

    assert result["status"] == "SIMULATED_SUCCESS"
    assert result["replayed"] is False


@pytest.mark.parametrize(
    "field",
    [
        "transaction_id",
        "sender",
        "receiver",
        "asset",
        "channel",
        "country",
    ],
)
def test_prepare_rejects_missing_required_transaction_fields(field):
    transaction = make_transaction()
    object.__setattr__(transaction, field, None)

    with pytest.raises((ProviderAdapterError, ValueError)):
        SandboxPaymentAdapter().prepare(transaction)
