"""Tests for the time-aware customer risk engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from payment_tracking_agent.models.payment import EntryDetailRecord, PaymentStatus
from payment_tracking_agent.risk.engine import compute_customer_risk, _compute_signals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=timezone.utc)


def _entry(
    customer_id: str,
    status: PaymentStatus = PaymentStatus.WITH_BENEFICIARY_BANK_PENDING,
    trace: str = "000000000000001",
) -> EntryDetailRecord:
    return EntryDetailRecord(
        transaction_code="22",
        receiving_dfi="12345678",
        check_digit="9",
        dfi_account_number_masked="****1234",
        amount_cents=10000,
        amount=100.0,
        individual_id_number=customer_id,
        individual_name="Test Customer",
        trace_number=trace,
        addenda_indicator="0",
        batch_number="1",
        sec_code="CCD",
        status=status,
        business_status=status.business_status,
    )


def _h(customer_id: str, status: PaymentStatus, days_ago: float = 0.0, trace: str = "T001") -> tuple[EntryDetailRecord, datetime]:
    """Return (entry, timestamp) with the timestamp offset by *days_ago* from now."""
    ts = _NOW - timedelta(days=days_ago)
    return _entry(customer_id, status, trace), ts


# ---------------------------------------------------------------------------
# No history
# ---------------------------------------------------------------------------

def test_no_history_returns_low() -> None:
    level, reason = compute_customer_risk("CUST-99", [])
    assert level == "LOW"
    assert "No payment history" in reason


# ---------------------------------------------------------------------------
# Single clean payment
# ---------------------------------------------------------------------------

def test_single_clean_payment_is_low() -> None:
    history = [_h("CUST-01", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 5.0, "T001")]
    level, _ = compute_customer_risk("CUST-01", history)
    assert level == "LOW"


# ---------------------------------------------------------------------------
# MEDIUM triggers
# ---------------------------------------------------------------------------

def test_one_recent_return_triggers_medium() -> None:
    history = [
        _h("CUST-02", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 10.0, "T001"),
        _h("CUST-02", PaymentStatus.REJECTED_BY_RETURN_FILE, 2.0, "T002"),  # 2 days ago
    ]
    level, reason = compute_customer_risk("CUST-02", history)
    assert level == "MEDIUM"
    assert "return" in reason.lower()


def test_rejection_rate_20pct_triggers_medium() -> None:
    # 1 rejected out of 5 = 20 %
    history = [
        _h("CUST-03", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, float(i), f"T{i:03d}")
        for i in range(4)
    ] + [_h("CUST-03", PaymentStatus.REJECTED_BY_SETTLEMENT, 50.0, "T004")]
    level, _ = compute_customer_risk("CUST-03", history)
    assert level == "MEDIUM"


# ---------------------------------------------------------------------------
# HIGH triggers
# ---------------------------------------------------------------------------

def test_two_returns_triggers_high() -> None:
    history = [
        _h("CUST-04", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 30.0, "T001"),
        _h("CUST-04", PaymentStatus.REJECTED_BY_RETURN_FILE, 20.0, "T002"),
        _h("CUST-04", PaymentStatus.REJECTED_BY_RETURN_FILE, 5.0, "T003"),
    ]
    level, reason = compute_customer_risk("CUST-04", history)
    assert level == "HIGH"


def test_rejection_rate_50pct_triggers_high() -> None:
    # 2 rejected out of 4 = 50 %
    history = [
        _h("CUST-05", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 60.0, "T001"),
        _h("CUST-05", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 55.0, "T002"),
        _h("CUST-05", PaymentStatus.WITH_BANK_VALIDATION_FAILED, 45.0, "T003"),
        _h("CUST-05", PaymentStatus.REJECTED_BY_SETTLEMENT, 10.0, "T004"),
    ]
    level, _ = compute_customer_risk("CUST-05", history)
    assert level == "HIGH"


def test_two_rejections_in_30_days_triggers_high() -> None:
    # Even with only 2/5 = 40 % rate, velocity in last 30 days is 2 → HIGH
    history = [
        _h("CUST-06", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 90.0, "T001"),
        _h("CUST-06", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 80.0, "T002"),
        _h("CUST-06", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 70.0, "T003"),
        _h("CUST-06", PaymentStatus.REJECTED_BY_RETURN_FILE, 10.0, "T004"),
        _h("CUST-06", PaymentStatus.REJECTED_BY_RETURN_FILE, 5.0, "T005"),
    ]
    level, _ = compute_customer_risk("CUST-06", history)
    assert level == "HIGH"


# ---------------------------------------------------------------------------
# Cross-customer isolation
# ---------------------------------------------------------------------------

def test_other_customers_do_not_affect_result() -> None:
    history = [
        _h("CUST-A", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 1.0, "T001"),
        # CUST-B has many returns — must NOT affect CUST-A
        _h("CUST-B", PaymentStatus.REJECTED_BY_RETURN_FILE, 2.0, "T002"),
        _h("CUST-B", PaymentStatus.REJECTED_BY_RETURN_FILE, 3.0, "T003"),
        _h("CUST-B", PaymentStatus.REJECTED_BY_RETURN_FILE, 4.0, "T004"),
    ]
    level_a, _ = compute_customer_risk("CUST-A", history)
    level_b, _ = compute_customer_risk("CUST-B", history)
    assert level_a == "LOW"
    assert level_b == "HIGH"


# ---------------------------------------------------------------------------
# Inter-rejection gap computation
# ---------------------------------------------------------------------------

def test_inter_rejection_gaps_computed_correctly() -> None:
    history = [
        _h("CUST-G", PaymentStatus.REJECTED_BY_RETURN_FILE, 20.0, "T001"),
        _h("CUST-G", PaymentStatus.REJECTED_BY_RETURN_FILE, 10.0, "T002"),  # 10 days later
        _h("CUST-G", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, 5.0, "T003"),
    ]
    signals = _compute_signals("CUST-G", history)
    assert len(signals.inter_rejection_gaps_days) == 1
    # The gap should be approximately 10 days (between days_ago=20 and days_ago=10)
    assert 9.5 <= signals.inter_rejection_gaps_days[0] <= 10.5


# ---------------------------------------------------------------------------
# Rate just below 20 % stays LOW
# ---------------------------------------------------------------------------

def test_just_below_20pct_no_returns_is_low() -> None:
    # 1 validation failure out of 6 ≈ 16.7 %, no returns
    history = [
        _h("CUST-H", PaymentStatus.WITH_BENEFICIARY_BANK_PENDING, float(i), f"T{i:03d}")
        for i in range(5)
    ] + [_h("CUST-H", PaymentStatus.WITH_BANK_VALIDATION_FAILED, 200.0, "T005")]
    level, _ = compute_customer_risk("CUST-H", history)
    assert level == "LOW"

