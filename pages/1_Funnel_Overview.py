import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT
from utils.charts import annotate

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
    "Outreach Emails": "contacted",
    "Replied":         "replied",
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
  COUNTIF(last_reply_at IS NOT NULL AND last_reply_at >= first_contacted_at) AS lm_replied,
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

# ── Load 3: monthly per-lead counts by segment (for conversion rate trends) ───
sql_lm_monthly = f"""
SELECT
  FORMAT_DATE('%Y-%m', DATE(first_contacted_at))   AS contact_month,
  lead_segment,
  COUNTIF(first_contacted_at IS NOT NULL)           AS contacted,
  COUNTIF(last_reply_at IS NOT NULL AND last_reply_at >= first_contacted_at) AS replied,
  COUNTIF(first_onboarding_call_at IS NOT NULL)     AS onboarding,
  COUNTIF(first_planning_call_at IS NOT NULL)       AS planning,
  COUNTIF(deal_created_at IS NOT NULL)              AS dealt
FROM `{PROJECT}`.analytics.leads_master
WHERE DATE(first_contacted_at) BETWEEN '{d_from}' AND '{d_to}'
  AND lead_segment NOT IN ('unmatched-email-addresses')
GROUP BY 1, 2
ORDER BY 1
"""
lm_monthly_df = query(sql_lm_monthly)
# Convert "2026-01" → "Jan 2026" for display (after query while still sortable)
lm_monthly_df = lm_monthly_df.sort_values("contact_month")
lm_monthly_df["contact_month"] = (
    pd.to_datetime(lm_monthly_df["contact_month"], format="%Y-%m", errors="coerce")
    .dt.strftime("%b %Y")
    .fillna(lm_monthly_df["contact_month"])
)

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
lm_monthly_fdf = lm_monthly_df[lm_monthly_df["lead_segment"].isin(segs)] if segs else lm_monthly_df

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

st.markdown("**Outreach Volumes** (email-level: each lead × campaign first-send counts separately)")
v1, v2, v3, v4, v5, v6 = st.columns(6)
with v1: st.metric("Outreach Emails",   f"{contacted:,}",
                   help="Each (lead × campaign) first-send counts as one outreach email.")
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

# ── Monthly conversion rate trends ────────────────────────────────────────────
st.subheader("Monthly Conversion Rate Trends")
st.caption("Cohort view: of leads first contacted in each month, what % eventually reached each stage.")

monthly_agg = (
    lm_monthly_fdf
    .groupby("contact_month")[["contacted","replied","onboarding","planning","dealt"]]
    .sum()
    .reset_index()
)
# Sort chronologically ("Jan 2026" doesn't sort alphabetically)
monthly_agg["__s"] = pd.to_datetime(monthly_agg["contact_month"], format="%b %Y", errors="coerce")
monthly_agg = monthly_agg.sort_values("__s").drop(columns=["__s"])
monthly_agg["reply_rate"]  = (monthly_agg["replied"]    / monthly_agg["contacted"]  * 100).round(1)
monthly_agg["onb_rate"]    = (monthly_agg["onboarding"] / monthly_agg["replied"]    * 100).round(1)
monthly_agg["plan_rate"]   = (monthly_agg["planning"]   / monthly_agg["onboarding"] * 100).round(1)
monthly_agg["deal_rate"]   = (monthly_agg["dealt"]      / monthly_agg["planning"]   * 100).round(1)
monthly_agg["c2plan_rate"] = (monthly_agg["planning"]   / monthly_agg["contacted"]  * 100).round(2)

RATE_CHARTS = [
    ("Contact → Reply %",       "reply_rate",  "#6366f1"),
    ("Reply → Onboarding %",    "onb_rate",    "#f59e0b"),
    ("Onboarding → Planning %", "plan_rate",   "#22c55e"),
    ("Planning → Deal %",       "deal_rate",   "#ef4444"),
]

if len(monthly_agg) > 0:
    mr1, mr2 = st.columns(2)
    mr3, mr4 = st.columns(2)
    for col, (label, col_name, color) in zip([mr1, mr2, mr3, mr4], RATE_CHARTS):
        with col:
            fig_r = px.line(
                monthly_agg, x="contact_month", y=col_name,
                title=label,
                labels={"contact_month": "", col_name: "%"},
                color_discrete_sequence=[color],
                markers=True,
            )
            fig_r.update_layout(height=260, margin=dict(t=40, b=10), showlegend=False,
                                yaxis=dict(ticksuffix="%"))
            fig_r.update_xaxes(type="category")
            annotate(fig_r, fmt=".1f", pct=True)
            st.plotly_chart(fig_r, use_container_width=True, config=CHART_CFG)

    fig_c2p = px.line(
        monthly_agg, x="contact_month", y="c2plan_rate",
        title="Contact → Planning % (end-to-end GTM conversion)",
        labels={"contact_month": "", "c2plan_rate": "%"},
        color_discrete_sequence=["#8b5cf6"],
        markers=True,
    )
    fig_c2p.update_layout(height=260, margin=dict(t=40, b=10), showlegend=False,
                          yaxis=dict(ticksuffix="%"))
    fig_c2p.update_xaxes(type="category")
    annotate(fig_c2p, fmt=".2f", pct=True)
    st.plotly_chart(fig_c2p, use_container_width=True, config=CHART_CFG)

st.divider()

# ── Trend charts ──────────────────────────────────────────────────────────────
dim = "cohort_week" if granularity == "Weekly" else "month_key"

ts = fdf.groupby(dim)[list(METRIC_OPTIONS.values())].sum().reset_index()
if dim == "month_key":
    ts["__s"] = pd.to_datetime(ts["month_key"], format="%b %Y", errors="coerce")
    ts = ts.sort_values("__s").drop(columns=["__s"])

TREND_CHARTS = [
    ("Outreach Emails", "contacted", "#6366f1", "bar"),
    ("Replied",         "replied",   "#f59e0b", "bar"),
]

t1, t2 = st.columns(2)
for col, (label, metric, color, _) in zip([t1, t2], TREND_CHARTS):
    with col:
        fig_t = px.bar(
            ts, x=dim, y=metric,
            title=label,
            labels={dim: "", metric: label},
            color_discrete_sequence=[color],
        )
        fig_t.update_layout(height=280, margin=dict(t=40, b=10), showlegend=False)
        fig_t.update_xaxes(type="category")
        annotate(fig_t)
        st.plotly_chart(fig_t, use_container_width=True, config=CHART_CFG)

st.divider()

# ── Calls charts (Calendly) ───────────────────────────────────────────────────
ONB_PATTERN  = r"(?i)(Creator Trip Collab|Community Trip Collab|Wellness Trip Collab|Outdoor Trip Collab|VIP.*Onboarding|Onboarding Session|Group Trips|MBA|HBS|campus)"
PLAN_PATTERN = r"(?i)(Plan(ning)? (your|a) (next )?trip|Brainstorm with your Planning Expert|Meet your Inspiration Expert|Planning Call|Start Planning Your Dream Trip|Let.s Plan Your Trip)"

sql_calls = f"""
SELECT
  DATE_TRUNC(DATE(invitee_created_at), WEEK(MONDAY))                            AS week_start,
  FORMAT_DATE('%Y%m', DATE_TRUNC(DATE(invitee_created_at), WEEK(MONDAY)))       AS month_key,
  COUNTIF(REGEXP_CONTAINS(event_name, r'{ONB_PATTERN}'))                                              AS onb_booked,
  COUNTIF(REGEXP_CONTAINS(event_name, r'{ONB_PATTERN}')
          AND invitee_status = 'active' AND no_show IS NOT TRUE)                                      AS onb_showed_up,
  COUNTIF(REGEXP_CONTAINS(event_name, r'{PLAN_PATTERN}'))                                             AS plan_booked,
  COUNTIF(REGEXP_CONTAINS(event_name, r'{PLAN_PATTERN}')
          AND invitee_status = 'active' AND no_show IS NOT TRUE)                                      AS plan_showed_up
FROM `{PROJECT}`.calendly.calendly_events
WHERE invitee_created_at >= TIMESTAMP '{d_from}'
  AND invitee_created_at <  TIMESTAMP_ADD(TIMESTAMP '{d_to}', INTERVAL 1 DAY)
  AND LOWER(COALESCE(invitee_email, '')) NOT LIKE '%@tourhero.com'
GROUP BY 1, 2
ORDER BY 1
"""
calls_df = query(sql_calls)

sql_deals_activity = f"""
SELECT
  DATE_TRUNC(DATE(deal_created_at), WEEK(MONDAY))                          AS week_start,
  FORMAT_DATE('%Y%m', DATE_TRUNC(DATE(deal_created_at), WEEK(MONDAY)))     AS month_key,
  COUNT(*) AS deals_count
FROM `{PROJECT}`.analytics.leads_master
WHERE deal_created_at IS NOT NULL
  AND DATE(deal_created_at) BETWEEN '{d_from}' AND '{d_to}'
GROUP BY 1, 2
ORDER BY 1
"""
deals_activity_df = query(sql_deals_activity)

sql_bookings = f"""
SELECT
  DATE_TRUNC(booking_date, WEEK(MONDAY))                          AS week_start,
  FORMAT_DATE('%Y%m', DATE_TRUNC(booking_date, WEEK(MONDAY)))     AS month_key,
  COUNT(*) AS bookings_count
FROM `{PROJECT}`.operations.imp_bookings
WHERE booking_status = 'confirmed'
  AND booking_date BETWEEN '{d_from}' AND '{d_to}'
GROUP BY 1, 2
ORDER BY 1
"""
bookings_df = query(sql_bookings)

calls_dim = "week_start" if granularity == "Weekly" else "month_key"

# Aggregate by month when monthly mode (raw data has one row per week)
if calls_dim == "month_key":
    calls_plot = (
        calls_df.groupby("month_key")[["onb_booked","onb_showed_up","plan_booked","plan_showed_up"]]
        .sum().reset_index()
    )
    calls_plot["__s"] = pd.to_datetime(calls_plot["month_key"], format="%b %Y", errors="coerce")
    calls_plot = calls_plot.sort_values("__s").drop(columns=["__s"])
else:
    calls_plot = calls_df


def _calls_chart(cdf: pd.DataFrame, dim: str, booked_col: str, showup_col: str, title: str,
                 ymax: float = None):
    cdf = cdf.copy()
    cdf["showup_pct"] = (
        cdf[showup_col] / cdf[booked_col].replace(0, None) * 100
    ).round(1)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=cdf[dim], y=cdf[booked_col], name="Booked", marker_color="#6366f1",
                         text=cdf[booked_col], textposition="inside",
                         textfont=dict(size=10, color="white")), secondary_y=False)
    fig.add_trace(go.Bar(x=cdf[dim], y=cdf[showup_col], name="Showed Up", marker_color="#22c55e",
                         text=cdf[showup_col], textposition="inside",
                         textfont=dict(size=10, color="white")), secondary_y=False)
    pct_labels = cdf["showup_pct"].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "")
    fig.add_trace(go.Scatter(x=cdf[dim], y=cdf["showup_pct"], name="Show-up %",
                             mode="lines+markers+text",
                             line=dict(color="#f59e0b", width=2),
                             marker=dict(size=6),
                             text=pct_labels, textposition="top center",
                             textfont=dict(size=10)), secondary_y=True)
    fig.update_layout(
        title=title, barmode="group", height=360,
        margin=dict(t=50, b=60),
        legend=dict(orientation="h", y=-0.22),
    )
    fig.update_yaxes(title_text="Calls", secondary_y=False)
    if ymax is not None:
        fig.update_yaxes(range=[0, ymax * 1.2], secondary_y=False)
    fig.update_yaxes(title_text="Show-up %", ticksuffix="%", range=[0, 110], secondary_y=True)
    fig.update_xaxes(type="category")
    return fig


st.subheader("Calls")

# Shared Y-axis max so both charts use the same scale and are visually comparable
_calls_ymax = (
    max(calls_plot["onb_booked"].max(), calls_plot["plan_booked"].max()) * 1.0
    if len(calls_plot) > 0 else None
)

col_onb, col_plan = st.columns(2)
with col_onb:
    if len(calls_plot) > 0:
        st.plotly_chart(_calls_chart(calls_plot, calls_dim, "onb_booked", "onb_showed_up",
                                     "Onboarding Calls — Booked vs Showed Up", ymax=_calls_ymax),
                        use_container_width=True, config=CHART_CFG)
    else:
        st.info("No onboarding call data for this period.")

with col_plan:
    if len(calls_plot) > 0:
        st.plotly_chart(_calls_chart(calls_plot, calls_dim, "plan_booked", "plan_showed_up",
                                     "Planning Calls — Booked vs Showed Up", ymax=_calls_ymax),
                        use_container_width=True, config=CHART_CFG)
    else:
        st.info("No planning call data for this period.")

st.divider()
st.subheader("Deals & Bookings")

activity_dim = "week_start" if granularity == "Weekly" else "month_key"

if activity_dim == "month_key":
    deals_plot = deals_activity_df.groupby("month_key")[["deals_count"]].sum().reset_index()
    deals_plot["__s"] = pd.to_datetime(deals_plot["month_key"], format="%b %Y", errors="coerce")
    deals_plot = deals_plot.sort_values("__s").drop(columns=["__s"])
    bookings_plot = bookings_df.groupby("month_key")[["bookings_count"]].sum().reset_index()
    bookings_plot["__s"] = pd.to_datetime(bookings_plot["month_key"], format="%b %Y", errors="coerce")
    bookings_plot = bookings_plot.sort_values("__s").drop(columns=["__s"])
else:
    deals_plot = deals_activity_df
    bookings_plot = bookings_df

col_deals, col_book = st.columns(2)
with col_deals:
    if len(deals_plot) > 0:
        fig_deals = px.bar(deals_plot, x=activity_dim, y="deals_count",
                           title="Deals Created",
                           labels={activity_dim: "", "deals_count": "Deals"},
                           color_discrete_sequence=["#ef4444"])
        fig_deals.update_layout(height=320, margin=dict(t=40, b=10), showlegend=False)
        fig_deals.update_xaxes(type="category")
        annotate(fig_deals)
        st.plotly_chart(fig_deals, use_container_width=True, config=CHART_CFG)
    else:
        st.info("No deals data for this period.")

with col_book:
    if len(bookings_plot) > 0:
        fig_book = px.bar(bookings_plot, x=activity_dim, y="bookings_count",
                          title="Confirmed Bookings",
                          labels={activity_dim: "", "bookings_count": "Bookings"},
                          color_discrete_sequence=["#22c55e"])
        fig_book.update_layout(height=320, margin=dict(t=40, b=10), showlegend=False)
        fig_book.update_xaxes(type="category")
        annotate(fig_book)
        st.plotly_chart(fig_book, use_container_width=True, config=CHART_CFG)
    else:
        st.info("No confirmed bookings data for this period.")

st.divider()
st.subheader("Segment Breakdown")

# ── Segment table (touch-level volumes + per-lead conversion rates) ───────────
seg_tbl = fdf.groupby("lead_segment").agg(
    Emails=("contacted",           "sum"),
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
