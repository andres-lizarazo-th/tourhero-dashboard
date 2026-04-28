import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.bq import query, PROJECT

st.set_page_config(page_title="Inbox", layout="wide")
st.title("📥 Inbox")

sql = f"""
SELECT channel, message_id, time_received, week_start, month_key,
  lead_email, lead_name, lead_handle, lead_segment,
  category, reply_sentiment, temperature, meeting_booked, mentions_availability,
  campaign_name, manager, not_a_fit, email_score,
  our_reply, ai_send_automatic_reply
FROM `{PROJECT}`.bdcrm.v_inbox_unified
WHERE time_received >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
"""
df = query(sql)
df["time_received"] = pd.to_datetime(df["time_received"], utc=True)

with st.sidebar:
    st.header("Filters")
    days = st.slider("Days back", 7, 180, 90)
    channels  = st.multiselect("Channel",  sorted(df["channel"].dropna().unique()),
                               default=list(df["channel"].dropna().unique()))
    segs      = st.multiselect("Segment",  sorted(df["lead_segment"].dropna().unique()))
    temps     = st.multiselect("Temperature", sorted(df["temperature"].dropna().unique()))
    managers  = st.multiselect("Manager",  sorted(df["manager"].dropna().unique()))
    meeting   = st.selectbox("Meeting Booked", ["All","Yes","No"])
    granularity = st.radio("Granularity", ["Weekly","Monthly"], horizontal=True)

cutoff = pd.Timestamp.today(tz="UTC") - pd.Timedelta(days=days)
fdf = df[df["time_received"] >= cutoff]
if channels: fdf = fdf[fdf["channel"].isin(channels)]
if segs:     fdf = fdf[fdf["lead_segment"].isin(segs)]
if temps:    fdf = fdf[fdf["temperature"].isin(temps)]
if managers: fdf = fdf[fdf["manager"].isin(managers)]
if meeting != "All": fdf = fdf[fdf["meeting_booked"] == meeting]

total_msgs    = len(fdf)
replied_msgs  = (fdf["our_reply"].notna() & (fdf["our_reply"].astype(str).str.strip() != "")).sum()
auto_replies  = fdf["ai_send_automatic_reply"].fillna(False).astype(bool).sum()
meetings      = (fdf["meeting_booked"] == "Yes").sum()
reply_rate    = replied_msgs / total_msgs * 100 if total_msgs else 0

c1,c2,c3,c4,c5 = st.columns(5)
with c1: st.metric("Total Messages",   f'{total_msgs:,}')
with c2: st.metric("Replied Messages", f'{replied_msgs:,}')
with c3: st.metric("Automated Replies", f'{auto_replies:,}')
with c4: st.metric("Meetings Booked",  f'{meetings:,}')
with c5: st.metric("Reply Rate",       f'{reply_rate:.1f}%')

SENTIMENT_ORDER  = ["Positive", "Neutral", "Negative"]
SENTIMENT_COLORS = {"Positive": "#22c55e", "Neutral": "#94a3b8", "Negative": "#ef4444"}

st.divider()
dim = "week_start" if granularity == "Weekly" else "month_key"

# ── Row 1: Volume by channel + Sentiment stacked bar ─────────────────────────
col1, col2 = st.columns(2)
with col1:
    ts = fdf.groupby([dim,"channel"])["message_id"].count().reset_index(name="count")
    fig = px.bar(ts, x=dim, y="count", color="channel",
                 title="Inbox Volume per " + ("Week" if granularity=="Weekly" else "Month"),
                 labels={dim:"Period","count":"Messages"},
                 color_discrete_sequence=["#6366f1","#f59e0b"])
    fig.update_layout(height=300, legend_title="Channel")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    sent_ts = (fdf.groupby([dim,"reply_sentiment"])["message_id"]
               .count().reset_index(name="count"))
    sent_ts["reply_sentiment"] = pd.Categorical(
        sent_ts["reply_sentiment"], categories=SENTIMENT_ORDER, ordered=True)
    sent_ts = sent_ts.sort_values([dim,"reply_sentiment"])
    fig2 = px.bar(sent_ts, x=dim, y="count", color="reply_sentiment",
                  barmode="stack",
                  title="Reply Sentiment per " + ("Week" if granularity=="Weekly" else "Month"),
                  labels={dim:"Period","count":"Messages","reply_sentiment":"Sentiment"},
                  color_discrete_map=SENTIMENT_COLORS,
                  category_orders={"reply_sentiment": SENTIMENT_ORDER})
    fig2.update_layout(height=300, legend_title="Sentiment")
    st.plotly_chart(fig2, use_container_width=True)

# ── Row 2: Category breakdown + Temp donut ───────────────────────────────────
col3, col4 = st.columns(2)
with col3:
    cat_cnt = (fdf.groupby(["category","reply_sentiment"])["message_id"]
               .count().reset_index(name="count")
               .sort_values("count", ascending=True))
    fig3 = px.bar(cat_cnt, x="count", y="category", color="reply_sentiment",
                  orientation="h",
                  title="Messages by Category",
                  labels={"count":"Messages","reply_sentiment":"Sentiment"},
                  color_discrete_map=SENTIMENT_COLORS,
                  category_orders={"reply_sentiment": SENTIMENT_ORDER})
    fig3.update_layout(height=420, legend_title="Sentiment")
    st.plotly_chart(fig3, use_container_width=True)

with col4:
    # Sentiment donut
    sent_total = fdf.groupby("reply_sentiment")["message_id"].count().reset_index(name="count")
    fig4 = px.pie(sent_total, names="reply_sentiment", values="count",
                  title="Overall Sentiment Mix", hole=0.45,
                  color="reply_sentiment",
                  color_discrete_map=SENTIMENT_COLORS)
    fig4.update_layout(height=260)
    st.plotly_chart(fig4, use_container_width=True)

    # Email temperature donut
    email_df = fdf[fdf["channel"]=="email"]
    if len(email_df) > 0:
        temp_cnt = email_df["temperature"].value_counts().reset_index()
        temp_cnt.columns = ["temperature","count"]
        fig5 = px.pie(temp_cnt, names="temperature", values="count",
                      title="Email Temperature", hole=0.45)
        fig5.update_layout(height=260)
        st.plotly_chart(fig5, use_container_width=True)

# ── Row 3: Replies by Inbox Manager ──────────────────────────────────────────
mgr_df = fdf[fdf["manager"].notna()].copy()
if len(mgr_df) > 0:
    col5, col6 = st.columns(2)
    with col5:
        mgr_cnt = (mgr_df.groupby(["manager","reply_sentiment"])["message_id"]
                   .count().reset_index(name="count"))
        mgr_cnt["reply_sentiment"] = pd.Categorical(
            mgr_cnt["reply_sentiment"], categories=SENTIMENT_ORDER, ordered=True)
        mgr_total = mgr_cnt.groupby("manager")["count"].sum().sort_values(ascending=True)
        mgr_cnt["manager"] = pd.Categorical(mgr_cnt["manager"], categories=mgr_total.index, ordered=True)
        fig6 = px.bar(mgr_cnt, x="count", y="manager", color="reply_sentiment",
                      orientation="h", barmode="stack",
                      title="Messages by Inbox Manager",
                      labels={"count":"Messages","manager":"Manager","reply_sentiment":"Sentiment"},
                      color_discrete_map=SENTIMENT_COLORS,
                      category_orders={"reply_sentiment": SENTIMENT_ORDER})
        fig6.update_layout(height=max(280, len(mgr_total) * 40), legend_title="Sentiment")
        st.plotly_chart(fig6, use_container_width=True)

    with col6:
        # Replied vs not replied per manager
        mgr_df2 = mgr_df.copy()
        mgr_df2["Replied"] = (
            mgr_df2["our_reply"].notna() &
            (mgr_df2["our_reply"].astype(str).str.strip() != "")
        ).map({True: "Replied", False: "Not Replied"})
        replied_mgr = (mgr_df2.groupby(["manager","Replied"])["message_id"]
                       .count().reset_index(name="count"))
        replied_mgr["manager"] = pd.Categorical(
            replied_mgr["manager"], categories=mgr_total.index, ordered=True)
        fig7 = px.bar(replied_mgr, x="count", y="manager", color="Replied",
                      orientation="h", barmode="stack",
                      title="Replied vs Pending by Manager",
                      labels={"count":"Messages","manager":"Manager"},
                      color_discrete_map={"Replied":"#22c55e","Not Replied":"#94a3b8"})
        fig7.update_layout(height=max(280, len(mgr_total) * 40), legend_title="")
        st.plotly_chart(fig7, use_container_width=True)

st.divider()
st.subheader("Inbox Table")

tbl = fdf[["time_received","channel","lead_name","lead_handle",
           "lead_segment","category","temperature","meeting_booked",
           "campaign_name","manager","email_score"]].copy()
tbl["time_received"] = tbl["time_received"].dt.tz_convert("America/Sao_Paulo").dt.strftime("%Y-%m-%d %H:%M")
tbl = tbl.sort_values("time_received", ascending=False)

st.dataframe(tbl, use_container_width=True, hide_index=True)

