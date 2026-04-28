import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Platform Performance", layout="wide")
st.title("🏔️ Platform Performance")

sql = f"""
SELECT tour_id, tour_name, state, active_status, start_date, end_date,
  published_date, week_start, month_key, market, hero_name, lead_segment,
  hero_instagram, ig_follower_count, hero_tour_count,
  tour_gbv_usd, confirmed_gbv_usd, cancelled_gbv_usd,
  total_bookings, confirmed_bookings, cancelled_bookings,
  payout_usd, cancellation_rate_pct
FROM `{PROJECT}`.operations.v_tours_pipeline
WHERE state = 'published'
"""
df = query(sql)
df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")

with st.sidebar:
    st.header("Filters")
    granularity = st.radio("Granularity", ["Weekly","Monthly"], horizontal=True)
    statuses  = st.multiselect("Active Status",
                               sorted(df["active_status"].dropna().unique()),
                               default=[s for s in df["active_status"].dropna().unique() if s != "cancelled"])
    segments  = st.multiselect("Segment", sorted(df["lead_segment"].dropna().unique()))
    markets   = st.multiselect("Market",  sorted(df["market"].dropna().unique()))
    excl_cancelled = st.checkbox("Exclude cancelled tours from GBV", value=True)

fdf = df.copy()
if statuses:  fdf = fdf[fdf["active_status"].isin(statuses)]
if segments:  fdf = fdf[fdf["lead_segment"].isin(segments)]
if markets:   fdf = fdf[fdf["market"].isin(markets)]
if excl_cancelled: fdf_gbv = fdf[fdf["active_status"] != "cancelled"]
else:              fdf_gbv = fdf

c1,c2,c3,c4,c5 = st.columns(5)
with c1: st.metric("Published Tours",   f'{fdf["tour_id"].nunique():,}')
with c2: st.metric("Completed",         f'{(fdf["active_status"]=="done").sum():,}')
with c3: st.metric("Confirmed Bookings",f'{int(fdf_gbv["confirmed_bookings"].sum()):,}')
with c4: st.metric("Confirmed GBV",     f'${fdf_gbv["confirmed_gbv_usd"].sum():,.0f}')
with c5: st.metric("Avg Cancel Rate",   f'{fdf["cancellation_rate_pct"].mean():.1f}%')

# Retention
total_h  = fdf["hero_name"].nunique()
repeat_h = fdf[fdf["hero_tour_count"] >= 2]["hero_name"].nunique()
st.metric("Hero Retention (2+ tours)", f'{repeat_h/total_h*100:.1f}%' if total_h else "—")

st.divider()

dim = "week_start" if granularity == "Weekly" else "month_key"
col1, col2 = st.columns(2)

with col1:
    ts = fdf.groupby(dim)["tour_id"].nunique().reset_index(name="tours")
    fig = px.bar(ts, x=dim, y="tours", title="Tours Published per " + ("Week" if granularity=="Weekly" else "Month"),
                 color_discrete_sequence=["#6366f1"],
                 labels={dim:"Period","tours":"Tours"})
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    gbv_ts = fdf_gbv.groupby(dim)["confirmed_gbv_usd"].sum().reset_index()
    fig2 = px.bar(gbv_ts, x=dim, y="confirmed_gbv_usd",
                  title="Confirmed GBV per " + ("Week" if granularity=="Weekly" else "Month"),
                  color_discrete_sequence=["#22c55e"],
                  labels={dim:"Period","confirmed_gbv_usd":"GBV (USD)"})
    fig2.update_layout(height=300, yaxis_tickprefix="$", yaxis_tickformat=",.0f")
    st.plotly_chart(fig2, use_container_width=True)

col3, col4 = st.columns(2)
with col3:
    status_counts = fdf["active_status"].value_counts().reset_index()
    status_counts.columns = ["status","count"]
    fig3 = px.pie(status_counts, names="status", values="count",
                  title="Tours by Status", hole=0.4)
    fig3.update_layout(height=300)
    st.plotly_chart(fig3, use_container_width=True)

with col4:
    gbv_status = fdf_gbv.groupby("active_status")["confirmed_gbv_usd"].sum().reset_index()
    fig4 = px.bar(gbv_status.sort_values("confirmed_gbv_usd", ascending=True),
                  x="confirmed_gbv_usd", y="active_status", orientation="h",
                  title="Confirmed GBV by Status",
                  color_discrete_sequence=["#f59e0b"],
                  labels={"confirmed_gbv_usd":"GBV (USD)","active_status":"Status"})
    fig4.update_layout(height=300, xaxis_tickprefix="$", xaxis_tickformat=",.0f")
    st.plotly_chart(fig4, use_container_width=True)

st.divider()
st.subheader("Top Heroes by GBV")
top_h = (fdf_gbv.groupby("hero_name")
         .agg(Tours=("tour_id","nunique"), GBV=("confirmed_gbv_usd","sum"),
              Bookings=("confirmed_bookings","sum"), Payout=("payout_usd","sum"))
         .sort_values("GBV", ascending=False).head(20).reset_index())
st.dataframe(top_h, use_container_width=True, hide_index=True,
             column_config={
                 "GBV":    st.column_config.NumberColumn("Confirmed GBV", format="$%.0f"),
                 "Payout": st.column_config.NumberColumn("Payout",        format="$%.0f"),
             })

st.divider()
st.subheader("Tour Detail Table")
tbl = fdf[["tour_name","state","active_status","start_date","hero_name","lead_segment",
           "confirmed_bookings","cancelled_bookings","confirmed_gbv_usd",
           "cancellation_rate_pct","payout_usd"]].copy()
tbl = tbl.sort_values("confirmed_gbv_usd", ascending=False)
st.dataframe(tbl, use_container_width=True, hide_index=True,
             column_config={
                 "confirmed_gbv_usd":     st.column_config.NumberColumn("GBV",    format="$%.0f"),
                 "payout_usd":            st.column_config.NumberColumn("Payout", format="$%.0f"),
                 "cancellation_rate_pct": st.column_config.NumberColumn("Cancel%",format="%.1f%%"),
             })

st.download_button(
    "📥 Download tour detail (CSV)",
    tbl.to_csv(index=False).encode("utf-8"),
    file_name=f"tours_{pd.Timestamp.today().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)
