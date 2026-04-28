import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Campaigns", layout="wide")
st.title("📧 Campaigns")

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
  campaign_type, campaign_status,
  sent, total_opens, unique_opens, replied, bounced, unsubscribed, interested,
  open_rate_pct, reply_rate_pct, bounce_rate_pct, unsub_rate_pct
FROM `{PROJECT}`.bison_tracking.v_campaign_performance
WHERE stat_date BETWEEN '{d_from}' AND '{d_to}'
"""
df = query(sql)
df["stat_date"]  = pd.to_datetime(df["stat_date"])
df["week_start"] = pd.to_datetime(df["week_start"])

with st.sidebar:
    campaigns = st.multiselect("Campaign", sorted(df["campaign_name"].dropna().unique()))
    statuses  = st.multiselect("Status",   sorted(df["campaign_status"].dropna().unique()))
    granularity = st.radio("Granularity", ["Weekly","Monthly"], horizontal=True)

fdf = df.copy()
if campaigns: fdf = fdf[fdf["campaign_name"].isin(campaigns)]
if statuses:  fdf = fdf[fdf["campaign_status"].isin(statuses)]

st.caption(f"📅 {d_from} → {d_to} · Granularity: **{granularity}**")

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

c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: st.metric("Emails Sent",   f'{total_sent:,}')
with c2: st.metric("Replies",       f'{total_replied:,}')
with c3: st.metric("Interested",    f'{total_intd:,}')
with c4: st.metric("Reply Rate",    f'{reply_rate:.2f}%')
with c5: st.metric("Bounce Rate",   f'{bounce_rate:.2f}%')
with c6: st.metric("Unsub Rate",    f'{unsub_rate:.2f}%')
st.caption("ℹ️ Open rate not available — Bison API does not provide open tracking data.")

st.divider()

# ── Time series ───────────────────────────────────────────────────────────────
dim = "week_start" if granularity == "Weekly" else "month_key"
ts = fdf.groupby(dim)[["sent","replied"]].sum().reset_index()

col1, col2 = st.columns(2)
with col1:
    fig = px.line(ts, x=dim, y=["sent","replied"],
                  title="Email Volume per " + ("Week" if granularity=="Weekly" else "Month"),
                  labels={"value":"count", dim:"Period"},
                  color_discrete_sequence=["#6366f1","#22c55e"], markers=True)
    fig.update_layout(height=320, legend_title="")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    # Recalculate rates from sums to avoid outlier daily rates distorting the average
    rates = fdf.groupby(dim)[["sent","replied","bounced","unsubscribed"]].sum().reset_index()
    rates["Reply %"]  = (rates["replied"]      / rates["sent"] * 100).where(rates["sent"] > 0)
    rates["Bounce %"] = (rates["bounced"]      / rates["sent"] * 100).where(rates["sent"] > 0)
    rates["Unsub %"]  = (rates["unsubscribed"] / rates["sent"] * 100).where(rates["sent"] > 0)
    fig2 = px.line(rates, x=dim, y=["Reply %","Bounce %","Unsub %"],
                   title="Rates per " + ("Week" if granularity=="Weekly" else "Month") + " (%)",
                   labels={"value":"%", dim:"Period"},
                   color_discrete_sequence=["#22c55e","#ef4444","#f59e0b"], markers=True)
    fig2.update_layout(height=320, legend_title="",
                       yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.subheader("Campaign Performance Table")

camp_tbl = fdf[fdf["sent"] > 0].groupby("campaign_name").agg(
    Sent=("sent","sum"),
    Replies=("replied","sum"),
    Bounced=("bounced","sum"),
    Unsubs=("unsubscribed","sum"),
    Interested=("interested","sum"),
).reset_index()
camp_tbl["Reply%"]  = (camp_tbl["Replies"] / camp_tbl["Sent"] * 100).round(2)
camp_tbl["Bounce%"] = (camp_tbl["Bounced"] / camp_tbl["Sent"] * 100).round(2)
camp_tbl["Unsub%"]  = (camp_tbl["Unsubs"]  / camp_tbl["Sent"] * 100).round(2)
camp_tbl = camp_tbl[camp_tbl["Sent"] > 0].sort_values("Reply%", ascending=False)

st.caption("⚠️ Open rate omitted — Bison API does not track email opens.")
st.dataframe(camp_tbl, use_container_width=True, hide_index=True,
             column_config={
                 "Reply%":  st.column_config.NumberColumn("Reply%",  format="%.2f%%"),
                 "Bounce%": st.column_config.NumberColumn("Bounce%", format="%.2f%%"),
                 "Unsub%":  st.column_config.NumberColumn("Unsub%",  format="%.2f%%"),
             })

st.download_button(
    "📥 Download campaign performance (CSV)",
    camp_tbl.to_csv(index=False).encode("utf-8"),
    file_name=f"campaigns_{d_from}_to_{d_to}.csv",
    mime="text/csv",
)
