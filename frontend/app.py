"""Run from the repo root: python -m streamlit run frontend/app.py."""

import math
from pathlib import Path

import pandas as pd
import streamlit as st

from frontend.api_client import APIClient, APIClientError
from frontend.charts import build_chart
from frontend.config import FrontendSettings
from frontend.session import (
    MAX_HISTORY, clear_dataset, initialize_session, load_dataset, refresh_dataset, reset_conversation, submit_question,
)


def display_columns(names: list[str]) -> list[str]:
    """Keep duplicate SQL output labels readable and Arrow-compatible."""
    used: dict[str, int] = {}
    result = []
    for name in names:
        used[name] = used.get(name, 0) + 1
        label = name if used[name] == 1 else f"{name} ({used[name]})"
        while label in result:
            label += " (duplicate)"
        result.append(label)
    return result



def display_frame(rows: list, columns: list[str]) -> pd.DataFrame:
    """Keep nullable integers exact and make oversized/mixed values Arrow-safe."""
    frame = pd.DataFrame(rows, columns=columns, dtype=object)
    for name in columns:
        values = frame[name].tolist()
        types = {type(value) for value in values if value is not None}
        oversized = any(type(value) is int and abs(value) > 2**53 - 1 for value in values)
        mixed = len(types) > 1 and not types <= {int, float}
        if oversized or mixed:
            frame[name] = pd.Series([None if value is None else str(value) for value in values], dtype=object)
    return frame

def render_overview(info: dict) -> None:
    st.subheader("Dataset overview")
    left, middle, right = st.columns(3)
    left.metric("Rows", f'{info["row_count"]:,}')
    middle.metric("Columns", f'{info["column_count"]:,}')
    right.metric("Missing cells", f'{sum(info["missing_values"].values()):,}')
    names = info["columns"][:100]
    preview, schema, statistics = st.tabs(["Preview", "Columns & missing values", "Statistics"])
    with preview:
        st.dataframe(display_frame(info["preview"], names), hide_index=True, width="stretch")
        st.caption("A small preview of the validated dataset.")
    with schema:
        st.dataframe(pd.DataFrame({
            "Column": names, "Type": [info["dtypes"].get(name, "unknown") for name in names],
            "Missing": [info["missing_values"].get(name, 0) for name in names],
        }), hide_index=True, width="stretch")
    with statistics:
        values = {name: {key: "—" if value is None else str(value) for key, value in info["statistics"].get(name, {}).items()} for name in names}
        st.dataframe(pd.DataFrame.from_dict(values, orient="index"), width="stretch")
    if len(info["columns"]) > 100:
        st.caption("The overview shows the first 100 columns for readability.")


def render_analysis(entry: dict, index: int) -> None:
    with st.chat_message("user"):
        st.write(entry["question"])
    with st.chat_message("assistant"):
        if entry["error"]:
            st.error(entry["error"])
            return
        response = entry["response"]
        st.write(response["answer"])
        if response["rows"]:
            chart = build_chart(response["columns"], response["rows"])
            if chart.figure is not None:
                st.plotly_chart(chart.figure, width="stretch", key=f"chart_{index}", config={"displaylogo": False})
                if chart.excluded_rows:
                    st.caption(f"Chart excludes {chart.excluded_rows} incomplete row(s). The result table retains them.")
                if chart.kind == "line" and any(value is None for row in response["rows"] for value in row):
                    st.caption("Missing measures remain gaps in the time series.")
            else:
                st.caption(chart.reason)
            st.dataframe(display_frame(response["rows"][:200], display_columns(response["columns"])), hide_index=True, width="stretch")
            st.caption(f'{response["row_count"]:,} result row(s). Results may be bounded by the backend query limit.')
            if response["row_count"] > 200:
                st.caption("Only the first 200 rows are displayed.")
        else:
            st.caption("No result table was returned for this question.")
        with st.expander("SQL & tool details"):
            if response["sql"]:
                st.code(response["sql"], language="sql")
            else:
                st.caption("No SQL was executed.")
            st.caption("Tools used: " + (", ".join(response["tools_used"]) or "None"))


def main() -> None:
    st.set_page_config(page_title="Agentic AI Data Analyst", page_icon="📊", layout="wide")
    initialize_session(st.session_state)
    try:
        settings = FrontendSettings.from_environment()
    except ValueError:
        st.error("Frontend configuration is invalid. Check the backend address, timeouts, and upload limit.")
        st.stop()
    api = APIClient(settings)
    with st.sidebar:
        st.title("Your dataset")
        st.caption(f"UTF-8 CSV · up to {settings.max_upload_bytes / (1024 * 1024):g} MiB")
        uploaded = st.file_uploader("Choose a CSV", type=["csv"], max_upload_size=math.ceil(settings.max_upload_bytes / (1024 * 1024)), key="csv_upload")
        load_clicked = st.button("Load dataset", type="primary", width="stretch", disabled=uploaded is None)
        sample_clicked = st.button("Try the retail sample", width="stretch")
        if load_clicked or sample_clicked:
            try:
                if sample_clicked:
                    sample = Path(__file__).resolve().parents[1] / "data/sample/retail_sales.csv"
                    filename, payload = sample.name, sample.read_bytes()
                else:
                    filename, payload = uploaded.name, uploaded.getvalue()
                with st.spinner("Uploading and inspecting your dataset…"):
                    loaded = load_dataset(st.session_state, api, filename, payload)
                if not loaded:
                    st.info("This dataset is already loaded.")
            except APIClientError as exc:
                st.error(str(exc))
        if st.session_state.dataset_info is not None:
            info = st.session_state.dataset_info
            st.success(f'{st.session_state.dataset_name}\n\n{info["row_count"]:,} rows · {info["column_count"]:,} columns')
            st.caption(f'File size: {st.session_state.dataset_size_bytes / 1024:.1f} KiB')
            if st.button("Refresh overview", disabled=st.session_state.dataset_expired, width="stretch"):
                try:
                    with st.spinner("Refreshing dataset…"):
                        refresh_dataset(st.session_state, api)
                except APIClientError as exc:
                    st.error(str(exc))
        if st.session_state.dataset_id:
            if st.button("New conversation", width="stretch"):
                try:
                    reset_conversation(st.session_state, api)
                    st.rerun()
                except APIClientError as exc:
                    st.error(str(exc))
            if st.button("Clear dataset & history", width="stretch"):
                try:
                    reset_conversation(st.session_state, api)
                    clear_dataset(st.session_state)
                    st.rerun()
                except APIClientError as exc:
                    st.error(str(exc))
        st.divider()
        if st.button("Check backend connection", width="stretch"):
            try:
                api.health()
                st.success("Backend is ready.")
            except APIClientError as exc:
                st.error(str(exc))
        st.caption("Privacy: real AI analysis sends your question, recent conversation context, and relevant dataset-derived information to Google Gemini. Free-tier content may be used by Google to improve its products; use synthetic data only.")

    st.title("Agentic AI Data Analyst")
    st.write("Explore your CSV, ask clear questions, and see the computed evidence behind every analysis.")
    if st.session_state.dataset_expired:
        st.warning("This dataset session has expired. Load the CSV again to continue. Previous results are retained for reference.")
    if st.session_state.conversation_expired:
        st.warning("This conversation has expired or is unavailable. Choose New conversation to continue with the current dataset.")
    info = st.session_state.dataset_info
    if info is None:
        st.info("Upload a CSV or try the retail sample to begin. Then inspect the data and ask a question.")
    else:
        render_overview(info)
    st.divider()
    st.subheader("Ask your data")
    st.caption("Follow-ups use the latest five successful turns for this dataset. Each answer still requires fresh tool evidence. Start a new conversation to change topics.")
    if not st.session_state.history:
        st.caption('Try “What is the total revenue?” or “Show revenue by category.”')
    ready = info is not None and not st.session_state.dataset_expired and not st.session_state.conversation_expired
    question = st.chat_input("Ask a question about this dataset…", disabled=not ready, max_chars=2000)
    if question and ready:
        with st.spinner("Analyzing the selected dataset…"):
            submit_question(st.session_state, api, question)
    for index, entry in enumerate(st.session_state.history):
        render_analysis(entry, index)
    if len(st.session_state.history) >= MAX_HISTORY:
        st.caption(f"Showing the latest {MAX_HISTORY} questions.")


if __name__ == "__main__":
    main()
