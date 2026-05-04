import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Funnel Overview", layout="wide")
st.title("Funnel Overview")

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

METRIC_OPTIONS = {
    "Outreach Touches":    "contacted",
    "Replied":             "replied",
    "Planning Calls (GTM Conv.)": "planning_called",
    "Deals Created":       "dealt",
}

with st.sidebar:
    st.header("Filters")
    date_range = st.date_input(
        "Date range",
        value=(ytd_start, today),
        min_value=date(2024, 1, 1),
        max_value=today,
    )
    granularity = st.radio("Granularity", ["Weekly", "Monthly"], horizontal=True)
    st.divider()
    trend_metric_label = st.radio("Trend metric", list(METRIC_OPTIONS.keys()), index=2)

trend_metric = METRIC_OPTIONS[trend_metric_label]

if isinstance(date_range, tuple) and len(date_range) == 2:
    d_from, d_to = date_range
else:
    d_from, d_to = ytd_start, today

# ── Load ──────────────────────────────────────────────────────────────────────
sql = f"""
SELECT lead_segment, campaign_id, campaign_name, cohort_week, month_key,
  SUM(leads_count)           AS leads_count,
  SUM(contacted)             AS contacted,
  SUM(replied)               AS replied,
  SUM(called)                AS called,
  SUM(dealt)                 AS dealt,
  SUM(vip_dealt)             AS vip_dealt,
  SUM(onboarding_called)     AS onboarding_called,
  SUM(planning_called)       AS planning_called,
  SUM(onboarding_within_180d) AS onboarding_within_180d,
  SUM(planning_within_180d)   AS planning_within_180d,
  SUM(deal_within_180d)       AS deal_within_180d
FROM `{PROJECT}`.analytics.v_funnel_by_segment
WHERE cohort_week BETWEEN '{d_from}' AND '{d_to}'
GROUP BY 1, 2, 3, 4, 5
"""
df = query(sql)

all_segs = sorted(df["lead_segment"].dropna().unique())
all_camps = sorted(df["campaign_name"].dropna().unique())
with st.sidebar:
    segs  = st.multiselect("Segment",  all_segs,  default=all_segs)
    camps = st.multiselect("Campaign", all_camps, default=[])

fdf = df[df["lead_segment"].isin(segs)] if segs else df
if camps:
    fdf = fdf[fdf["campaign_name"].isin(camps)]

seg_label  = ", ".join(segs)  if len(segs)  < len(all_segs)  else "all"
camp_label = ", ".join(camps) if camps else "all"
st.caption(
    f"{d_from} to {d_to} · Granularity: **{granularity}** · "
    f"Segments: **{seg_label}** · Campaigns: **{camp_label}**"
)

# ── Volume scorecards ─────────────────────────────────────────────────────────
contacted   = int(fdf["contacted"].sum())
replied     = int(fdf["replied"].sum())
onb         = int(fdf["onboarding_called"].sum())
planning    = int(fdf["planning_called"].sum())
dealt       = int(fdf["dealt"].sum())
onb_180d    = int(fdf["onboarding_within_180d"].sum())
plan_180d   = int(fdf["planning_within_180d"].sum())
deal_180d   = int(fdf["deal_within_180d"].sum())

st.markdown("**Volumes**")
v1, v2, v3, v4, v5, v6 = st.columns(6)
with v1: st.metric("Outreach Touches",  f"{contacted:,}",
                   help="Each (lead x campaign) first-send counts as one touch.")
with v2: st.metric("Replied",           f"{replied:,}")
with v3: st.metric("Onboarding Calls",  f"{onb:,}")
with v4: st.metric("Planning Calls",    f"{planning:,}",
                   help="GTM conversion event.")
with v5: st.metric("Deals Created",     f"{dealt:,}")
with v6: st.metric("VIP Deals",         f"{int(fdf['vip_dealt'].sum()):,}")

# ── Conversion rate scorecards ────────────────────────────────────────────────
reply_rt      = replied    / contacted * 100 if contacted else 0
onb_180d_rt   = onb_180d   / contacted * 100 if contacted else 0
plan_180d_rt  = plan_180d  / contacted * 100 if contacted else 0
deal_180d_rt  = deal_180d  / contacted * 100 if contacted else 0
reply_to_plan = planning   / replied   * 100 if replied   else 0

st.markdown("**Conversion Rates (180-day cohort window)**")
r1, r2, r3, r4, r5 = st.columns(5)
with r1: st.metric("Reply Rate",            f"{reply_rt:.1f}%",
                   help="Replied / Outreach Touches")
with r2: st.metric("Reply to Planning",     f"{reply_to_plan:.1f}%",
                   help="Planning Calls / Replied")
with r3: st.metric("GTM Conv. (180d)",      f"{plan_180d_rt:.2f}%",
                   help="Touches that led to a planning call within 180 days. Primary GTM KPI.")
with r4: st.metric("Onboarding Rate (180d)",f"{onb_180d_rt:.2f}%",
                   help="Touches that led to an onboarding call within 180 days")
with r5: st.metric("Deal Rate (180d)",      f"{deal_180d_rt:.2f}%",
                   help="Touches that led to a deal created within 180 days")

st.divider()

# ── Single trend chart ────────────────────────────────────────────────────────
dim = "cohort_week" if granularity == "Weekly" else "month_key"

# Outreach touches volume (always shown)
st.markdown("**Outreach Touches per Week** (aggregated across selected segments)")
ts_touches = (fdf.groupby(dim)[["contacted"]].sum().reset_index())

fig_touches = px.bar(
    ts_touches, x=dim, y="contacted",
    labels={dim: "Period", "contacted": "Touches"},
    color_discrete_sequence=["#6366f1"],
)
fig_touches.update_layout(height=320, margin=dict(t=20, b=20), showlegend=False)
st.plotly_chart(fig_touches, use_container_width=True, config=CHART_CFG)

# Selectable trend metric
st.markdown(f"**Trend: {trend_metric_label}** (aggregated across selected segments via sidebar filter)")
# Aggregate across selected segments only (no color breakdown)
ts = (fdf.groupby(dim)
      [list(METRIC_OPTIONS.values()) + ["planning_within_180d"]]
      .sum().reset_index())

fig = px.line(
    ts, x=dim, y=trend_metric,
    labels={dim: "Period", trend_metric: trend_metric_label},
    color_discrete_sequence=["#22c55e"],
    markers=True,
)
fig.update_layout(height=300, margin=dict(t=20, b=20), showlegend=False)
st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

# ── GTM conversion rate trend ─────────────────────────────────────────────────
st.markdown("**GTM Conversion Rate (180d): Planning Calls / Outreach Touches**")
ts_total = fdf.groupby(dim)[["contacted", "planning_within_180d"]].sum().reset_index()
ts_total["GTM Conv %"] = (
    ts_total["planning_within_180d"] / ts_total["contacted"] * 100
).where(ts_total["contacted"] > 0)

fig_gtm = px.line(
    ts_total, x=dim, y="GTM Conv %",
    labels={"GTM Conv %": "%", dim: "Period"},
    color_discrete_sequence=["#6366f1"],
    markers=True,
)
fig_gtm.update_layout(height=280, margin=dict(t=20, b=20),
                      yaxis=dict(ticksuffix="%"))
st.plotly_chart(fig_gtm, use_container_width=True, config=CHART_CFG)

st.divider()
st.subheader("Segment Breakdown")

# ── Segment table ─────────────────────────────────────────────────────────────
seg_tbl = fdf.groupby("lead_segment").agg(
    Touches=("contacted",            "sum"),
    Replied=("replied",              "sum"),
    Onboarding=("onboarding_called", "sum"),
    Planning=("planning_called",     "sum"),
    Deals=("dealt",                  "sum"),
    VIP_Deals=("vip_dealt",          "sum"),
    Onb_60d=("onboarding_within_60d","sum"),
    Plan_60d=("planning_within_60d", "sum"),
    Deal_60d=("deal_within_60d",     "sum"),
).reset_index()

seg_tbl["Reply%"]      = (seg_tbl["Replied"]   / seg_tbl["Touches"] * 100).round(1)
seg_tbl["GTM Conv%"]   = (seg_tbl["Plan_60d"]  / seg_tbl["Touches"] * 100).round(2)
seg_tbl["Onb60%"]      = (seg_tbl["Onb_60d"]   / seg_tbl["Touches"] * 100).round(2)
seg_tbl["Deal60%"]     = (seg_tbl["Deal_60d"]  / seg_tbl["Touches"] * 100).round(2)
seg_tbl = seg_tbl.sort_values("Plan_60d", ascending=False)

st.dataframe(seg_tbl, use_container_width=True, hide_index=True,
             column_config={
                 "Reply%":    st.column_config.NumberColumn("Reply%",    format="%.1f%%"),
                 "GTM Conv%": st.column_config.NumberColumn("GTM Conv%", format="%.2f%%"),
                 "Onb60%":    st.column_config.NumberColumn("Onb60%",    format="%.2f%%"),
                 "Deal60%":   st.column_config.NumberColumn("Deal60%",   format="%.2f%%"),
             })
