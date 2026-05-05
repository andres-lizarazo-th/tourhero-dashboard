import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Lead Explorer", layout="wide")

st.markdown("""
<style>
[data-testid="stElementToolbar"] {display: none !important;}
[data-testid="stDownloadButton"] {display: none !important;}
</style>
""", unsafe_allow_html=True)

CHART_CFG = {"displayModeBar": False}

st.title("Lead Explorer")
st.caption("Filters query BigQuery directly — click **Search** to apply.")

# ── Search form (server-side BQ filtering for 4.8M row table) ─────────────────
with st.form("lead_search"):
    c1, c2, c3 = st.columns(3)
    with c1:
        seg = st.multiselect("Segment", ["vip","qualifying","creator","mba","faith","organic","unmatched-email-addresses"])
        stage = st.multiselect("Pipeline Stage", [
            "1 - Scraped","2 - Enriched","3 - Contacted","4 - Replied",
            "5 - Call Booked","6 - Deal Created"
        ])
    with c2:
        has_deal = st.selectbox("Has Deal", ["All","Yes","No"])
        has_call = st.selectbox("Has Call", ["All","Yes","No"])
        is_vip_deal = st.selectbox("Has VIP Deal", ["All","Yes","No"])
    with c3:
        search_email = st.text_input("Email contains")
        search_name  = st.text_input("Name contains")
        limit = st.selectbox("Max rows", [500, 1000, 5000], index=1)

    submitted = st.form_submit_button("Search", type="primary")

if not submitted:
    st.info("Set filters above and click Search.")
    st.stop()

# Build WHERE
clauses = []
if seg:         clauses.append(f"lead_segment IN ({','.join(repr(s) for s in seg)})")
if stage:       clauses.append(f"current_pipeline_stage IN ({','.join(repr(s) for s in stage)})")
if has_deal == "Yes": clauses.append("has_deal_created = TRUE")
if has_deal == "No":  clauses.append("has_deal_created = FALSE")
if has_call == "Yes": clauses.append("has_booked_call = TRUE")
if has_call == "No":  clauses.append("has_booked_call = FALSE")
if is_vip_deal == "Yes": clauses.append("has_vip_deal = TRUE")
if is_vip_deal == "No":  clauses.append("has_vip_deal = FALSE")
if search_email: clauses.append(f"LOWER(email) LIKE '%{search_email.lower()}%'")
if search_name:  clauses.append(f"LOWER(full_name) LIKE '%{search_name.lower()}%'")

where = " AND ".join(clauses) if clauses else "TRUE"

sql = f"""
SELECT lead_id, full_name, email, instagram_username, lead_segment,
  current_pipeline_stage, ig_follower_count,
  contacted_via_email, has_replied_email, has_booked_call,
  has_booked_onboarding, has_deal_created, has_vip_deal,
  first_contacted_at, last_reply_at, call_booked_at, deal_created_at,
  deal_count, total_est_gbv, latest_deal_status_category,
  calls_count, tours_count, days_contacted_to_deal
FROM `{PROJECT}`.analytics.v_leads_enriched
WHERE {where}
ORDER BY total_est_gbv DESC NULLS LAST
LIMIT {limit}
"""

with st.spinner("Querying BigQuery…"):
    df = query(sql)

# ── Scorecards ────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5 = st.columns(5)
with c1: st.metric("Leads found",     f'{len(df):,}')
with c2: st.metric("With Deal",       f'{df["has_deal_created"].sum():,}')
with c3: st.metric("With Call",       f'{df["has_booked_call"].sum():,}')
with c4: st.metric("Total Est. GBV",  f'${df["total_est_gbv"].sum():,.0f}')
with c5:
    avg_d = df["days_contacted_to_deal"].dropna().mean()
    st.metric("Avg Days to Deal", f'{avg_d:.0f}' if not pd.isna(avg_d) else "—")

st.divider()
st.subheader(f"Results ({len(df):,} leads)")

tbl = df.copy()
for col in ["first_contacted_at","last_reply_at","call_booked_at","deal_created_at"]:
    if col in tbl.columns:
        tbl[col] = pd.to_datetime(tbl[col], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")

st.dataframe(tbl, use_container_width=True, hide_index=True,
             column_config={
                 "total_est_gbv": st.column_config.NumberColumn("GBV", format="$%.0f"),
                 "ig_follower_count": st.column_config.NumberColumn("Followers", format="%d"),
             })
