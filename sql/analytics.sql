
-- 1. Reconciliation run overview using a CTE.
WITH run_summary AS (
    SELECT
        run_id,
        processor_input_rows,
        bank_input_rows,
        matched_count,
        status_difference_count,
        exception_count,
        created_at
    FROM reconciliation_runs
)
SELECT *
FROM run_summary
ORDER BY run_id DESC;


-- 2. Exception counts and proportions by run.
SELECT
    run_id,
    exception_type,
    COUNT(*) AS exception_count,
    ROUND(
        100.0 * COUNT(*) /
        NULLIF(SUM(COUNT(*)) OVER (PARTITION BY run_id), 0),
        2
    ) AS exception_percentage
FROM reconciliation_exceptions
GROUP BY run_id, exception_type
ORDER BY run_id, exception_count DESC, exception_type;


-- 3. Matched transaction totals by currency and run.
SELECT
    run_id,
    currency,
    COUNT(*) AS matched_transactions,
    SUM(amount) AS matched_amount
FROM matched_transactions
GROUP BY run_id, currency
ORDER BY run_id, currency;


-- 4. Compare exception counts across runs with a window function.
WITH exception_counts AS (
    SELECT
        run_id,
        exception_type,
        COUNT(*) AS exception_count
    FROM reconciliation_exceptions
    GROUP BY run_id, exception_type
)
SELECT
    run_id,
    exception_type,
    exception_count,
    LAG(exception_count) OVER (
        PARTITION BY exception_type
        ORDER BY run_id
    ) AS previous_run_count,
    exception_count - LAG(exception_count) OVER (
        PARTITION BY exception_type
        ORDER BY run_id
    ) AS change_from_previous_run
FROM exception_counts
ORDER BY exception_type, run_id;


-- 5. Join run metadata to its exceptions for investigation.
SELECT
    r.run_id,
    r.created_at,
    e.transaction_id,
    e.source,
    e.exception_type,
    e.reason,
    e.processor_amount,
    e.bank_amount,
    e.processor_currency,
    e.bank_currency
FROM reconciliation_runs AS r
INNER JOIN reconciliation_exceptions AS e
    ON e.run_id = r.run_id
ORDER BY r.run_id, e.exception_type, e.transaction_id;
