import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Funnel Overview", layout="wide")
st.title("🔽 Funnel Overview")

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
    granularity = st.radio("Granularity", ["Weekly","Monthly"], horizontal=True)

if isinstance(date_range, tuple) and len(date_range) == 2:
    d_from, d_to = date_range
else:
    d_from, d_to = ytd_start, today

# ── Load ──────────────────────────────────────────────────────────────────────
sql = f"""
SELECT lead_segment, cohort_week, month_key,
  SUM(leads_count) as leads_count,
  SUM(contacted)   as contacted,
  SUM(replied)     as replied,
  SUM(called)      as called,
  SUM(dealt)       as dealt,
  SUM(vip_dealt)   as vip_dealt,
  SUM(onboarding_called) as onboarding_called,
  SUM(planning_called)   as planning_called,
  SUM(onboarding_within_30d)         as onboarding_within_30d,
  SUM(deal_within_30d_of_onboarding) as deal_within_30d_of_onboarding
FROM `{PROJECT}`.analytics.v_funnel_by_segment
WHERE cohort_week BETWEEN '{d_from}' AND '{d_to}'
GROUP BY 1,2,3
"""
df = query(sql)

# Segment chips (quick filter at top)
all_segs = sorted(df["lead_segment"].dropna().unique())
with st.sidebar:
    segs = st.multiselect("Segment", all_segs, default=all_segs)

fdf = df[df["lead_segment"].isin(segs)] if segs else df

st.caption(f"📅 {d_from} → {d_to} · Granularity: **{granularity}** · Segments: **{', '.join(segs) if len(segs) < len(all_segs) else 'all'}**")

# ── Volume scorecards ─────────────────────────────────────────────────────────
contacted = int(fdf["contacted"].sum())
replied   = int(fdf["replied"].sum())
called    = int(fdf["called"].sum())
onb       = int(fdf["onboarding_called"].sum())
dealt     = int(fdf["dealt"].sum())
onb_30d   = int(fdf["onboarding_within_30d"].sum())
deal_30d  = int(fdf["deal_within_30d_of_onboarding"].sum())

st.markdown("**Volumes**")
v1,v2,v3,v4,v5 = st.columns(5)
with v1: st.metric("Outreach Touches", f"{contacted:,}",
                   help="Each (lead × campaign) first-send counts as one touch.")
with v2: st.metric("Replied",          f"{replied:,}")
with v3: st.metric("Calls Booked",     f"{called:,}")
with v4: st.metric("Onboarding Calls", f"{onb:,}")
with v5: st.metric("Deals Created",    f"{dealt:,}")

# ── Conversion rate scorecards ────────────────────────────────────────────────
reply_rt   = replied / contacted * 100 if contacted else 0
call_rt    = called  / replied   * 100 if replied   else 0
deal_rt    = dealt   / called    * 100 if called    else 0
overall_rt = dealt   / contacted * 100 if contacted else 0
onb_rt_30d = onb_30d  / contacted * 100 if contacted else 0
deal_onb   = deal_30d / onb_30d   * 100 if onb_30d   else 0

st.markdown("**Conversion Rates**")
r1,r2,r3,r4,r5,r6 = st.columns(6)
with r1: st.metric("Reply Rate",          f"{reply_rt:.1f}%",
                   help="Replied / Outreach Touches")
with r2: st.metric("Call Rate",           f"{call_rt:.1f}%",
                   help="Calls / Replied")
with r3: st.metric("Deal Rate",           f"{deal_rt:.1f}%",
                   help="Deals / Calls")
with r4: st.metric("Overall Conv.",       f"{overall_rt:.2f}%",
                   help="Deals / Touches (top-line funnel efficiency)")
with r5: st.metric("Onb. Rate (30d)",     f"{onb_rt_30d:.2f}%",
                   help="Of touches, % whose lead booked an onboarding call within 30 days")
with r6: st.metric("Deal from Onb. (30d)",f"{deal_onb:.1f}%",
                   help="Of leads who booked an onboarding, % converted to a deal within 30 days")

st.divider()

# ── Volume time series — separate charts per metric ──────────────────────────
dim = "cohort_week" if granularity == "Weekly" else "month_key"
ts = fdf.groupby([dim,"lead_segment"])[["contacted","replied","called","dealt"]].sum().reset_index()
ts_total = fdf.groupby(dim)[["contacted","replied","called","dealt"]].sum().reset_index()

st.markdown("**Volume Trends** (grouped by segment)")
v1, v2 = st.columns(2)
with v1:
    fig = px.line(ts, x=dim, y="contacted", color="lead_segment",
                  title="Outreach Touches",
                  labels={dim:"Period","contacted":"Touches"}, markers=True)
    fig.update_layout(height=300, legend_title="Segment")
    st.plotly_chart(fig, use_container_width=True)
with v2:
    fig = px.line(ts, x=dim, y="replied", color="lead_segment",
                  title="Replies",
                  labels={dim:"Period","replied":"Replied"}, markers=True)
    fig.update_layout(height=300, legend_title="Segment")
    st.plotly_chart(fig, use_container_width=True)

v3, v4 = st.columns(2)
with v3:
    fig = px.line(ts, x=dim, y="called", color="lead_segment",
                  title="Calls Booked",
                  labels={dim:"Period","called":"Calls"}, markers=True)
    fig.update_layout(height=300, legend_title="Segment")
    st.plotly_chart(fig, use_container_width=True)
with v4:
    fig = px.line(ts, x=dim, y="dealt", color="lead_segment",
                  title="Deals Created",
                  labels={dim:"Period","dealt":"Deals"}, markers=True)
    fig.update_layout(height=300, legend_title="Segment")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Conversion rate time series ──────────────────────────────────────────────
st.markdown("**Conversion Rate Trends** (overall, all selected segments)")

rates = ts_total.copy()
rates["Reply %"]   = (rates["replied"] / rates["contacted"] * 100).where(rates["contacted"] > 0)
rates["Call %"]    = (rates["called"]  / rates["replied"]   * 100).where(rates["replied"]   > 0)
rates["Deal %"]    = (rates["dealt"]   / rates["called"]    * 100).where(rates["called"]    > 0)
rates["Overall %"] = (rates["dealt"]   / rates["contacted"] * 100).where(rates["contacted"] > 0)

c1, c2 = st.columns(2)
with c1:
    fig_funnel = px.line(rates, x=dim, y=["Reply %","Call %","Deal %"],
                         title="Funnel Step Conversion (per period)",
                         labels={"value":"%", dim:"Period","variable":"Stage"},
                         color_discrete_sequence=["#22c55e","#f59e0b","#ef4444"], markers=True)
    fig_funnel.update_layout(height=320, legend_title="",
                             yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig_funnel, use_container_width=True)

with c2:
    fig_overall = px.line(rates, x=dim, y="Overall %",
                          title="Overall Conversion (Deals / Touches)",
                          labels={"Overall %":"%", dim:"Period"},
                          color_discrete_sequence=["#6366f1"], markers=True)
    fig_overall.update_layout(height=320,
                              yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig_overall, use_container_width=True)

# Cohort 30d rates over time
cohort = ts_total.copy()
# Need onboarding_within_30d & deal_within_30d_of_onboarding aggregated
cohort_extra = (fdf.groupby(dim)[["onboarding_within_30d","deal_within_30d_of_onboarding"]]
                .sum().reset_index())
cohort = cohort.merge(cohort_extra, on=dim, how="left")
cohort["Onb 30d %"]      = (cohort["onboarding_within_30d"]         / cohort["contacted"] * 100).where(cohort["contacted"] > 0)
cohort["Deal/Onb 30d %"] = (cohort["deal_within_30d_of_onboarding"] / cohort["onboarding_within_30d"] * 100).where(cohort["onboarding_within_30d"] > 0)

fig_cohort = px.line(cohort, x=dim, y=["Onb 30d %","Deal/Onb 30d %"],
                     title="Cohort 30-Day Conversion Rates (per period)",
                     labels={"value":"%", dim:"Period","variable":"Metric"},
                     color_discrete_sequence=["#f59e0b","#ef4444"], markers=True)
fig_cohort.update_layout(height=300, legend_title="",
                         yaxis=dict(ticksuffix="%"))
st.plotly_chart(fig_cohort, use_container_width=True)

st.divider()
st.subheader("Segment Breakdown")

# ── Segment table ─────────────────────────────────────────────────────────────
seg_tbl = fdf.groupby("lead_segment").agg(
    Touches=("contacted","sum"),
    Replied=("replied","sum"),
    Calls=("called","sum"),
    Onboarding=("onboarding_called","sum"),
    Planning=("planning_called","sum"),
    Deals=("dealt","sum"),
    VIP_Deals=("vip_dealt","sum"),
    Onb_30d=("onboarding_within_30d","sum"),
    Deal_Onb_30d=("deal_within_30d_of_onboarding","sum"),
).reset_index()

seg_tbl["Reply%"]    = (seg_tbl["Replied"] / seg_tbl["Touches"] * 100).round(1)
seg_tbl["Call%"]     = (seg_tbl["Calls"]   / seg_tbl["Replied"] * 100).round(1)
seg_tbl["Deal%"]     = (seg_tbl["Deals"]   / seg_tbl["Calls"]   * 100).round(1)
seg_tbl["Overall%"]  = (seg_tbl["Deals"]   / seg_tbl["Touches"] * 100).round(2)
seg_tbl["Onb30%"]    = (seg_tbl["Onb_30d"] / seg_tbl["Touches"] * 100).round(2)
seg_tbl = seg_tbl.sort_values("Deals", ascending=False)

st.dataframe(seg_tbl, use_container_width=True, hide_index=True,
             column_config={
                 "Reply%":   st.column_config.NumberColumn("Reply%",   format="%.1f%%"),
                 "Call%":    st.column_config.NumberColumn("Call%",    format="%.1f%%"),
                 "Deal%":    st.column_config.NumberColumn("Deal%",    format="%.1f%%"),
                 "Overall%": st.column_config.NumberColumn("Overall%", format="%.2f%%"),
                 "Onb30%":   st.column_config.NumberColumn("Onb30%",   format="%.2f%%"),
             })

st.download_button(
    "📥 Download segment breakdown (CSV)",
    seg_tbl.to_csv(index=False).encode("utf-8"),
    file_name=f"funnel_segments_{d_from}_to_{d_to}.csv",
    mime="text/csv",
)
