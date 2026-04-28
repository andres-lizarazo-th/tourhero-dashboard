import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Organic", layout="wide")
st.title("🌱 Organic")

sql = f"""
SELECT email, full_name, first_request_at, week_start, month_key,
  last_request_at, request_count, latest_destination, latest_budget,
  lead_segment, current_pipeline_stage,
  has_deal_created, last_contacted_at, last_reply_at,
  first_deal_at, latest_deal_status_category,
  total_confirmed_guests, total_est_gbv, converted, days_request_to_deal
FROM `{PROJECT}`.operations.v_organic_pipeline
"""
df = query(sql)
df["first_request_at"] = pd.to_datetime(df["first_request_at"], utc=True, errors="coerce")

with st.sidebar:
    st.header("Filters")
    granularity = st.radio("Granularity", ["Weekly","Monthly"], horizontal=True)
    converted   = st.selectbox("Converted", ["All","Yes","No"])
    dests       = st.multiselect("Destination", sorted(df["latest_destination"].dropna().unique()))
    stages      = st.multiselect("Stage", sorted(df["current_pipeline_stage"].dropna().unique()))

fdf = df.copy()
if converted == "Yes": fdf = fdf[fdf["converted"]==True]
if converted == "No":  fdf = fdf[fdf["converted"]==False]
if dests:  fdf = fdf[fdf["latest_destination"].isin(dests)]
if stages: fdf = fdf[fdf["current_pipeline_stage"].isin(stages)]

total_requests = int(fdf["request_count"].sum())
unique_req     = len(fdf)
conv_count     = int(fdf["converted"].sum())
conv_rate      = conv_count / unique_req * 100 if unique_req else 0
avg_days       = fdf["days_request_to_deal"].dropna().mean()

c1,c2,c3,c4 = st.columns(4)
with c1: st.metric("Trip Requests",      f'{total_requests:,}')
with c2: st.metric("Unique Requestors",  f'{unique_req:,}')
with c3: st.metric("Converted to Deal",  f'{conv_count:,}')
with c4: st.metric("Conversion Rate",    f'{conv_rate:.1f}%')
if not pd.isna(avg_days):
    st.metric("Avg Days Request → Deal", f'{avg_days:.0f}')

st.divider()

dim = "week_start" if granularity == "Weekly" else "month_key"
col1, col2 = st.columns(2)

with col1:
    ts = fdf.groupby(dim).agg(
        Requests=("request_count","sum"),
        Converted=("converted","sum")
    ).reset_index()
    fig = px.bar(ts, x=dim, y=["Requests","Converted"],
                 barmode="overlay", opacity=0.8,
                 title="Requests & Conversions per " + ("Week" if granularity=="Weekly" else "Month"),
                 color_discrete_sequence=["#6366f1","#22c55e"])
    fig.update_layout(height=300, legend_title="")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    dest = fdf.groupby("latest_destination").agg(
        Requests=("request_count","sum"),
        Converted=("converted","sum")
    ).reset_index().sort_values("Requests", ascending=False).head(15)
    fig2 = px.bar(dest, x="Requests", y="latest_destination", orientation="h",
                  title="Top 15 Destinations",
                  color_discrete_sequence=["#6366f1"])
    fig2.update_layout(height=400, margin=dict(t=30,b=10))
    st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.subheader("Organic Leads Table")

tbl = fdf[["first_request_at","full_name","email","latest_destination",
           "latest_budget","request_count","converted",
           "latest_deal_status_category","total_est_gbv","days_request_to_deal"]].copy()
tbl["first_request_at"] = tbl["first_request_at"].dt.strftime("%Y-%m-%d")
tbl = tbl.sort_values("first_request_at", ascending=False)

st.dataframe(tbl, use_container_width=True, hide_index=True,
             column_config={
                 "total_est_gbv": st.column_config.NumberColumn("Est. GBV", format="$%.0f"),
                 "converted":     st.column_config.CheckboxColumn("Converted"),
             })

