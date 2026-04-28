import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Deals & Revenue", layout="wide")
st.title("💰 Deals & Revenue")

sql = f"""
SELECT deal_id, hero_email, hero_first_name, lead_segment, trip_name,
  countries, week_start, month_key, deal_created_at,
  deal_status, deal_status_category, deal_tier, deal_channel,
  est_gbv, confirmed_guests, quote_count,
  pending_quote_count, sent_to_hero_quote_count,
  approved_quote_count, rejected_quote_count,
  quote_gbv_usd, first_quote_at, latest_quote_at
FROM `{PROJECT}`.operations.v_deals_pipeline
"""
df = query(sql)
df["deal_created_at"] = pd.to_datetime(df["deal_created_at"], utc=True)
df["week_start"]      = pd.to_datetime(df["week_start"])

with st.sidebar:
    st.header("Filters")
    days = st.slider("Days back (from deal created)", 30, 730, 365)
    statuses  = st.multiselect("Status",  sorted(df["deal_status_category"].dropna().unique()))
    tiers     = st.multiselect("Tier",    sorted(df["deal_tier"].dropna().unique()))
    segments  = st.multiselect("Segment", sorted(df["lead_segment"].dropna().unique()))
    channels  = st.multiselect("Channel", sorted(df["deal_channel"].dropna().unique()))
    granularity = st.radio("Granularity", ["Weekly","Monthly"], horizontal=True)

cutoff = pd.Timestamp.today(tz="UTC") - pd.Timedelta(days=days)
fdf = df[df["deal_created_at"] >= cutoff]
if statuses: fdf = fdf[fdf["deal_status_category"].isin(statuses)]
if tiers:    fdf = fdf[fdf["deal_tier"].isin(tiers)]
if segments: fdf = fdf[fdf["lead_segment"].isin(segments)]
if channels: fdf = fdf[fdf["deal_channel"].isin(channels)]

c1,c2,c3,c4,c5 = st.columns(5)
published = (fdf["deal_status_category"]=="Published").sum()
with c1: st.metric("Total Deals",      f'{len(fdf):,}')
with c2: st.metric("Est. GBV",         f'${fdf["est_gbv"].sum():,.0f}')
with c3: st.metric("Quote GBV",        f'${fdf["quote_gbv_usd"].sum():,.0f}')
with c4: st.metric("Published",        f'{int(published):,}')
with c5: st.metric("Win Rate",         f'{published/len(fdf)*100:.1f}%' if len(fdf) else "—")

st.divider()

dim = "week_start" if granularity == "Weekly" else "month_key"
col1, col2 = st.columns(2)
with col1:
    ts = fdf.groupby([dim,"deal_status_category"])["deal_id"].count().reset_index(name="count")
    fig = px.bar(ts, x=dim, y="count", color="deal_status_category",
                 title="Deals per " + ("Week" if granularity=="Weekly" else "Month"),
                 labels={dim:"Period","count":"Deals"})
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    gbv_ts = fdf.groupby(dim)["est_gbv"].sum().reset_index()
    fig2 = px.bar(gbv_ts, x=dim, y="est_gbv",
                  title="Est. GBV per " + ("Week" if granularity=="Weekly" else "Month"),
                  labels={dim:"Period","est_gbv":"Est. GBV (USD)"},
                  color_discrete_sequence=["#22c55e"])
    fig2.update_layout(height=300, yaxis_tickprefix="$", yaxis_tickformat=",.0f")
    st.plotly_chart(fig2, use_container_width=True)

col3, col4 = st.columns(2)
with col3:
    status_pie = fdf["deal_status_category"].value_counts().reset_index()
    status_pie.columns = ["status","count"]
    fig3 = px.pie(status_pie, names="status", values="count",
                  title="Deals by Status", hole=0.4)
    fig3.update_layout(height=300)
    st.plotly_chart(fig3, use_container_width=True)

with col4:
    tier_ch = fdf.groupby(["deal_tier","deal_channel"])["deal_id"].count().reset_index(name="count")
    fig4 = px.bar(tier_ch, x="deal_tier", y="count", color="deal_channel",
                  title="Deals by Tier & Channel", barmode="stack",
                  labels={"count":"Deals"})
    fig4.update_layout(height=300)
    st.plotly_chart(fig4, use_container_width=True)

st.divider()
st.subheader("Deals Table")

tbl = fdf[["deal_created_at","hero_first_name","hero_email","trip_name",
           "countries","deal_status_category","deal_tier","deal_channel",
           "lead_segment","est_gbv","quote_gbv_usd","quote_count",
           "approved_quote_count"]].copy()
tbl["deal_created_at"] = tbl["deal_created_at"].dt.tz_convert("America/Sao_Paulo").dt.strftime("%Y-%m-%d")
tbl = tbl.sort_values("deal_created_at", ascending=False)

st.dataframe(tbl, use_container_width=True, hide_index=True,
             column_config={
                 "est_gbv":       st.column_config.NumberColumn("Est. GBV",   format="$%.0f"),
                 "quote_gbv_usd": st.column_config.NumberColumn("Quote GBV",  format="$%.0f"),
             })

st.download_button(
    "📥 Download deals table (CSV)",
    tbl.to_csv(index=False).encode("utf-8"),
    file_name=f"deals_{pd.Timestamp.today().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)
