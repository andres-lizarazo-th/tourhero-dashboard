import streamlit as st
from datetime import datetime
from utils.bq import PROJECT, query

st.set_page_config(
    page_title="TourHero GTM Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("TourHero GTM Dashboard")
st.caption(f"Connected to BigQuery project `{PROJECT}` · cache TTL 1h")

st.markdown("""
Use the sidebar to navigate between pages. Each page has its own filters.

| Page | What it shows | Data source |
|---|---|---|
| **0 · Exec Summary** | Funnel conversion, revenue efficiency, hero retention, campaign health | All views combined |
| **1 · Funnel Overview** | Outreach → Reply → Call → Deal · weekly/monthly trends · segment breakdown | `v_funnel_by_segment` |
| **2 · Campaigns** | Email campaign performance · reply/bounce/unsub rates · per-campaign table | `v_campaign_performance` |
| **3 · Inbox** | Inbound messages (email + DM) · sentiment · manager workload · category mix | `v_inbox_unified` |
| **4 · Deals & Revenue** | Deal pipeline · GBV · quote funnel · status mix | `v_deals_pipeline` |
| **5 · Lead Explorer** | Per-lead search with lifetime aggregates | `v_leads_enriched` |
| **6 · Organic** | Website trip requests and conversions | `v_organic_pipeline` |
| **7 · Platform** | Published tours · bookings · confirmed revenue · hero payouts | `v_tours_pipeline` |

### How to use

- **Date range** — every page has a date filter. Default is **Year-to-date (YTD)**.
- **Granularity** — toggle between **Weekly** and **Monthly** on charts that show trends.
- **Segments** — filter by lead segment (`creator`, `vip`, `vip-prequal`, `mba`, `faith`, `organic`, `unmatched-email-addresses`) on relevant pages.
- **Segments** — additional filter available on Funnel Overview and Inbox pages.

### Data freshness

- **BigQuery views** are computed live on every query — no staleness.
- **Underlying tables** (Bison, Calendly, Airtable) refresh on their own schedules. The pipeline is rebuilt fully when `leads_consolidator` runs (~daily).
- **Streamlit cache**: query results are cached for 1 hour per unique filter combination. To force a refresh, use the menu (top-right) → **Clear cache** → refresh the page.
""")

# Quick freshness footer
try:
    sql = f"""
    SELECT
      (SELECT MAX(_loaded_at) FROM `{PROJECT}`.analytics.leads_master)            AS leads_master_loaded,
      (SELECT MAX(sent_at)    FROM `{PROJECT}`.bison_tracking.bison_sent_emails)  AS last_bison_send,
      (SELECT MAX(deal_created_at) FROM `{PROJECT}`.operations.v_deals_pipeline)  AS last_deal_created
    """
    fr = query(sql).iloc[0]
    st.divider()
    cols = st.columns(3)
    with cols[0]: st.metric("Latest leads_master rebuild", fr["leads_master_loaded"].strftime("%Y-%m-%d %H:%M") if fr["leads_master_loaded"] else "—")
    with cols[1]: st.metric("Latest Bison email send",     fr["last_bison_send"].strftime("%Y-%m-%d %H:%M")   if fr["last_bison_send"]   else "—")
    with cols[2]: st.metric("Latest deal created",         fr["last_deal_created"].strftime("%Y-%m-%d %H:%M") if fr["last_deal_created"] else "—")
except Exception as e:
    st.warning(f"Could not load freshness footer: {e}")
