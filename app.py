import io
import streamlit as st
import pandas as pd
import datetime as dt
import pytz
from streamlit_autorefresh import st_autorefresh
from app.sources import fetch_all_sources
from app.dedup_classify import classify_categories, classify_impact, deduplicate_articles

IST = pytz.timezone("Asia/Kolkata")

st.set_page_config(page_title="NSE Live News Terminal", layout="wide")

# ---------------------------------------------------------------------
# MARKET SESSION UTILITY
# ---------------------------------------------------------------------
def get_market_status():
    now = dt.datetime.now(IST)
    if now.weekday() >= 5:
        return "CLOSED (WEEKEND)"
    
    current_time = now.time()
    pre_open_start = dt.time(9, 0)
    market_open = dt.time(9, 15)
    market_close = dt.time(15, 30)
    
    if pre_open_start <= current_time < market_open:
        return "PRE-OPEN (09:00 - 09:15 IST)"
    elif market_open <= current_time <= market_close:
        return "OPEN (09:15 - 15:30 IST)"
    else:
        return "CLOSED"

market_status = get_market_status()

# ---------------------------------------------------------------------
# HEADER & STATUS BAR
# ---------------------------------------------------------------------
col_title, col_status = st.columns([3, 1])
with col_title:
    st.title("NSE Live News Terminal")
    st.markdown("Institutional News Aggregation and Deduplication Desk")
with col_status:
    st.info(f"MARKET STATUS: {market_status}")

# ---------------------------------------------------------------------
# CONFIGURATION PANEL (TOGGLEABLE)
# ---------------------------------------------------------------------
with st.expander("Configuration & Watchlist Options", expanded=False):
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Watchlist Configuration")
        uploaded_file = st.file_uploader(
            "Upload Watchlist (CSV or Excel)",
            type=["csv", "xlsx"]
        )
        
        default_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS"]
        custom_symbols = []

        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".csv"):
                    uploaded_df = pd.read_csv(uploaded_file)
                else:
                    uploaded_df = pd.read_excel(uploaded_file)
                
                possible_cols = [c for c in uploaded_df.columns if "sym" in c.lower() or "stock" in c.lower() or "ticker" in c.lower()]
                target_col = possible_cols[0] if possible_cols else uploaded_df.columns[0]
                
                custom_symbols = uploaded_df[target_col].dropna().astype(str).str.strip().str.upper().tolist()
                st.success(f"Loaded {len(custom_symbols)} stocks from uploaded file.")
            except Exception as e:
                st.error(f"Error parsing uploaded file: {e}")

        combined_symbols = list(set(custom_symbols + default_symbols)) if custom_symbols else default_symbols
        selected_symbols = st.multiselect("Active Watchlist Stocks", options=combined_symbols, default=custom_symbols or default_symbols)

    with col_right:
        st.subheader("System Settings")
        refresh_interval = st.selectbox(
            "Auto-Refresh Interval",
            options=["Manual", "1 Minute", "3 Minutes", "5 Minutes"],
            index=0
        )
        
        lookback_hours = st.slider(
            "Catch-Up Window (Hours)",
            min_value=1,
            max_value=72,
            value=24
        )
        
        impact_filter = st.multiselect(
            "Impact Level Filter",
            options=["HIGH", "MEDIUM", "LOW"],
            default=["HIGH", "MEDIUM", "LOW"]
        )

# ---------------------------------------------------------------------
# AUTO-REFRESH LOGIC
# ---------------------------------------------------------------------
if refresh_interval != "Manual":
    interval_ms = int(refresh_interval.split()[0]) * 60000
    st_autorefresh(interval=interval_ms, key="data_refresh_timer")

st.markdown("---")

# ---------------------------------------------------------------------
# DATA FETCHING
# ---------------------------------------------------------------------
fetch_triggered = st.button("Fetch & Process News", type="primary")

if fetch_triggered or (refresh_interval != "Manual"):
    if not selected_symbols:
        st.warning("Please select at least one stock ticker in the configuration panel.")
    else:
        with st.spinner("Polling active sources..."):
            raw_articles = fetch_all_sources(selected_symbols, hours_back=lookback_hours)
            
            if raw_articles:
                processed = []
                for art in raw_articles:
                    art["category"] = ", ".join(classify_categories(art["headline"]))
                    art["impact"] = classify_impact(art["headline"])
                    processed.append(art)

                clean_articles = deduplicate_articles(processed)
                st.session_state["news_df"] = pd.DataFrame(clean_articles)
            else:
                st.session_state["news_df"] = pd.DataFrame()

# ---------------------------------------------------------------------
# DISPLAY RESULTS, SEARCH & EXPORT
# ---------------------------------------------------------------------
if "news_df" in st.session_state and not st.session_state["news_df"].empty:
    df = st.session_state["news_df"].copy()
    
    if "impact" in df.columns:
        df = df[df["impact"].isin(impact_filter)]
    
    # Global Search Bar
    search_query = st.text_input("Global Search (Filter by Keyword, Ticker, or Source)", placeholder="Type to filter results...")
    if search_query:
        mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
        df = df[mask]
    
    # Summary Cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Articles", len(df))
    col2.metric("High Impact Alerts", len(df[df["impact"] == "HIGH"]) if "impact" in df.columns else 0)
    col3.metric("Stocks Covered", df["stock_symbol"].nunique() if "stock_symbol" in df.columns else 0)
    col4.metric("Sources Polled", df["source"].nunique() if "source" in df.columns else 0)

    st.markdown("---")
    
    # Export to Excel
    cols_to_export = [c for c in ["stock_symbol", "published_time", "impact", "category", "headline", "source", "source_type", "article_url"] if c in df.columns]
    df_export = df[cols_to_export].copy()
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Live_News')
    
    st.download_button(
        label="Download Excel Report (.xlsx)",
        data=buffer,
        file_name=f"NSE_News_{dt.datetime.now(IST).strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")

    # Data Formatting / Badging Rules
    def style_impact(val):
        if val == "HIGH":
            return "color: #ff4b4b; font-weight: bold;"
        elif val == "MEDIUM":
            return "color: #ffa421; font-weight: bold;"
        elif val == "LOW":
            return "color: #21c354; font-weight: normal;"
        return ""

    def style_source_type(val):
        if val in ["BSE", "NSE"]:
            return "background-color: #2e4a7b; color: white; border-radius: 3px;"
        elif val == "SEARCH_RESULT":
            return "color: #888888;"
        return ""

    # Apply Styler
    styled_df = df_export.style.map(style_impact, subset=['impact']).map(style_source_type, subset=['source_type'])

    # Display Table
    st.dataframe(
        styled_df,
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
    st.info("Execute 'Fetch & Process News' or wait for the auto-refresh cycle to load data.")
