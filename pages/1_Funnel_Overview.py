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
    "Outreach Touches":         "contacted",
    "Replied":                  "replied",
    "Planning Calls (GTM Conv.)": "planning_called",
    "Deals Created":            "dealt",
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

# ── Load 1: touch-level volumes from v_funnel_by_segment ─────────────────────
sql = f"""
SELECT lead_segment, campaign_id, campaign_name, cohort_week, month_key,
  SUM(leads_count)       AS leads_count,
  SUM(contacted)         AS contacted,
  SUM(replied)           AS replied,
  SUM(called)            AS called,
  SUM(dealt)             AS dealt,
  SUM(vip_dealt)         AS vip_dealt,
  SUM(onboarding_called) AS onboarding_called,
  SUM(planning_called)   AS planning_called
FROM `{PROJECT}`.analytics.v_funnel_by_segment
WHERE cohort_week BETWEEN '{d_from}' AND '{d_to}'
GROUP BY 1, 2, 3, 4, 5
"""
df = query(sql)

# ── Load 2: per-lead stage rates + velocity from leads_master ─────────────────
sql_lm = f"""
SELECT
  lead_segment,
  COUNTIF(first_contacted_at IS NOT NULL)               AS lm_contacted,
  COUNTIF(last_reply_at IS NOT NULL)                    AS lm_replied,
  COUNTIF(first_onboarding_call_at IS NOT NULL)         AS lm_onboarding,
  COUNTIF(first_planning_call_at IS NOT NULL)           AS lm_planning,
  COUNTIF(deal_created_at IS NOT NULL)                  AS lm_dealt,
  ROUND(AVG(CASE WHEN last_reply_at >= first_contacted_at
                 THEN TIMESTAMP_DIFF(last_reply_at, first_contacted_at, DAY) END), 1)
        AS avg_days_to_reply,
  ROUND(AVG(CASE WHEN first_onboarding_call_at >= first_contacted_at
                 THEN TIMESTAMP_DIFF(first_onboarding_call_at, first_contacted_at, DAY) END), 1)
        AS avg_days_to_onb,
  ROUND(AVG(CASE WHEN first_planning_call_at IS NOT NULL
                      AND first_onboarding_call_at IS NOT NULL
                      AND first_planning_call_at >= first_onboarding_call_at
                 THEN TIMESTAMP_DIFF(first_planning_call_at, first_onboarding_call_at, DAY) END), 1)
        AS avg_days_onb_to_plan,
  ROUND(AVG(CASE WHEN first_planning_call_at IS NOT NULL
                      AND first_contacted_at IS NOT NULL
                      AND first_planning_call_at >= first_contacted_at
                 THEN TIMESTAMP_DIFF(first_planning_call_at, first_contacted_at, DAY) END), 1)
        AS avg_days_to_plan
FROM `{PROJECT}`.analytics.leads_master
WHERE DATE(first_contacted_at) BETWEEN '{d_from}' AND '{d_to}'
  AND lead_segment NOT IN ('unmatched-email-addresses')
GROUP BY 1
"""
lm_df = query(sql_lm)

# ── Sidebar segment / campaign filters ───────────────────────────────────────
all_segs  = sorted(df["lead_segment"].dropna().unique())
all_camps = sorted(df["campaign_name"].dropna().unique())
with st.sidebar:
    segs  = st.multiselect("Segment",  all_segs,  default=all_segs)
    camps = st.multiselect("Campaign", all_camps, default=[])

fdf = df[df["lead_segment"].isin(segs)] if segs else df
if camps:
    fdf = fdf[fdf["campaign_name"].isin(camps)]

lm_fdf = lm_df[lm_df["lead_segment"].isin(segs)] if segs else lm_df

seg_label  = ", ".join(segs)  if len(segs)  < len(all_segs)  else "all"
camp_label = ", ".join(camps) if camps else "all"
st.caption(
    f"{d_from} to {d_to} · Granularity: **{granularity}** · "
    f"Segments: **{seg_label}** · Campaigns: **{camp_label}**"
)

# ── Volume scorecards (touch-level) ───────────────────────────────────────────
contacted   = int(fdf["contacted"].sum())
replied     = int(fdf["replied"].sum())
onb         = int(fdf["onboarding_called"].sum())
planning    = int(fdf["planning_called"].sum())
dealt       = int(fdf["dealt"].sum())

st.markdown("**Outreach Volumes** (touch-level: each lead × campaign counts separately)")
v1, v2, v3, v4, v5, v6 = st.columns(6)
with v1: st.metric("Outreach Touches",  f"{contacted:,}",
                   help="Each (lead × campaign) first-send counts as one touch.")
with v2: st.metric("Replied",           f"{replied:,}")
with v3: st.metric("Onboarding Calls",  f"{onb:,}")
with v4: st.metric("Planning Calls",    f"{planning:,}",
                   help="GTM conversion event.")
with v5: st.metric("Deals Created",     f"{dealt:,}")
with v6: st.metric("VIP Deals",         f"{int(fdf['vip_dealt'].sum()):,}")

# ── Per-lead conversion funnel ────────────────────────────────────────────────
lm_tot         = lm_fdf.sum(numeric_only=True)
lm_contacted   = int(lm_tot.get("lm_contacted",  0))
lm_replied     = int(lm_tot.get("lm_replied",    0))
lm_onboarding  = int(lm_tot.get("lm_onboarding", 0))
lm_planning    = int(lm_tot.get("lm_planning",   0))
lm_dealt       = int(lm_tot.get("lm_dealt",      0))

reply_rt    = lm_replied    / lm_contacted   * 100 if lm_contacted   else 0
onb_rt      = lm_onboarding / lm_replied     * 100 if lm_replied     else 0
plan_rt     = lm_planning   / lm_onboarding  * 100 if lm_onboarding  else 0
deal_rt     = lm_dealt      / lm_planning    * 100 if lm_planning    else 0
contact2plan = lm_planning  / lm_contacted   * 100 if lm_contacted   else 0

st.markdown("**Per-Lead Conversion Funnel** (unique leads — same lead contacted by 2 campaigns counts once)")
fa, fb, fc, fd, fe = st.columns(5)
with fa: st.metric("Contact → Reply",     f"{reply_rt:.1f}%",
                   help="Unique leads who replied / unique leads contacted")
with fb: st.metric("Reply → Onboarding",  f"{onb_rt:.1f}%",
                   help="Leads who had an onboarding call / leads who replied")
with fc: st.metric("Onboarding → Planning", f"{plan_rt:.1f}%",
                   help="Leads who booked a planning call / leads who had onboarding. Primary GTM conversion.")
with fd: st.metric("Planning → Deal",     f"{deal_rt:.1f}%",
                   help="Leads who created a deal / leads who had a planning call")
with fe: st.metric("Contact → Planning",  f"{contact2plan:.2f}%",
                   help="End-to-end: leads who reached planning call / total leads contacted")

# Funnel chart
if lm_contacted > 0:
    funnel_df = pd.DataFrame({
        "Stage": ["Contacted", "Replied", "Onboarding", "Planning Call", "Deal"],
        "Leads": [lm_contacted, lm_replied, lm_onboarding, lm_planning, lm_dealt],
    })
    fig_funnel = px.funnel(funnel_df, x="Leads", y="Stage",
                           color_discrete_sequence=["#6366f1"])
    fig_funnel.update_layout(height=300, margin=dict(t=10, b=10), showlegend=False)
    st.plotly_chart(fig_funnel, use_container_width=True, config=CHART_CFG)

st.divider()

# ── Trend charts ──────────────────────────────────────────────────────────────
dim = "cohort_week" if granularity == "Weekly" else "month_key"

st.markdown("**Outreach Touches per Period** (aggregated across selected segments)")
ts_touches = fdf.groupby(dim)[["contacted"]].sum().reset_index()
fig_touches = px.bar(
    ts_touches, x=dim, y="contacted",
    labels={dim: "Period", "contacted": "Touches"},
    color_discrete_sequence=["#6366f1"],
)
fig_touches.update_layout(height=300, margin=dict(t=20, b=20), showlegend=False)
st.plotly_chart(fig_touches, use_container_width=True, config=CHART_CFG)

st.markdown(f"**Trend: {trend_metric_label}** (aggregated across selected segments)")
ts = fdf.groupby(dim)[list(METRIC_OPTIONS.values())].sum().reset_index()
fig = px.line(
    ts, x=dim, y=trend_metric,
    labels={dim: "Period", trend_metric: trend_metric_label},
    color_discrete_sequence=["#22c55e"],
    markers=True,
)
fig.update_layout(height=280, margin=dict(t=20, b=20), showlegend=False)
st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

st.divider()
st.subheader("Segment Breakdown")

# ── Segment table (touch-level volumes + per-lead conversion rates) ───────────
seg_tbl = fdf.groupby("lead_segment").agg(
    Touches=("contacted",          "sum"),
    Replied=("replied",            "sum"),
    Onboarding=("onboarding_called", "sum"),
    Planning=("planning_called",   "sum"),
    Deals=("dealt",                "sum"),
    VIP_Deals=("vip_dealt",        "sum"),
).reset_index()

# Merge per-lead rates from leads_master query
lm_seg = lm_fdf[["lead_segment","lm_contacted","lm_replied","lm_onboarding","lm_planning","lm_dealt"]].copy()
seg_tbl = seg_tbl.merge(lm_seg, on="lead_segment", how="left")

seg_tbl["Reply%"]      = (seg_tbl["lm_replied"]    / seg_tbl["lm_contacted"]  * 100).round(1)
seg_tbl["Onb%"]        = (seg_tbl["lm_onboarding"] / seg_tbl["lm_replied"]    * 100).round(1)
seg_tbl["Plan%"]       = (seg_tbl["lm_planning"]   / seg_tbl["lm_onboarding"] * 100).round(1)
seg_tbl["C→Plan%"]     = (seg_tbl["lm_planning"]   / seg_tbl["lm_contacted"]  * 100).round(2)

seg_tbl = seg_tbl.sort_values("lm_planning", ascending=False)
seg_tbl = seg_tbl.drop(columns=["lm_contacted","lm_replied","lm_onboarding","lm_planning","lm_dealt"])

st.dataframe(seg_tbl, use_container_width=True, hide_index=True,
             column_config={
                 "Reply%":  st.column_config.NumberColumn("Reply%",      format="%.1f%%",
                            help="Unique leads who replied / contacted"),
                 "Onb%":    st.column_config.NumberColumn("Reply→Onb%",  format="%.1f%%",
                            help="Replied leads who had onboarding call"),
                 "Plan%":   st.column_config.NumberColumn("Onb→Plan%",   format="%.1f%%",
                            help="Onboarded leads who booked planning call"),
                 "C→Plan%": st.column_config.NumberColumn("Contact→Plan%", format="%.2f%%",
                            help="End-to-end: leads who reached planning / leads contacted"),
             })

# ── Stage Velocity ────────────────────────────────────────────────────────────
st.divider()
st.subheader("Stage Velocity (Avg Days per Stage)")
st.caption("How long does each stage transition take on average, for leads in the selected date range and segments.")

vel_tbl = lm_fdf[["lead_segment","avg_days_to_reply","avg_days_to_onb",
                   "avg_days_onb_to_plan","avg_days_to_plan"]].copy()
vel_tbl = vel_tbl.rename(columns={
    "lead_segment":       "Segment",
    "avg_days_to_reply":   "Contact→Reply (days)",
    "avg_days_to_onb":     "Contact→Onboarding (days)",
    "avg_days_onb_to_plan":"Onboarding→Planning (days)",
    "avg_days_to_plan":    "Contact→Planning (days)",
})
vel_tbl = vel_tbl.sort_values("Contact→Planning (days)")

st.dataframe(vel_tbl, use_container_width=True, hide_index=True,
             column_config={
                 "Contact→Reply (days)":       st.column_config.NumberColumn(format="%.1f"),
                 "Contact→Onboarding (days)":  st.column_config.NumberColumn(format="%.1f"),
                 "Onboarding→Planning (days)": st.column_config.NumberColumn(format="%.1f"),
                 "Contact→Planning (days)":    st.column_config.NumberColumn(format="%.1f"),
             })
