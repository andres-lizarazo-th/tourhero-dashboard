import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT
from utils.charts import annotate

st.set_page_config(page_title="Campaigns", layout="wide")
st.title("Campaigns")

st.markdown("""
<style>
[data-testid="stElementToolbar"] {display: none !important;}
[data-testid="stDownloadButton"] {display: none !important;}
</style>
""", unsafe_allow_html=True)

CHART_CFG = {"displayModeBar": False}

# ── Sidebar filters ───────────────────────────────────────────────────────────
today = date.today()
ytd_start = date(today.year, 1, 1)

with st.sidebar:
    st.header("Filters")
    date_range = st.date_input(
        "Date range",
        value=(ytd_start, today),
        min_value=date(2024, 1, 1),
        max_value=today,
    )

if isinstance(date_range, tuple) and len(date_range) == 2:
    d_from, d_to = date_range
else:
    d_from, d_to = ytd_start, today

sql = f"""
SELECT stat_date, week_start, month_key, campaign_id, campaign_name,
  campaign_type, campaign_status, campaign_created_at,
  sent, replied, bounced, unsubscribed, interested,
  reply_rate_pct, bounce_rate_pct, unsub_rate_pct,
  unique_leads_total
FROM `{PROJECT}`.bison_tracking.v_campaign_performance
WHERE stat_date BETWEEN '{d_from}' AND '{d_to}'
"""
df = query(sql)
df["stat_date"] = pd.to_datetime(df["stat_date"])

with st.sidebar:
    campaigns   = st.multiselect("Campaign", sorted(df["campaign_name"].dropna().unique()))
    statuses    = st.multiselect("Status",   sorted(df["campaign_status"].dropna().unique()))
    granularity = st.radio("Granularity", ["Weekly", "Monthly"], horizontal=True)

fdf = df.copy()
if campaigns: fdf = fdf[fdf["campaign_name"].isin(campaigns)]
if statuses:  fdf = fdf[fdf["campaign_status"].isin(statuses)]

st.caption(f"{d_from} to {d_to} · Granularity: **{granularity}**")

# ── Scorecards ────────────────────────────────────────────────────────────────
active = fdf[fdf["sent"] > 0]
total_sent    = int(active["sent"].sum())
total_replied = int(active["replied"].sum())
total_bounced = int(active["bounced"].sum())
total_unsub   = int(active["unsubscribed"].sum())
total_intd    = int(fdf["interested"].sum())
reply_rate    = total_replied / total_sent * 100 if total_sent else 0
bounce_rate   = total_bounced / total_sent * 100 if total_sent else 0
unsub_rate    = total_unsub   / total_sent * 100 if total_sent else 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1: st.metric("Emails Sent",   f"{total_sent:,}")
with c2: st.metric("Replies",       f"{total_replied:,}")
with c3: st.metric("Interested",    f"{total_intd:,}")
with c4: st.metric("Reply Rate",    f"{reply_rate:.2f}%",
                   help="Lifetime campaign-level rate. Not shown per-week (replies lag behind sends by days–weeks).")
with c5: st.metric("Bounce Rate",   f"{bounce_rate:.2f}%")
with c6: st.metric("Unsub Rate",    f"{unsub_rate:.2f}%")

st.divider()

# ── Time series ───────────────────────────────────────────────────────────────
dim = "week_start" if granularity == "Weekly" else "month_key"

col1, col2 = st.columns(2)

def _sort_monthly(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df = df.copy()
    df["__s"] = pd.to_datetime(df[col], format="%b %Y", errors="coerce")
    return df.sort_values("__s").drop(columns=["__s"])

def _sort_weekly(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Sort '%-d %b' week labels chronologically, handling year boundaries."""
    df = df.copy()
    yr   = d_from.year
    base = pd.to_datetime(df[col] + f" {yr}", errors="coerce")
    late  = base > pd.Timestamp(d_to) + pd.Timedelta(days=90)
    base.loc[late] = pd.to_datetime(df.loc[late, col] + f" {yr - 1}", errors="coerce")
    if yr != d_to.year:
        early = base < pd.Timestamp(d_from) - pd.Timedelta(days=7)
        base.loc[early] = pd.to_datetime(df.loc[early, col] + f" {d_to.year}", errors="coerce")
    df["__s"] = base
    return df.sort_values("__s").drop(columns=["__s"])

with col1:
    ts = fdf.groupby(dim)[["sent", "replied"]].sum().reset_index()
    if dim == "month_key":
        ts = _sort_monthly(ts, "month_key")
    else:
        ts = _sort_weekly(ts, dim)
    fig = px.bar(ts, x=dim, y="sent",
                 title="Emails Sent per " + ("Week" if granularity == "Weekly" else "Month"),
                 labels={"sent": "Sent", dim: "Period"},
                 color_discrete_sequence=["#6366f1"],
                 category_orders={dim: ts[dim].tolist()})
    fig.update_layout(height=340, margin=dict(t=40, b=20))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=ts[dim].tolist())
    annotate(fig)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

with col2:
    # Bounce and unsub are same-day/immediate responses — valid to show per week.
    # Reply rate is NOT shown per-week because replies lag behind sends by days to weeks;
    # the cohort-correct reply rate is shown on the Funnel Overview page.
    rates = fdf.groupby(dim)[["sent", "bounced", "unsubscribed"]].sum().reset_index()
    if dim == "month_key":
        rates = _sort_monthly(rates, "month_key")
    else:
        rates = _sort_weekly(rates, dim)
    rates["Bounce %"] = (rates["bounced"]      / rates["sent"] * 100).where(rates["sent"] > 0)
    rates["Unsub %"]  = (rates["unsubscribed"] / rates["sent"] * 100).where(rates["sent"] > 0)
    fig2 = px.line(rates, x=dim, y=["Bounce %", "Unsub %"],
                   title="Bounce & Unsub Rate per " + ("Week" if granularity == "Weekly" else "Month"),
                   labels={"value": "%", dim: "Period"},
                   color_discrete_sequence=["#ef4444", "#f59e0b"], markers=True,
                   category_orders={dim: rates[dim].tolist()})
    fig2.update_layout(height=340, legend_title="",
                       yaxis=dict(ticksuffix="%"))
    fig2.update_xaxes(type="category", categoryorder="array", categoryarray=rates[dim].tolist())
    annotate(fig2, fmt=".1f", pct=True)
    st.caption("Reply rate is not shown per-week — replies arrive days to weeks after the send. See Funnel Overview for cohort-corrected reply rates.")
    st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)

st.divider()
st.subheader("Campaign Performance Table")

camp_tbl = fdf[fdf["sent"] > 0].groupby("campaign_name").agg(
    Created=("campaign_created_at", "min"),
    Sent=("sent",                   "sum"),
    Unique_Leads=("unique_leads_total", "max"),  # same value for all rows of a campaign
    Replies=("replied",             "sum"),
    Bounced=("bounced",             "sum"),
    Unsubs=("unsubscribed",         "sum"),
    Interested=("interested",       "sum"),
).reset_index()
camp_tbl["Reply%"]  = (camp_tbl["Replies"] / camp_tbl["Sent"] * 100).round(2)
camp_tbl["Bounce%"] = (camp_tbl["Bounced"] / camp_tbl["Sent"] * 100).round(2)
camp_tbl["Unsub%"]  = (camp_tbl["Unsubs"]  / camp_tbl["Sent"] * 100).round(2)
camp_tbl["Created"] = pd.to_datetime(camp_tbl["Created"]).dt.date
camp_tbl = camp_tbl[camp_tbl["Sent"] > 0].sort_values("Created", ascending=False)

st.dataframe(camp_tbl, use_container_width=True, hide_index=True,
             column_config={
                 "Created":      st.column_config.DateColumn("Created", format="YYYY-MM-DD"),
                 "Unique_Leads": st.column_config.NumberColumn("Unique Leads"),
                 "Reply%":       st.column_config.NumberColumn("Reply%",  format="%.2f%%"),
                 "Bounce%":      st.column_config.NumberColumn("Bounce%", format="%.2f%%"),
                 "Unsub%":       st.column_config.NumberColumn("Unsub%",  format="%.2f%%"),
             })
