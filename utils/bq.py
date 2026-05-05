import os
from pathlib import Path

import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

_ROOT = Path(__file__).parents[2]
_ENV = _ROOT / ".env"
if _ENV.exists():
    from dotenv import load_dotenv
    load_dotenv(_ENV)

# Fix relative credentials path (local dev with .env)
_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
if _creds and not os.path.isabs(_creds):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_ROOT / _creds)

# Project / location can come from .env locally OR from st.secrets on Streamlit Cloud.
# Accessing st.secrets when no secrets.toml exists raises an error, so guard it.
def _secret_get(key: str, default: str) -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

PROJECT  = os.getenv("GCP_PROJECT_ID") or _secret_get("GCP_PROJECT_ID",  "creator-outreach-database")
LOCATION = os.getenv("BQ_LOCATION")    or _secret_get("BQ_LOCATION",     "southamerica-east1")

DS = {
    "analytics":      "analytics",
    "bison":          "bison_tracking",
    "bdcrm":          "bdcrm",
    "operations":     "operations",
}


def _has_streamlit_secrets() -> bool:
    """Safely check if a secrets.toml file exists. Accessing st.secrets when no
    secrets file is present raises StreamlitSecretNotFoundError."""
    try:
        return "gcp_service_account" in st.secrets
    except Exception:
        return False


@st.cache_resource
def _client() -> bigquery.Client:
    # On Streamlit Cloud: credentials come from st.secrets["gcp_service_account"]
    # Locally: credentials come from GOOGLE_APPLICATION_CREDENTIALS env var
    if _has_streamlit_secrets():
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"])
        )
        return bigquery.Client(project=PROJECT, credentials=creds)
    return bigquery.Client(project=PROJECT)


_WEEK_DATE_COLS = {"cohort_week", "week_start", "month_start"}


@st.cache_data(ttl=3600, show_spinner="Querying BigQuery…")
def query(sql: str) -> pd.DataFrame:
    job = _client().query(sql, location=LOCATION)
    df = job.to_dataframe(create_bqstorage_client=False)
    # Convert month_key YYYYMM int → "Jan 2026" label so Plotly treats it as
    # categorical text, not a number (avoids "202.601k" axis rendering).
    if "month_key" in df.columns:
        mk = df["month_key"].astype(str).str.zfill(6)
        df["month_key"] = (
            pd.to_datetime(mk, format="%Y%m", errors="coerce")
            .dt.strftime("%b %Y")
            .fillna(mk)
        )
    # Format Monday-truncated DATE columns as "20 Apr" so Plotly cannot
    # auto-parse them as dates (which would shift tick labels to the nearest Sunday).
    for col in _WEEK_DATE_COLS & set(df.columns):
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            dt = df[col]
        elif df[col].dtype == "object":
            dt = pd.to_datetime(df[col], errors="coerce")
        else:
            continue
        df[col] = dt.dt.strftime("%-d %b")
    return df


def q(view: str, dataset: str, where: str = "", cols: str = "*") -> pd.DataFrame:
    w = f"WHERE {where}" if where else ""
    return query(f"SELECT {cols} FROM `{PROJECT}`.`{dataset}`.`{view}` {w}")
