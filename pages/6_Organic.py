import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Organic", layout="wide")

st.markdown("""
<style>
[data-testid="stElementToolbar"] {display: none !important;}
[data-testid="stDownloadButton"] {display: none !important;}
</style>
""", unsafe_allow_html=True)

CHART_CFG = {"displayModeBar": False}

st.title("Organic")

sql = f"""
SELECT email, full_name, first_request_at, week_start, month_key,
  last_request_at, request_count, latest_destination, latest_budget,
  lead_segment, current_pipeline_stage,
  has_deal_created, last_contacted_at, last_reply_at,
  first_deal_at, latest_deal_status_category,
  total_confirmed_guests, total_est_gbv, converted, days_request_to_deal,
  qualifying_answer, group_min_size, group_max_size,
  tracking_referrer_type, tracking_referrer_domain,
  tracking_landing_page, tracking_bd_track
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
    qualifs     = st.multiselect("Qualifying Answer", sorted(df["qualifying_answer"].dropna().unique()))
    ref_types   = st.multiselect("Referrer Type", sorted(df["tracking_referrer_type"].dropna().unique()))

fdf = df.copy()
if converted == "Yes": fdf = fdf[fdf["converted"]==True]
if converted == "No":  fdf = fdf[fdf["converted"]==False]
if dests:     fdf = fdf[fdf["latest_destination"].isin(dests)]
if stages:    fdf = fdf[fdf["current_pipeline_stage"].isin(stages)]
if qualifs:   fdf = fdf[fdf["qualifying_answer"].isin(qualifs)]
if ref_types: fdf = fdf[fdf["tracking_referrer_type"].isin(ref_types)]

# ── Scorecards ────────────────────────────────────────────────────────────────
total_requests = int(fdf["request_count"].sum())
unique_req     = len(fdf)
conv_count     = int(fdf["converted"].sum())
conv_rate      = conv_count / unique_req * 100 if unique_req else 0
avg_days       = fdf["days_request_to_deal"].dropna().mean()
bd_driven      = int(fdf["tracking_bd_track"].notna().sum())

c1,c2,c3,c4,c5 = st.columns(5)
with c1: st.metric("Trip Requests",      f'{total_requests:,}')
with c2: st.metric("Unique Requestors",  f'{unique_req:,}')
with c3: st.metric("Converted to Deal",  f'{conv_count:,}')
with c4: st.metric("Conversion Rate",    f'{conv_rate:.1f}%')
with c5: st.metric("BD-Driven Requests", f'{bd_driven:,}',
                   help="Requests where a BD campaign link (tracking_bd_track) was captured")
if not pd.isna(avg_days):
    st.metric("Avg Days Request → Deal", f'{avg_days:.0f}')

st.divider()

# ── Volume trends + Destinations ─────────────────────────────────────────────
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
    st.plotly_chart(fig, use_container_width=True, config=CHART_CFG)

with col2:
    dest = fdf.groupby("latest_destination").agg(
        Requests=("request_count","sum"),
        Converted=("converted","sum")
    ).reset_index().sort_values("Requests", ascending=False).head(15)
    fig2 = px.bar(dest, x="Requests", y="latest_destination", orientation="h",
                  title="Top 15 Destinations",
                  color_discrete_sequence=["#6366f1"])
    fig2.update_layout(height=400, margin=dict(t=30,b=10))
    st.plotly_chart(fig2, use_container_width=True, config=CHART_CFG)

st.divider()

# ── Qualifying + Referrer source ──────────────────────────────────────────────
st.subheader("Lead Quality & Acquisition")
q1, q2 = st.columns(2)

with q1:
    QUALIFY_ORDER = ["I organize them for a living", "A couple of times", "Not yet, but I'd love to"]
    QUALIFY_COLORS = {
        "I organize them for a living": "#22c55e",
        "A couple of times":            "#f59e0b",
        "Not yet, but I'd love to":     "#94a3b8",
    }
    qual = fdf["qualifying_answer"].value_counts().reset_index()
    qual.columns = ["qualifying_answer", "count"]
    qual["qualifying_answer"] = pd.Categorical(qual["qualifying_answer"],
                                               categories=QUALIFY_ORDER, ordered=True)
    qual = qual.sort_values("qualifying_answer")
    fig3 = px.bar(qual, x="count", y="qualifying_answer", orientation="h",
                  title="Qualifying Answer Distribution",
                  color="qualifying_answer",
                  color_discrete_map=QUALIFY_COLORS,
                  labels={"count":"Leads","qualifying_answer":"Answer"})
    fig3.update_layout(height=280, showlegend=False)
    st.plotly_chart(fig3, use_container_width=True, config=CHART_CFG)

with q2:
    ref = fdf["tracking_referrer_type"].value_counts().reset_index()
    ref.columns = ["referrer_type","count"]
    fig4 = px.pie(ref, names="referrer_type", values="count",
                  title="Referrer Type (how they found us)", hole=0.4,
                  color_discrete_sequence=px.colors.qualitative.Set2)
    fig4.update_layout(height=280)
    st.plotly_chart(fig4, use_container_width=True, config=CHART_CFG)

q3, q4 = st.columns(2)
with q3:
    dom = (fdf["tracking_referrer_domain"].value_counts()
           .head(10).reset_index())
    dom.columns = ["domain","count"]
    fig5 = px.bar(dom, x="count", y="domain", orientation="h",
                  title="Top 10 Referrer Domains",
                  color_discrete_sequence=["#6366f1"],
                  labels={"count":"Leads","domain":"Domain"})
    fig5.update_layout(height=320)
    st.plotly_chart(fig5, use_container_width=True, config=CHART_CFG)

with q4:
    land = (fdf["tracking_landing_page"].value_counts()
            .head(10).reset_index())
    land.columns = ["page","count"]
    fig6 = px.bar(land, x="count", y="page", orientation="h",
                  title="Top 10 Landing Pages",
                  color_discrete_sequence=["#f59e0b"],
                  labels={"count":"Leads","page":"Page"})
    fig6.update_layout(height=320)
    st.plotly_chart(fig6, use_container_width=True, config=CHART_CFG)

st.divider()

# ── Group size distribution ───────────────────────────────────────────────────
grp_df = fdf[fdf["group_min_size"].notna() | fdf["group_max_size"].notna()].copy()
if len(grp_df) > 0:
    st.subheader("Group Size")
    g1, g2 = st.columns(2)
    with g1:
        fig7 = px.histogram(grp_df, x="group_min_size", nbins=15,
                            title="Min Group Size Distribution",
                            color_discrete_sequence=["#6366f1"],
                            labels={"group_min_size":"Min group size","count":"Leads"})
        fig7.update_layout(height=260)
        st.plotly_chart(fig7, use_container_width=True, config=CHART_CFG)
    with g2:
        fig8 = px.histogram(grp_df, x="group_max_size", nbins=15,
                            title="Max Group Size Distribution",
                            color_discrete_sequence=["#22c55e"],
                            labels={"group_max_size":"Max group size","count":"Leads"})
        fig8.update_layout(height=260)
        st.plotly_chart(fig8, use_container_width=True, config=CHART_CFG)
    st.divider()

# ── Organic Leads Table ───────────────────────────────────────────────────────
st.subheader("Organic Leads Table")

tbl = fdf[["first_request_at","full_name","email","latest_destination",
           "latest_budget","request_count","qualifying_answer",
           "group_min_size","group_max_size",
           "tracking_referrer_type","tracking_referrer_domain",
           "converted","latest_deal_status_category",
           "total_est_gbv","days_request_to_deal"]].copy()
tbl["first_request_at"] = tbl["first_request_at"].dt.strftime("%Y-%m-%d")
tbl = tbl.sort_values("first_request_at", ascending=False)

st.dataframe(tbl, use_container_width=True, hide_index=True,
             column_config={
                 "total_est_gbv":       st.column_config.NumberColumn("Est. GBV",   format="$%.0f"),
                 "converted":           st.column_config.CheckboxColumn("Converted"),
                 "qualifying_answer":   st.column_config.TextColumn("Qualifying"),
                 "group_min_size":      st.column_config.NumberColumn("Grp Min"),
                 "group_max_size":      st.column_config.NumberColumn("Grp Max"),
                 "tracking_referrer_type":   st.column_config.TextColumn("Ref. Type"),
                 "tracking_referrer_domain": st.column_config.TextColumn("Ref. Domain"),
             })
