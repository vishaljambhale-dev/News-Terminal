import streamlit as st
import pandas as pd
import datetime as dt
from app.company_master import CompanyMaster
from app.sources import fetch_news_for_symbols
from app.dedup_classify import classify_categories, classify_impact, deduplicate_articles

st.set_page_config(page_title="NSE News Terminal", layout="wide", page_icon="⚡")

st.title("⚡ NSE Live News Terminal")
st.markdown("On-demand news monitoring, deduplication, and export for NSE stocks.")

# Sidebar Controls
st.sidebar.header("⚙️ Configuration")

# Watchlist input
try:
    watchlist_df = pd.read_csv("watchlist.csv")
    default_symbols = watchlist_df["NSE_SYMBOL"].dropna().tolist()
except Exception:
    default_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS"]

selected_symbols = st.sidebar.multiselect("Watchlist Stocks", options=default_symbols, default=default_symbols)

# Historical Lookback / Catch-up Window
lookback_hours = st.sidebar.slider(
    "🕒 Catch-Up Window (Hours)",
    min_value=1,
    max_value=72,
    value=24,
    help="Fetch news published within this time window to catch up on articles published while inactive."
)

impact_filter = st.sidebar.multiselect("Impact Filter", options=["HIGH", "MEDIUM", "LOW"], default=["HIGH", "MEDIUM", "LOW"])

# Main Action Button
if st.button("🔄 Fetch & Process News", type="primary"):
    with st.spinner("Fetching news feeds and removing duplicates..."):
        raw_articles = fetch_news_for_symbols(selected_symbols, hours_back=lookback_hours)
        
        if not raw_articles:
            st.warning("No articles found for the selected time window.")
        else:
            processed = []
            for art in raw_articles:
                art["category"] = ", ".join(classify_categories(art["headline"]))
                art["impact"] = classify_impact(art["headline"])
                processed.append(art)

            clean_articles = deduplicate_articles(processed)
            st.session_state["news_df"] = pd.DataFrame(clean_articles)

# Display Results & Export
if "news_df" in st.session_state and not st.session_state["news_df"].empty:
    df = st.session_state["news_df"].copy()
    df = df[df["impact"].isin(impact_filter)]
    
    # Summary Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Articles", len(df))
    col2.metric("High Impact Alerts", len(df[df["impact"] == "HIGH"]))
    col3.metric("Stocks Covered", df["stock_symbol"].nunique())

    st.markdown("---")
    
    # CSV Export Button
    df_export = df[["stock_symbol", "published_time", "impact", "category", "headline", "source", "article_url"]].copy()
    csv_data = df_export.to_csv(index=False).encode('utf-8')
    
    st.download_button(
        label="📄 Download Compiled News List (CSV)",
        data=csv_data,
        file_name=f"nse_news_export_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

    st.markdown("---")

    # Interactive Table
    st.dataframe(
        df_export,
        column_config={
            "article_url": st.column_config.LinkColumn("Source Link", display_text="Read Article"),
            "published_time": "Published (IST)",
            "stock_symbol": "Symbol",
            "impact": "Impact",
            "category": "Category",
            "headline": "Headline",
            "source": "Publisher",
        },
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Click **'Fetch & Process News'** above to load articles.")
