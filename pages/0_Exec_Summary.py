import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Exec Summary", layout="wide")
st.title("📊 Exec Summary")

# ── Sidebar: global date range + granularity ─────────────────────────────────
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
    granularity = st.radio("Granularity", ["Weekly", "Monthly"], horizontal=True)

if isinstance(date_range, tuple) and len(date_range) == 2:
    d_from, d_to = date_range
else:
    d_from, d_to = ytd_start, today

st.caption(f"📅 Showing data from **{d_from}** to **{d_to}** · Granularity: **{granularity}**")

# Helper for currency / number formatting
def fmt_currency(x): return f"${x:,.0f}" if pd.notna(x) else "—"
def fmt_pct(x):      return f"{x:.1f}%" if pd.notna(x) else "—"
def fmt_num(x):      return f"{int(x):,}" if pd.notna(x) else "—"

# ═════════════════════════════════════════════════════════════════════════════
# SECTION A — Pipeline Funnel & Conversion Rates (v_funnel_by_segment)
# ═════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("A · Pipeline Funnel & Conversion Rates")

funnel_sql = f"""
SELECT cohort_week, month_key, lead_segment,
  SUM(leads_count)            AS leads,
  SUM(contacted)              AS contacted,
  SUM(replied)                AS replied,
  SUM(called)                 AS called,
  SUM(onboarding_called)      AS onboarding_called,
  SUM(planning_called)        AS planning_called,
  SUM(dealt)                  AS dealt,
  SUM(onboarding_within_30d)  AS onb_30d,
  SUM(deal_within_30d_of_onboarding) AS deal_30d
FROM `{PROJECT}`.analytics.v_funnel_by_segment
WHERE cohort_week BETWEEN '{d_from}' AND '{d_to}'
GROUP BY 1, 2, 3
"""
funnel = query(funnel_sql)

# Aggregate totals for scorecards
contacted = int(funnel["contacted"].sum())
replied   = int(funnel["replied"].sum())
called    = int(funnel["called"].sum())
onb       = int(funnel["onboarding_called"].sum())
dealt     = int(funnel["dealt"].sum())
onb_30d   = int(funnel["onb_30d"].sum())
deal_30d  = int(funnel["deal_30d"].sum())

# Conversion rates
reply_rate     = replied / contacted * 100 if contacted else 0
call_rate      = called  / replied   * 100 if replied   else 0
deal_rate      = dealt   / called    * 100 if called    else 0
onb_rate_30d   = onb_30d  / contacted * 100 if contacted else 0
deal_from_onb  = deal_30d / onb_30d   * 100 if onb_30d   else 0

# Row 1 — Volumes
st.markdown("**Volumes**")
v1, v2, v3, v4, v5 = st.columns(5)
with v1: st.metric("Contacted",        fmt_num(contacted))
with v2: st.metric("Replied",          fmt_num(replied))
with v3: st.metric("Calls Booked",     fmt_num(called))
with v4: st.metric("Onboarding Calls", fmt_num(onb))
with v5: st.metric("Deals Created",    fmt_num(dealt))

# Row 2 — Conversion rates
st.markdown("**Conversion Rates**")
r1, r2, r3, r4, r5 = st.columns(5)
with r1: st.metric("Contact → Reply",          fmt_pct(reply_rate))
with r2: st.metric("Reply → Call",             fmt_pct(call_rate))
with r3: st.metric("Call → Deal",              fmt_pct(deal_rate))
with r4: st.metric("Onboarding Rate (30d)",    fmt_pct(onb_rate_30d),
                   help="Of leads first contacted in the period, % who booked an onboarding call within 30 days")
with r5: st.metric("Deal from Onboarding (30d)", fmt_pct(deal_from_onb),
                   help="Of leads who booked an onboarding call, % who got a deal created within 30 days")

# Time series — separate charts per metric (volume scales differ wildly)
dim = "cohort_week" if granularity == "Weekly" else "month_key"
ts = funnel.groupby(dim)[["contacted","replied","called","dealt"]].sum().reset_index()

a1, a2 = st.columns(2)
with a1:
    fig = px.bar(ts, x=dim, y="contacted",
                 title="Contacted per " + ("Week" if granularity=="Weekly" else "Month"),
                 labels={dim:"Period","contacted":"Leads"},
                 color_discrete_sequence=["#6366f1"])
    fig.update_layout(height=260, margin=dict(t=40,b=20))
    st.plotly_chart(fig, use_container_width=True)
with a2:
    fig = px.bar(ts, x=dim, y="replied",
                 title="Replied per " + ("Week" if granularity=="Weekly" else "Month"),
                 labels={dim:"Period","replied":"Leads"},
                 color_discrete_sequence=["#22c55e"])
    fig.update_layout(height=260, margin=dict(t=40,b=20))
    st.plotly_chart(fig, use_container_width=True)

a3, a4 = st.columns(2)
with a3:
    fig = px.bar(ts, x=dim, y="called",
                 title="Calls Booked per " + ("Week" if granularity=="Weekly" else "Month"),
                 labels={dim:"Period","called":"Calls"},
                 color_discrete_sequence=["#f59e0b"])
    fig.update_layout(height=260, margin=dict(t=40,b=20))
    st.plotly_chart(fig, use_container_width=True)
with a4:
    fig = px.bar(ts, x=dim, y="dealt",
                 title="Deals Created per " + ("Week" if granularity=="Weekly" else "Month"),
                 labels={dim:"Period","dealt":"Deals"},
                 color_discrete_sequence=["#ef4444"])
    fig.update_layout(height=260, margin=dict(t=40,b=20))
    st.plotly_chart(fig, use_container_width=True)

# Conversion rate trends — all on the same 0-100% scale, can share one chart
st.markdown("**Conversion Rate Trends**")
rates_ts = ts.copy()
rates_ts["Reply Rate %"]  = (rates_ts["replied"] / rates_ts["contacted"] * 100).where(rates_ts["contacted"] > 0)
rates_ts["Call Rate %"]   = (rates_ts["called"]  / rates_ts["replied"]   * 100).where(rates_ts["replied"]   > 0)
rates_ts["Deal Rate %"]   = (rates_ts["dealt"]   / rates_ts["called"]    * 100).where(rates_ts["called"]    > 0)
rates_ts["Overall Conv %"] = (rates_ts["dealt"]  / rates_ts["contacted"] * 100).where(rates_ts["contacted"] > 0)

fig_rates = px.line(rates_ts, x=dim,
                    y=["Reply Rate %","Call Rate %","Deal Rate %","Overall Conv %"],
                    title="Funnel Conversion Rates per " + ("Week" if granularity=="Weekly" else "Month"),
                    labels={"value":"%", dim:"Period","variable":"Metric"},
                    color_discrete_sequence=["#22c55e","#f59e0b","#ef4444","#6366f1"],
                    markers=True)
fig_rates.update_layout(height=320, margin=dict(t=40,b=20),
                        yaxis=dict(ticksuffix="%"), legend_title="")
st.plotly_chart(fig_rates, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# SECTION B — Revenue Efficiency (v_deals_pipeline)
# ═════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("B · Revenue Efficiency")

deals_sql = f"""
SELECT deal_id, deal_status_category, deal_channel, deal_tier,
  est_gbv, quote_gbv_usd, quote_revenue_usd,
  deal_created_at, week_start, month_key
FROM `{PROJECT}`.operations.v_deals_pipeline
WHERE DATE(deal_created_at) BETWEEN '{d_from}' AND '{d_to}'
"""
deals = query(deals_sql)
deals["deal_created_at"] = pd.to_datetime(deals["deal_created_at"], utc=True)

total_deals = len(deals)
published   = (deals["deal_status_category"] == "Published").sum()
win_rate    = published / total_deals * 100 if total_deals else 0
total_gbv   = deals["est_gbv"].sum()
total_quote = deals["quote_revenue_usd"].sum() if "quote_revenue_usd" in deals.columns else 0
avg_gbv     = deals["est_gbv"].mean() if total_deals else 0

c1,c2,c3,c4,c5 = st.columns(5)
with c1: st.metric("Total Deals",       fmt_num(total_deals))
with c2: st.metric("Published Deals",   fmt_num(published))
with c3: st.metric("Win Rate",          fmt_pct(win_rate))
with c4: st.metric("Avg GBV / Deal",    fmt_currency(avg_gbv))
with c5: st.metric("Total Est. GBV",    fmt_currency(total_gbv))

dim_b = "week_start" if granularity == "Weekly" else "month_key"
deals_ts = deals.groupby(dim_b).agg(
    deals=("deal_id","count"),
    est_gbv=("est_gbv","sum"),
).reset_index()

b1, b2 = st.columns(2)
with b1:
    fig = px.bar(deals_ts, x=dim_b, y="deals",
                 title="Deals Created per " + ("Week" if granularity=="Weekly" else "Month"),
                 labels={dim_b:"Period","deals":"Deals"},
                 color_discrete_sequence=["#6366f1"])
    fig.update_layout(height=260, margin=dict(t=40,b=20))
    st.plotly_chart(fig, use_container_width=True)
with b2:
    fig = px.bar(deals_ts, x=dim_b, y="est_gbv",
                 title="Est. GBV per " + ("Week" if granularity=="Weekly" else "Month"),
                 labels={dim_b:"Period","est_gbv":"GBV (USD)"},
                 color_discrete_sequence=["#22c55e"])
    fig.update_layout(height=260, margin=dict(t=40,b=20),
                      yaxis_tickprefix="$", yaxis_tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True)

b3, b4 = st.columns(2)
with b3:
    if total_deals:
        wr_ch = (deals.groupby("deal_channel")
                 .apply(lambda x: (x["deal_status_category"]=="Published").sum() / len(x) * 100)
                 .reset_index(name="win_rate")
                 .sort_values("win_rate", ascending=True))
        fig = px.bar(wr_ch, x="win_rate", y="deal_channel", orientation="h",
                     title="Win Rate by Channel (%)",
                     labels={"win_rate":"%","deal_channel":""},
                     color_discrete_sequence=["#6366f1"])
        fig.update_layout(height=260, margin=dict(t=40,b=20))
        st.plotly_chart(fig, use_container_width=True)
with b4:
    if total_deals:
        wr_tier = (deals.groupby("deal_tier")
                   .apply(lambda x: (x["deal_status_category"]=="Published").sum() / len(x) * 100)
                   .reset_index(name="win_rate")
                   .sort_values("win_rate", ascending=True))
        fig = px.bar(wr_tier, x="win_rate", y="deal_tier", orientation="h",
                     title="Win Rate by Tier (%)",
                     labels={"win_rate":"%","deal_tier":""},
                     color_discrete_sequence=["#22c55e"])
        fig.update_layout(height=260, margin=dict(t=40,b=20))
        st.plotly_chart(fig, use_container_width=True)

# Win Rate trend over time
if total_deals:
    wr_ts = (deals.assign(period=deals[dim_b])
             .groupby("period")
             .apply(lambda x: pd.Series({
                 "deals": len(x),
                 "published": (x["deal_status_category"]=="Published").sum(),
             }))
             .reset_index())
    wr_ts["Win Rate %"] = (wr_ts["published"] / wr_ts["deals"] * 100).where(wr_ts["deals"] > 0)
    fig_wr = px.line(wr_ts, x="period", y="Win Rate %",
                     title="Win Rate Trend per " + ("Week" if granularity=="Weekly" else "Month"),
                     labels={"period":"Period"},
                     color_discrete_sequence=["#22c55e"], markers=True)
    fig_wr.update_layout(height=280, margin=dict(t=40,b=20),
                         yaxis=dict(ticksuffix="%", range=[0,100]))
    st.plotly_chart(fig_wr, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# SECTION C — Hero Retention (v_tours_pipeline)
# ═════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("C · Hero Retention")

tours_sql = f"""
SELECT hero_name, hero_tour_count, confirmed_gbv_usd, tour_id, published_date
FROM `{PROJECT}`.operations.v_tours_pipeline
WHERE state = 'published'
  AND DATE(published_date) BETWEEN '{d_from}' AND '{d_to}'
"""
tours = query(tours_sql)

total_heroes  = tours["hero_name"].nunique() if len(tours) else 0
repeat_heroes = tours[tours["hero_tour_count"] >= 2]["hero_name"].nunique() if len(tours) else 0
retention_pct = repeat_heroes / total_heroes * 100 if total_heroes else 0
avg_tours_per_hero = (tours.groupby("hero_name")["tour_id"].nunique().mean()
                      if total_heroes else 0)

c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Total Heroes (period)",  fmt_num(total_heroes))
with c2: st.metric("Repeat Heroes (2+ tours)", fmt_num(repeat_heroes))
with c3: st.metric("Hero Retention",          fmt_pct(retention_pct))
with c4: st.metric("Avg Tours / Hero",        f"{avg_tours_per_hero:.2f}" if avg_tours_per_hero else "—")

if len(tours):
    top10 = (tours.groupby("hero_name")
             .agg(tours_count=("tour_id","nunique"), confirmed_gbv=("confirmed_gbv_usd","sum"))
             .sort_values("confirmed_gbv", ascending=True).tail(10).reset_index())
    fig = px.bar(top10, x="confirmed_gbv", y="hero_name", orientation="h",
                 title="Top 10 Heroes by Confirmed GBV (in period)",
                 labels={"confirmed_gbv":"Confirmed GBV (USD)","hero_name":""},
                 color_discrete_sequence=["#f59e0b"])
    fig.update_layout(height=320, margin=dict(t=40,b=20),
                      xaxis_tickprefix="$", xaxis_tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No published tours in the selected date range.")

# ═════════════════════════════════════════════════════════════════════════════
# SECTION D — Campaign Health (v_campaign_performance)
# ═════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("D · Campaign Health")

camp_sql = f"""
SELECT campaign_id, campaign_name, campaign_status,
  SUM(sent)        AS total_sent,
  SUM(replied)     AS total_replied,
  SUM(bounced)     AS total_bounced
FROM `{PROJECT}`.bison_tracking.v_campaign_performance
WHERE stat_date BETWEEN '{d_from}' AND '{d_to}'
GROUP BY 1, 2, 3
"""
camp = query(camp_sql)

if len(camp):
    camp["reply_rate_pct"]  = camp["total_replied"] / camp["total_sent"].replace(0, pd.NA) * 100
    camp["bounce_rate_pct"] = camp["total_bounced"] / camp["total_sent"].replace(0, pd.NA) * 100

    def health(r):
        if pd.notna(r["bounce_rate_pct"]) and r["bounce_rate_pct"] > 5: return "🔴 Deliverability"
        if pd.notna(r["reply_rate_pct"])  and r["reply_rate_pct"]  < 1: return "🟡 Low Reply"
        return "🟢 Healthy"

    camp["health"] = camp.apply(health, axis=1)
    camp_active = camp[camp["total_sent"] > 0]

    n_red    = int((camp_active["health"] == "🔴 Deliverability").sum())
    n_yellow = int((camp_active["health"] == "🟡 Low Reply").sum())
    n_green  = int((camp_active["health"] == "🟢 Healthy").sum())

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Active Campaigns", fmt_num(len(camp_active)))
    with c2: st.metric("🔴 Deliverability Issues", fmt_num(n_red))
    with c3: st.metric("🟡 Low Reply Rate",        fmt_num(n_yellow))
    with c4: st.metric("🟢 Healthy",               fmt_num(n_green))

    health_counts = (camp_active["health"].value_counts()
                     .reindex(["🟢 Healthy","🟡 Low Reply","🔴 Deliverability"])
                     .fillna(0).reset_index())
    health_counts.columns = ["status","count"]

    d1, d2 = st.columns(2)
    with d1:
        fig = px.bar(health_counts, x="status", y="count",
                     color="status",
                     color_discrete_map={
                         "🔴 Deliverability":"#ef4444",
                         "🟡 Low Reply":"#f59e0b",
                         "🟢 Healthy":"#22c55e",
                     },
                     title="Campaigns by Health Status",
                     labels={"count":"Campaigns","status":""})
        fig.update_layout(height=280, showlegend=False, margin=dict(t=40,b=20))
        st.plotly_chart(fig, use_container_width=True)

    with d2:
        # Top 10 worst-bounce campaigns (deliverability watchlist)
        watch = (camp_active.sort_values("bounce_rate_pct", ascending=False)
                 .head(10)[["campaign_name","total_sent","reply_rate_pct","bounce_rate_pct","health"]])
        watch = watch.rename(columns={
            "campaign_name":"Campaign", "total_sent":"Sent",
            "reply_rate_pct":"Reply %", "bounce_rate_pct":"Bounce %", "health":"Status"
        })
        st.dataframe(
            watch, use_container_width=True, hide_index=True,
            column_config={
                "Reply %":  st.column_config.NumberColumn("Reply %",  format="%.2f%%"),
                "Bounce %": st.column_config.NumberColumn("Bounce %", format="%.2f%%"),
            }
        )
else:
    st.info("No campaign activity in the selected date range.")
