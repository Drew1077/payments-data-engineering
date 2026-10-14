
# Payments Data Engineering & Reconciliation Pipeline

A Python, pandas, MySQL, and SQL project that reconciles payment processor transactions against bank settlements, identifies discrepancies, and persists auditable reconciliation results.

## Project objectives

- Ingest processor and bank settlement CSV files.
- Validate required fields, amounts, dates, currencies, and statuses.
- Identify duplicate IDs, missing transactions, amount mismatches, currency mismatches, and status differences.
- Preserve exception reasons for investigation.
- Export reconciliation results as CSV and JSON.
- Persist reconciliation runs and their results in MySQL.
- Analyse exceptions and matched transactions using SQL.
- Run automated tests and Python syntax checks in GitLab CI.

## Technology stack

- Python 3.12
- pandas
- MySQL 8.0
- mysql-connector-python
- pytest
- GitLab CI/CD

## Project structure

```text
data/
  raw/                 Synthetic input CSV files
  processed/           Generated reconciliation outputs
docs/
  reconciliation_rules.txt
reports/
sql/
  schema.sql
  analytics.sql
src/
  reconciliation.py
  database.py
tests/
  test_reconciliation.py
.gitlab-ci.yml
requirements.txt
```

## Setup

Create and activate a Python virtual environment, then install dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Ensure MySQL 8.0 is running.

## Database setup

Execute the schema from PowerShell:

```powershell
Get-Content .\sql\schema.sql -Raw | mysql -u root -p
```

The schema creates the dedicated `payments_reconciliation` database and four tables:

- `reconciliation_runs`
- `matched_transactions`
- `status_differences`
- `reconciliation_exceptions`

Create a dedicated application user and grant it only the permissions required by the application. Do not put database passwords in source code or commit credentials to version control.

## Configure database credentials

Set credentials in your current PowerShell session:

```powershell
$env:MYSQL_USER = "payments_app"
$secure = Read-Host "Enter database password" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:MYSQL_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
```

Optional connection settings default to `127.0.0.1:3306` and the `payments_reconciliation` database. Override them with `MYSQL_HOST`, `MYSQL_PORT`, and `MYSQL_DATABASE` if needed.

These credentials remain available only in the current terminal session.

## Run reconciliation

From the project root:

```powershell
python -c "from src.reconciliation import run_reconciliation; print(run_reconciliation('data/raw/processor_transactions.csv', 'data/raw/bank_settlements.csv', 'data/processed')['summary'])"
```

The pipeline generates:

- `data/processed/matched.csv`
- `data/processed/status_differences.csv`
- `data/processed/exceptions.csv`
- `data/processed/summary.json`

## Persist results to MySQL

After configuring database credentials, run:

```powershell
python -c "from src.reconciliation import run_reconciliation; from src.database import persist_reconciliation; result = run_reconciliation('data/raw/processor_transactions.csv', 'data/raw/bank_settlements.csv', 'data/processed'); print('Persisted run ID:', persist_reconciliation(result))"
```

Each successful persistence operation creates a new reconciliation run and associates its detail records with that run ID.

## Run tests

```powershell
python -m pytest -q
```

Check Python syntax:

```powershell
python -m py_compile .\src\reconciliation.py .\src\database.py
```

## SQL analytics

Execute the included analytics queries:

```powershell
Get-Content .\sql\analytics.sql -Raw | mysql -u root -p -D payments_reconciliation
```

The queries demonstrate:

- Common table expressions (CTEs)
- Joins
- Aggregations by exception type and currency
- Window functions using `LAG()`
- Exception percentages and run-to-run comparisons

## Reconciliation principles

- Duplicate IDs are not arbitrarily matched.
- Financial matching requires a unique transaction ID, equal decimal amounts, and matching currencies.
- Status differences are reported separately when financial fields match.
- Invalid records and unmatched transactions are retained as explicit exceptions.
- Synthetic inputs are deterministic so tests can verify expected outcomes.

## Scope and limitations

This project demonstrates reconciliation logic, relational data modelling, SQL analytics, automated testing, and a CI configuration. The included CI job runs syntax checks and pytest; it does not establish that a live MySQL integration test has passed in GitLab.

The dataset is synthetic and intended for demonstration, not for production payment processing.
