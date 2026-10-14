
CREATE DATABASE IF NOT EXISTS payments_reconciliation;

USE payments_reconciliation;

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    run_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    processor_input_rows INT NOT NULL,
    bank_input_rows INT NOT NULL,
    processor_valid_rows INT NOT NULL,
    bank_valid_rows INT NOT NULL,
    matched_count INT NOT NULL,
    status_difference_count INT NOT NULL,
    exception_count INT NOT NULL,
    matched_amount_totals_by_currency JSON NOT NULL,
    exception_counts_by_type JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matched_transactions (
    run_id BIGINT NOT NULL,
    transaction_id VARCHAR(100) NOT NULL,
    processor_date DATE NOT NULL,
    settlement_date DATE NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    processor_status VARCHAR(30) NOT NULL,
    bank_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (run_id, transaction_id),
    CONSTRAINT fk_matched_run
        FOREIGN KEY (run_id)
        REFERENCES reconciliation_runs(run_id)
);

CREATE TABLE IF NOT EXISTS status_differences (
    run_id BIGINT NOT NULL,
    transaction_id VARCHAR(100) NOT NULL,
    processor_date DATE NOT NULL,
    settlement_date DATE NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    processor_status VARCHAR(30) NOT NULL,
    bank_status VARCHAR(30) NOT NULL,
    exception_type VARCHAR(50) NOT NULL,
    reason VARCHAR(255) NOT NULL,
    PRIMARY KEY (run_id, transaction_id),
    CONSTRAINT fk_status_run
        FOREIGN KEY (run_id)
        REFERENCES reconciliation_runs(run_id)
);

CREATE TABLE IF NOT EXISTS reconciliation_exceptions (
    exception_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    transaction_id VARCHAR(100),
    source VARCHAR(30) NOT NULL,
    source_row VARCHAR(30),
    exception_type VARCHAR(60) NOT NULL,
    reason VARCHAR(255) NOT NULL,
    record_json JSON,
    processor_amount DECIMAL(18, 2),
    bank_amount DECIMAL(18, 2),
    processor_currency CHAR(3),
    bank_currency CHAR(3),
    CONSTRAINT fk_exception_run
        FOREIGN KEY (run_id)
        REFERENCES reconciliation_runs(run_id),
    INDEX idx_exception_run_type (run_id, exception_type),
    INDEX idx_exception_transaction (transaction_id)
);
