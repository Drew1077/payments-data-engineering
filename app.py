from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from src.reconciliation import run_reconciliation


ROOT = Path(__file__).resolve().parent
PROCESSOR_SAMPLE = ROOT / "data" / "raw" / "processor_transactions.csv"
BANK_SAMPLE = ROOT / "data" / "raw" / "bank_settlements.csv"

PROCESSOR_COLUMNS = {
    "transaction_id", "transaction_date", "amount", "currency", "status"
}
BANK_COLUMNS = {
    "transaction_id", "settlement_date", "amount", "currency", "status"
}

st.set_page_config(
    page_title="PayRecon | Payment Reconciliation",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: #0b1220; color: #e5edf7; }
    [data-testid="stSidebar"] { background: #111c2e; }
    [data-testid="stMetric"] {
        background: #142238;
        border: 1px solid #263b56;
        padding: 18px;
        border-radius: 12px;
    }
    [data-testid="stMetricLabel"] { color: #a9bad0; }
    [data-testid="stMetricValue"] { color: #f2f7ff; }
    .hero {
        background: linear-gradient(120deg, #142b43, #123c43);
        border: 1px solid #28505b;
        border-radius: 16px;
        padding: 25px 28px;
        margin-bottom: 20px;
    }
    .hero h1 { margin: 0; color: #f2f7ff; font-size: 2rem; }
    .hero p { margin: 8px 0 0; color: #bdd0df; }
    .eyebrow {
        color: #63e6c2;
        text-transform: uppercase;
        letter-spacing: 2px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    h2, h3 { color: #e5edf7; }
    div[data-testid="stDataFrame"] {
        border: 1px solid #263b56;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Payments data engineering</div>
      <h1>PayRecon</h1>
      <p>Payment reconciliation workspace · Detect discrepancies · Explore exceptions · Export results</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 💳 PayRecon")
    st.caption("Reconciliation workspace")
    source_mode = st.radio(
        "Data source",
        ["Use sample data", "Upload CSV files"],
        help="Sample data is included with this project. Uploaded files are processed temporarily.",
    )
    st.divider()
    st.markdown("### Required fields")
    st.caption("Processor: transaction_id, transaction_date, amount, currency, status")
    st.caption("Bank: transaction_id, settlement_date, amount, currency, status")
    st.divider()
    st.caption("Built with Python · pandas · MySQL · Streamlit")


def validate_upload(uploaded_file, required_columns: set[str]) -> str | None:
    try:
        frame = pd.read_csv(io.BytesIO(uploaded_file.getvalue()), dtype=str)
    except Exception as exc:
        return f"Could not read {uploaded_file.name}: {exc}"

    missing = required_columns - set(frame.columns)
    if missing:
        return f"{uploaded_file.name} is missing required columns: {', '.join(sorted(missing))}"
    return None


processor_upload = None
bank_upload = None

if source_mode == "Upload CSV files":
    upload_col1, upload_col2 = st.columns(2)
    with upload_col1:
        processor_upload = st.file_uploader(
            "Processor transactions CSV",
            type=["csv"],
            key="processor_upload",
        )
    with upload_col2:
        bank_upload = st.file_uploader(
            "Bank settlements CSV",
            type=["csv"],
            key="bank_upload",
        )

    if processor_upload is not None:
        error = validate_upload(processor_upload, PROCESSOR_COLUMNS)
        if error:
            st.error(error)
    if bank_upload is not None:
        error = validate_upload(bank_upload, BANK_COLUMNS)
        if error:
            st.error(error)

can_run = (
    source_mode == "Use sample data"
    or (processor_upload is not None and bank_upload is not None)
)

st.markdown("### Run reconciliation")
st.write(
    "Compare processor transactions with bank settlements using the project's existing reconciliation engine."
)

if st.button(
    "▶  Run reconciliation",
    type="primary",
    disabled=not can_run,
    width="content",
):
    try:
        with st.spinner("Validating records and comparing transactions..."):
            if source_mode == "Use sample data":
                if not PROCESSOR_SAMPLE.exists() or not BANK_SAMPLE.exists():
                    st.error("Sample CSV files were not found in data/raw/.")
                    st.stop()

                result = run_reconciliation(
                    PROCESSOR_SAMPLE,
                    BANK_SAMPLE,
                    ROOT / "data" / "processed",
                )
            else:
                processor_error = validate_upload(processor_upload, PROCESSOR_COLUMNS)
                bank_error = validate_upload(bank_upload, BANK_COLUMNS)
                if processor_error or bank_error:
                    if processor_error:
                        st.error(processor_error)
                    if bank_error:
                        st.error(bank_error)
                    st.stop()

                with tempfile.TemporaryDirectory(prefix="payrecon_") as temp_dir:
                    temp_path = Path(temp_dir)
                    processor_path = temp_path / "processor_transactions.csv"
                    bank_path = temp_path / "bank_settlements.csv"

                    processor_path.write_bytes(processor_upload.getvalue())
                    bank_path.write_bytes(bank_upload.getvalue())

                    result = run_reconciliation(
                        processor_path,
                        bank_path,
                        temp_path / "processed",
                    )

            st.session_state["reconciliation_result"] = result
            st.session_state["reconciliation_source"] = source_mode
            st.success("Reconciliation completed successfully.")
    except Exception as exc:
        st.error(f"Reconciliation failed: {exc}")

result = st.session_state.get("reconciliation_result")

if result is None:
    st.info(
        "Choose a data source, then select **Run reconciliation** to view the results."
    )
    st.markdown("### What this dashboard checks")
    intro_cols = st.columns(3)
    intro_cols[0].markdown("**Transaction matching**\n\nFinds records that match across both sources.")
    intro_cols[1].markdown("**Exception detection**\n\nFlags duplicates, missing records and financial mismatches.")
    intro_cols[2].markdown("**Audit-friendly outputs**\n\nExplore results and download reports for further analysis.")
    st.stop()

summary = result["summary"]
matched_df = pd.DataFrame(result["matched"])
status_df = pd.DataFrame(result["status_differences"])
exceptions_df = pd.DataFrame(result["exceptions"])
for display_df in (matched_df, status_df, exceptions_df):
    if "source_row" in display_df.columns:
        display_df["source_row"] = display_df["source_row"].map(lambda value: "" if pd.isna(value) else str(value))

processor_rows = summary["processor_input_rows"]
bank_rows = summary["bank_input_rows"]
matched_count = summary["matched_count"]
status_count = summary["status_difference_count"]
exception_count = summary["exception_count"]
match_rate = (matched_count / processor_rows * 100) if processor_rows else 0.0

st.markdown("## Reconciliation overview")
st.caption(
    f"Data source: {st.session_state.get('reconciliation_source', 'Unknown')} · "
    f"{processor_rows:,} processor rows · {bank_rows:,} bank rows"
)

metric_cols = st.columns(4)
metric_cols[0].metric("Processor rows", f"{processor_rows:,}")
metric_cols[1].metric("Matched transactions", f"{matched_count:,}")
metric_cols[2].metric("Status differences", f"{status_count:,}")
metric_cols[3].metric("Exceptions", f"{exception_count:,}")

rate_col, amount_col = st.columns(2)
with rate_col:
    st.metric("Match rate", f"{match_rate:.1f}%", help="Matched count divided by processor input rows.")
with amount_col:
    st.markdown("**Matched amount totals by currency**")
    totals = summary["matched_amount_totals_by_currency"]
    if totals:
        st.dataframe(
            pd.DataFrame(
                [{"Currency": currency, "Matched amount": amount} for currency, amount in totals.items()]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("No matched transaction amounts to summarize.")

st.divider()
st.markdown("## Exception analysis")

chart_col, detail_col = st.columns([1, 1.4])
with chart_col:
    st.markdown("#### Exceptions by type")
    exception_counts = summary["exception_counts_by_type"]
    if exception_counts:
        chart_df = pd.DataFrame(
            [{"Exception type": key, "Count": value} for key, value in exception_counts.items()]
        ).set_index("Exception type")
        st.bar_chart(chart_df, horizontal=True)
    else:
        st.success("No exceptions detected.")

with detail_col:
    st.markdown("#### Exception details")
    if not exceptions_df.empty:
        available_types = sorted(exceptions_df["exception_type"].dropna().unique().tolist())
        selected_types = st.multiselect(
            "Filter by exception type",
            options=available_types,
            default=available_types,
        )
        filtered_exceptions = exceptions_df[
            exceptions_df["exception_type"].isin(selected_types)
        ]
        st.dataframe(filtered_exceptions, hide_index=True, width="stretch")
        st.download_button(
            "Download filtered exceptions CSV",
            data=filtered_exceptions.to_csv(index=False).encode("utf-8"),
            file_name="exceptions.csv",
            mime="text/csv",
        )
    else:
        st.success("No exceptions to display.")

st.divider()
st.markdown("## Transaction explorer")

matched_tab, status_tab, exceptions_tab = st.tabs(
    ["Matched transactions", "Status differences", "All exceptions"]
)

with matched_tab:
    st.caption(f"{len(matched_df):,} matched transactions")
    if not matched_df.empty:
        st.dataframe(matched_df, hide_index=True, width="stretch")
    else:
        st.info("No matched transactions in this run.")
    st.download_button(
        "Download matched CSV",
        data=matched_df.to_csv(index=False).encode("utf-8"),
        file_name="matched.csv",
        mime="text/csv",
    )

with status_tab:
    st.caption(f"{len(status_df):,} status differences")
    if not status_df.empty:
        st.dataframe(status_df, hide_index=True, width="stretch")
    else:
        st.info("No status differences in this run.")
    st.download_button(
        "Download status differences CSV",
        data=status_df.to_csv(index=False).encode("utf-8"),
        file_name="status_differences.csv",
        mime="text/csv",
    )

with exceptions_tab:
    st.caption(f"{len(exceptions_df):,} exceptions")
    if not exceptions_df.empty:
        st.dataframe(exceptions_df, hide_index=True, width="stretch")
    else:
        st.info("No exceptions in this run.")
    st.download_button(
        "Download all exceptions CSV",
        data=exceptions_df.to_csv(index=False).encode("utf-8"),
        file_name="exceptions.csv",
        mime="text/csv",
    )

st.divider()
st.markdown("## Run summary")
st.json(summary)
st.download_button(
    "Download summary JSON",
    data=json.dumps(summary, indent=2).encode("utf-8"),
    file_name="summary.json",
    mime="application/json",
)

st.caption(
    "This demo uses synthetic or user-supplied CSV data. It does not connect to a live payment processor or bank. "
    "Uploaded files are processed in temporary storage and are not automatically persisted to MySQL."
)
