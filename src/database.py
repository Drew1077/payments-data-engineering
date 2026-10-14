
from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

import mysql.connector
from mysql.connector import Error


def _connection_config() -> dict[str, Any]:
    """Read database connection settings from environment variables."""
    required = ("MYSQL_USER", "MYSQL_PASSWORD")

    missing = [key for key in required if key not in os.environ]
    if missing:
        raise ValueError(
            f"Missing database environment variables: {', '.join(missing)}"
        )

    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.getenv(
            "MYSQL_DATABASE", "payments_reconciliation"
        ),
        "connection_timeout": 10,
    }


def persist_reconciliation(result: dict[str, Any]) -> int:
    """Persist one reconciliation result and return its run ID."""
    summary = result["summary"]
    connection = mysql.connector.connect(**_connection_config())

    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO reconciliation_runs (
                    processor_input_rows,
                    bank_input_rows,
                    processor_valid_rows,
                    bank_valid_rows,
                    matched_count,
                    status_difference_count,
                    exception_count,
                    matched_amount_totals_by_currency,
                    exception_counts_by_type
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    summary["processor_input_rows"],
                    summary["bank_input_rows"],
                    summary["processor_valid_rows"],
                    summary["bank_valid_rows"],
                    summary["matched_count"],
                    summary["status_difference_count"],
                    summary["exception_count"],
                    json.dumps(summary["matched_amount_totals_by_currency"]),
                    json.dumps(summary["exception_counts_by_type"]),
                ),
            )
            run_id = cursor.lastrowid

            matched_rows = [
                (
                    run_id,
                    row["transaction_id"],
                    row["processor_date"],
                    row["settlement_date"],
                    Decimal(str(row["amount"])),
                    row["currency"],
                    row["processor_status"],
                    row["bank_status"],
                )
                for row in result["matched"]
            ]
            if matched_rows:
                cursor.executemany(
                    """
                    INSERT INTO matched_transactions (
                        run_id, transaction_id, processor_date,
                        settlement_date, amount, currency,
                        processor_status, bank_status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    matched_rows,
                )

            status_rows = [
                (
                    run_id,
                    row["transaction_id"],
                    row["processor_date"],
                    row["settlement_date"],
                    Decimal(str(row["amount"])),
                    row["currency"],
                    row["processor_status"],
                    row["bank_status"],
                    row["exception_type"],
                    row["reason"],
                )
                for row in result["status_differences"]
            ]
            if status_rows:
                cursor.executemany(
                    """
                    INSERT INTO status_differences (
                        run_id, transaction_id, processor_date,
                        settlement_date, amount, currency,
                        processor_status, bank_status,
                        exception_type, reason
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    status_rows,
                )

            exception_rows = [
                (
                    run_id,
                    row.get("transaction_id") or None,
                    row["source"],
                    str(row["source_row"]) if row.get("source_row") is not None else None,
                    row["exception_type"],
                    row["reason"],
                    json.dumps(row.get("record"), default=str),
                    Decimal(str(row["processor_amount"]))
                    if row.get("processor_amount") not in (None, "")
                    else None,
                    Decimal(str(row["bank_amount"]))
                    if row.get("bank_amount") not in (None, "")
                    else None,
                    row.get("processor_currency") or None,
                    row.get("bank_currency") or None,
                )
                for row in result["exceptions"]
            ]
            if exception_rows:
                cursor.executemany(
                    """
                    INSERT INTO reconciliation_exceptions (
                        run_id, transaction_id, source, source_row,
                        exception_type, reason, record_json,
                        processor_amount, bank_amount,
                        processor_currency, bank_currency
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    exception_rows,
                )

            connection.commit()
            return int(run_id)
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()
