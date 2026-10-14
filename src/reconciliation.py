
from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd


PROCESSOR_COLUMNS = {
    "transaction_id",
    "transaction_date",
    "amount",
    "currency",
    "status",
}
BANK_COLUMNS = {
    "transaction_id",
    "settlement_date",
    "amount",
    "currency",
    "status",
}
VALID_STATUSES = {"captured", "settled", "failed", "refunded"}
VALID_CURRENCIES = {"USD", "EUR", "GBP", "INR"}


def _validate_source(
    frame: pd.DataFrame, source: str, date_column: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    required = PROCESSOR_COLUMNS if source == "processor" else BANK_COLUMNS
    missing_columns = required - set(frame.columns)

    if missing_columns:
        raise ValueError(
            f"{source} input is missing columns: {sorted(missing_columns)}"
        )

    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []

    for row_number, row in enumerate(frame.to_dict("records"), start=2):
        record = dict(row)
        record["source"] = source
        record["source_row"] = row_number
        issues: list[str] = []

        transaction_id = record.get("transaction_id")
        if pd.isna(transaction_id) or not str(transaction_id).strip():
            issues.append("missing_transaction_id")
        else:
            record["transaction_id"] = str(transaction_id).strip()

        date_value = record.get(date_column)
        if pd.isna(date_value) or not str(date_value).strip():
            issues.append("missing_date")
        else:
            parsed_date = pd.to_datetime(date_value, errors="coerce")
            if pd.isna(parsed_date):
                issues.append("invalid_date")
            else:
                record[date_column] = parsed_date.date().isoformat()

        amount_value = record.get("amount")
        if pd.isna(amount_value) or not str(amount_value).strip():
            issues.append("missing_amount")
        else:
            try:
                amount = Decimal(str(amount_value).strip())
                if not amount.is_finite() or amount < 0:
                    issues.append("invalid_amount")
                else:
                    record["amount"] = format(amount, "f")
            except (InvalidOperation, ValueError):
                issues.append("invalid_amount")

        currency_value = record.get("currency")
        currency = "" if pd.isna(currency_value) else str(currency_value).strip().upper()
        if currency not in VALID_CURRENCIES:
            issues.append("invalid_currency")
        record["currency"] = currency

        status_value = record.get("status")
        status = "" if pd.isna(status_value) else str(status_value).strip().lower()
        if status not in VALID_STATUSES:
            issues.append("invalid_status")
        record["status"] = status

        if issues:
            invalid.append(
                {
                    "transaction_id": record.get("transaction_id", ""),
                    "source": source,
                    "source_row": row_number,
                    "exception_type": "invalid_record",
                    "reason": ";".join(issues),
                    "record": json.dumps(
                        {key: str(value) for key, value in row.items()},
                        sort_keys=True,
                    ),
                }
            )
        else:
            valid.append(record)

    return valid, invalid


def reconcile_frames(
    processor_frame: pd.DataFrame,
    bank_frame: pd.DataFrame,
) -> dict[str, Any]:
    processor, processor_invalid = _validate_source(
        processor_frame, "processor", "transaction_date"
    )
    bank, bank_invalid = _validate_source(
        bank_frame, "bank", "settlement_date"
    )

    exceptions: list[dict[str, Any]] = processor_invalid + bank_invalid
    matched: list[dict[str, Any]] = []
    status_differences: list[dict[str, Any]] = []

    processor_counts = Counter(
        str(value).strip()
        for value in processor_frame["transaction_id"].dropna()
        if str(value).strip()
    )
    bank_counts = Counter(
        str(value).strip()
        for value in bank_frame["transaction_id"].dropna()
        if str(value).strip()
    )

    duplicate_processor = {
        transaction_id
        for transaction_id, count in processor_counts.items()
        if count > 1
    }
    duplicate_bank = {
        transaction_id
        for transaction_id, count in bank_counts.items()
        if count > 1
    }

    for source_name, rows, duplicates in (
        ("processor", processor, duplicate_processor),
        ("bank", bank, duplicate_bank),
    ):
        for row in rows:
            if row["transaction_id"] in duplicates:
                exceptions.append(
                    {
                        "transaction_id": row["transaction_id"],
                        "source": source_name,
                        "source_row": row["source_row"],
                        "exception_type": "duplicate_id",
                        "reason": f"duplicate transaction ID in {source_name}",
                        "record": json.dumps(
                            {key: str(value) for key, value in row.items()},
                            sort_keys=True,
                        ),
                    }
                )

    processor_by_id = {
        row["transaction_id"]: row
        for row in processor
        if row["transaction_id"] not in duplicate_processor
    }
    bank_by_id = {
        row["transaction_id"]: row
        for row in bank
        if row["transaction_id"] not in duplicate_bank
    }

    processor_ids = set(processor_by_id)
    bank_ids = set(bank_by_id)

    for transaction_id in sorted(processor_ids | bank_ids):
        processor_row = processor_by_id.get(transaction_id)
        bank_row = bank_by_id.get(transaction_id)

        if processor_row is None:
            exceptions.append(
                {
                    "transaction_id": transaction_id,
                    "source": "bank",
                    "source_row": bank_row["source_row"],
                    "exception_type": (
                        "duplicate_processor_id"
                        if transaction_id in duplicate_processor
                        else (
                            "invalid_processor_record"
                            if transaction_id in {
                                str(value).strip()
                                for value in processor_frame["transaction_id"].dropna()
                                if str(value).strip()
                            }
                            else "missing_processor_record"
                        )
                    ),
                    "reason": (
                        "processor transaction ID is duplicated and cannot be uniquely matched"
                        if transaction_id in duplicate_processor
                        else (
                            "processor record exists but failed validation"
                            if transaction_id in {
                                str(value).strip()
                                for value in processor_frame["transaction_id"].dropna()
                                if str(value).strip()
                            }
                            else "transaction exists in bank but not processor"
                        )
                    ),
                    "record": json.dumps(bank_row, sort_keys=True),
                }
            )
            continue

        if bank_row is None:
            exceptions.append(
                {
                    "transaction_id": transaction_id,
                    "source": "processor",
                    "source_row": processor_row["source_row"],
                    "exception_type": "missing_bank_record",
                    "reason": "transaction exists in processor but not bank",
                    "record": json.dumps(processor_row, sort_keys=True),
                }
            )
            continue

        processor_amount = Decimal(processor_row["amount"])
        bank_amount = Decimal(bank_row["amount"])
        mismatch_reasons: list[str] = []

        if processor_amount != bank_amount:
            mismatch_reasons.append("amount_mismatch")
        if processor_row["currency"] != bank_row["currency"]:
            mismatch_reasons.append("currency_mismatch")

        if mismatch_reasons:
            exceptions.append(
                {
                    "transaction_id": transaction_id,
                    "source": "both",
                    "source_row": "",
                    "exception_type": (
                        "amount_and_currency_mismatch"
                        if len(mismatch_reasons) == 2
                        else mismatch_reasons[0]
                    ),
                    "reason": ";".join(mismatch_reasons),
                    "processor_amount": processor_row["amount"],
                    "bank_amount": bank_row["amount"],
                    "processor_currency": processor_row["currency"],
                    "bank_currency": bank_row["currency"],
                    "record": json.dumps(
                        {"processor": processor_row, "bank": bank_row},
                        sort_keys=True,
                    ),
                }
            )
            continue

        comparison = {
            "transaction_id": transaction_id,
            "processor_date": processor_row["transaction_date"],
            "settlement_date": bank_row["settlement_date"],
            "amount": processor_row["amount"],
            "currency": processor_row["currency"],
            "processor_status": processor_row["status"],
            "bank_status": bank_row["status"],
        }

        if processor_row["status"] != bank_row["status"]:
            status_differences.append(
                {
                    **comparison,
                    "exception_type": "status_difference",
                    "reason": "financial fields match but statuses differ",
                }
            )
        else:
            matched.append(comparison)

    summary = {
        "processor_input_rows": len(processor_frame),
        "bank_input_rows": len(bank_frame),
        "processor_valid_rows": len(processor),
        "bank_valid_rows": len(bank),
        "matched_count": len(matched),
        "status_difference_count": len(status_differences),
        "exception_count": len(exceptions),
        "exception_counts_by_type": dict(
            sorted(Counter(row["exception_type"] for row in exceptions).items())
        ),
        "matched_amount_totals_by_currency": {},
    }

    totals: dict[str, Decimal] = {}
    for row in matched:
        currency = row["currency"]
        totals[currency] = totals.get(currency, Decimal("0")) + Decimal(row["amount"])

    summary["matched_amount_totals_by_currency"] = {
        currency: format(amount, "f")
        for currency, amount in sorted(totals.items())
    }

    return {
        "matched": matched,
        "status_differences": status_differences,
        "exceptions": exceptions,
        "summary": summary,
    }


def run_reconciliation(
    processor_path: str | Path,
    bank_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    processor_frame = pd.read_csv(processor_path, dtype=str, keep_default_na=True)
    bank_frame = pd.read_csv(bank_path, dtype=str, keep_default_na=True)

    result = reconcile_frames(processor_frame, bank_frame)

    pd.DataFrame(result["matched"]).to_csv(output / "matched.csv", index=False)
    pd.DataFrame(result["status_differences"]).to_csv(
        output / "status_differences.csv", index=False
    )
    pd.DataFrame(result["exceptions"]).to_csv(
        output / "exceptions.csv", index=False
    )
    (output / "summary.json").write_text(
        json.dumps(result["summary"], indent=2) + "\n",
        encoding="utf-8",
    )

    return result
