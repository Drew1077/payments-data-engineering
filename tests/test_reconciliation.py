
import pandas as pd

from src.reconciliation import reconcile_frames


def make_processor(rows):
    return pd.DataFrame(
        rows,
        columns=[
            "transaction_id",
            "transaction_date",
            "amount",
            "currency",
            "status",
        ],
    )


def make_bank(rows):
    return pd.DataFrame(
        rows,
        columns=[
            "transaction_id",
            "settlement_date",
            "amount",
            "currency",
            "status",
        ],
    )


def test_exact_financial_match_with_same_status():
    processor = make_processor(
        [["T1", "2026-09-01", "10.00", "USD", "settled"]]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "10.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert len(result["matched"]) == 1
    assert result["matched"][0]["transaction_id"] == "T1"
    assert result["exceptions"] == []
    assert result["status_differences"] == []


def test_status_difference_is_separate_from_financial_match():
    processor = make_processor(
        [["T1", "2026-09-01", "10.00", "USD", "captured"]]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "10.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert result["matched"] == []
    assert len(result["status_differences"]) == 1
    assert result["status_differences"][0]["exception_type"] == "status_difference"


def test_amount_and_currency_mismatch_are_reported():
    processor = make_processor(
        [["T1", "2026-09-01", "10.00", "USD", "settled"]]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "11.00", "EUR", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert result["matched"] == []
    assert len(result["exceptions"]) == 1
    assert (
        result["exceptions"][0]["exception_type"]
        == "amount_and_currency_mismatch"
    )
    assert "amount_mismatch" in result["exceptions"][0]["reason"]
    assert "currency_mismatch" in result["exceptions"][0]["reason"]


def test_missing_counterparts_are_reported():
    processor = make_processor(
        [["T1", "2026-09-01", "10.00", "USD", "settled"]]
    )
    bank = make_bank(
        [["T2", "2026-09-02", "20.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    exception_types = {
        (item["transaction_id"], item["exception_type"])
        for item in result["exceptions"]
    }
    assert ("T1", "missing_bank_record") in exception_types
    assert ("T2", "missing_processor_record") in exception_types


def test_duplicate_ids_are_quarantined():
    processor = make_processor(
        [
            ["T1", "2026-09-01", "10.00", "USD", "settled"],
            ["T1", "2026-09-01", "10.00", "USD", "settled"],
        ]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "10.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert result["matched"] == []
    assert sum(
        item["exception_type"] == "duplicate_id"
        for item in result["exceptions"]
    ) == 2


def test_invalid_record_is_reported_and_duplicate_is_still_detected():
    processor = make_processor(
        [
            ["T1", "2026-09-01", "10.00", "USD", "settled"],
            ["T1", "2026-09-01", "", "USD", "settled"],
        ]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "10.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert result["matched"] == []
    assert any(
        item["exception_type"] == "invalid_record"
        and "missing_amount" in item["reason"]
        for item in result["exceptions"]
    )
    assert any(
        item["exception_type"] == "duplicate_id"
        for item in result["exceptions"]
    )


def test_invalid_status_is_not_silently_accepted():
    processor = make_processor(
        [["T1", "2026-09-01", "10.00", "USD", "unknown_state"]]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "10.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert result["matched"] == []
    assert any(
        item["exception_type"] == "invalid_record"
        and "invalid_status" in item["reason"]
        for item in result["exceptions"]
    )


def test_missing_required_columns_raise_clear_error():
    processor = pd.DataFrame({"transaction_id": ["T1"]})
    bank = make_bank(
        [["T1", "2026-09-02", "10.00", "USD", "settled"]]
    )

    try:
        reconcile_frames(processor, bank)
    except ValueError as exc:
        assert "missing columns" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing columns")


def test_invalid_processor_counterpart_is_not_called_missing():
    processor = make_processor(
        [["T1", "2026-09-01", "", "USD", "settled"]]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "10.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert result["matched"] == []
    assert any(
        item["exception_type"] == "invalid_processor_record"
        and item["transaction_id"] == "T1"
        for item in result["exceptions"]
    )
    assert not any(
        item["exception_type"] == "missing_processor_record"
        and item["transaction_id"] == "T1"
        for item in result["exceptions"]
    )


def test_amount_only_mismatch_has_specific_exception_type():
    processor = make_processor(
        [["T1", "2026-09-01", "10.00", "USD", "settled"]]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "11.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert len(result["exceptions"]) == 1
    assert result["exceptions"][0]["exception_type"] == "amount_mismatch"


def test_duplicate_processor_id_takes_precedence_for_bank_counterpart():
    processor = make_processor(
        [
            ["T1", "2026-09-01", "10.00", "USD", "settled"],
            ["T1", "2026-09-01", "10.00", "USD", "settled"],
        ]
    )
    bank = make_bank(
        [["T1", "2026-09-02", "10.00", "USD", "settled"]]
    )

    result = reconcile_frames(processor, bank)

    assert result["matched"] == []
    assert any(
        item["exception_type"] == "duplicate_processor_id"
        and item["transaction_id"] == "T1"
        for item in result["exceptions"]
    )
    assert not any(
        item["exception_type"] == "missing_processor_record"
        and item["transaction_id"] == "T1"
        for item in result["exceptions"]
    )
