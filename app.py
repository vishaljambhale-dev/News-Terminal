import streamlit as st
import pandas as pd
import datetime as dt
from app.sources import fetch_all_sources
from app.dedup_classify import classify_categories, classify_impact, deduplicate_articles

st.set_page_config(page_title="NSE Live News Terminal", layout="wide", page_icon="⚡")

st.title("⚡ NSE Live News Terminal")
st.markdown("Multi-source financial news aggregation, deduplication, and export.")

# ---------------------------------------------------------------------
# TOGGLEABLE CONFIGURATION PANEL
# ---------------------------------------------------------------------
with st.expander("⚙️ Configuration & Watchlist Options", expanded=False):
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("1. Watchlist Stock Selection")
        
        # File Uploader for CSV/Excel
        uploaded_file = st.file_uploader(
            "Upload Watchlist (CSV or Excel)",
            type=["csv", "xlsx"],
            help="Upload a file with a column containing stock tickers (e.g., 'NSE_SYMBOL' or 'Symbol')."
        )
        
        default_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS"]
        custom_symbols = []

        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".csv"):
                    uploaded_df = pd.read_csv(uploaded_file)
                else:
                    uploaded_df = pd.read_excel(uploaded_file)
                
                # Auto-detect column containing symbols
                possible_cols = [c for c in uploaded_df.columns if "sym" in c.lower() or "stock" in c.lower() or "ticker" in c.lower()]
                target_col = possible_cols[0] if possible_cols else uploaded_df.columns[0]
                
                custom_symbols = uploaded_df[target_col].dropna().astype(str).str.strip().str.upper().tolist()
                st.success(f"Loaded {len(custom_symbols)} stocks from uploaded file!")
            except Exception as e:
                st.error(f"Error parsing uploaded file: {e}")

        combined_symbols = list(set(custom_symbols + default_symbols)) if custom_symbols else default_symbols
        selected_symbols = st.multiselect("Active Watchlist Stocks", options=combined_symbols, default=custom_symbols or default_symbols)

    with col_right:
        st.subheader("2. Settings & Filters")
        lookback_hours = st.slider(
            "🕒 Catch-Up Window (Hours)",
            min_value=1,
            max_value=72,
            value=24,
            help="Fetches articles published within this timeframe to catch up on inactive periods."
        )
        
        impact_filter = st.multiselect(
            "Impact Level Filter",
            options=["HIGH", "MEDIUM", "LOW"],
            default=["HIGH", "MEDIUM", "LOW"]
        )

st.markdown("---")

# ---------------------------------------------------------------------
# FETCH & PROCESS ACTION
# ---------------------------------------------------------------------
if st.button("🔄 Fetch & Process News", type="primary"):
    if not selected_symbols:
        st.warning("Please select at least one stock ticker in the configuration panel.")
    else:
        with st.spinner("Polling India/Global feeds, BSE notices, NSE announcements, and searching Google News..."):
            raw_articles = fetch_all_sources(selected_symbols, hours_back=lookback_hours)
            
            if not raw_articles:
                st.warning("No relevant articles found for the selected lookback window.")
            else:
                processed = []
                for art in raw_articles:
                    art["category"] = ", ".join(classify_categories(art["headline"]))
                    art["impact"] = classify_impact(art["headline"])
                    processed.append(art)

                clean_articles = deduplicate_articles(processed)
                st.session_state["news_df"] = pd.DataFrame(clean_articles)

# ---------------------------------------------------------------------
# DISPLAY RESULTS & DOWNLOAD BUTTON
# ---------------------------------------------------------------------
if "news_df" in st.session_state and not st.session_state["news_df"].empty:
    df = st.session_state["news_df"].copy()
    
    if "impact" in df.columns:
        df = df[df["impact"].isin(impact_filter)]
    
    # Summary Cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Articles", len(df))
    col2.metric("High Impact Alerts", len(df[df["impact"] == "HIGH"]) if "impact" in df.columns else 0)
    col3.metric("Stocks Covered", df["stock_symbol"].nunique() if "stock_symbol" in df.columns else 0)
    col4.metric("Sources Polled", df["source"].nunique() if "source" in df.columns else 0)

    st.markdown("---")
    
    # Download Button
    cols_to_export = [c for c in ["stock_symbol", "published_time", "impact", "category", "headline", "source", "source_type", "article_url"] if c in df.columns]
    df_export = df[cols_to_export].copy()
    csv_data = df_export.to_csv(index=False).encode('utf-8')
    
    st.download_button(
        label="📄 Download Compiled News List (CSV)",
        data=csv_data,
        file_name=f"nse_news_export_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

    st.markdown("---")

    # Display Table
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
            "source_type": "Type"
        },
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Click **'Fetch & Process News'** above to load articles.")
