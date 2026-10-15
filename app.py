import io
import streamlit as st
import pandas as pd
import datetime as dt
import pytz
import yfinance as yf
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from app.sources import fetch_all_sources
from app.dedup_classify import classify_categories, classify_impact, deduplicate_articles

IST = pytz.timezone("Asia/Kolkata")

st.set_page_config(page_title="NSE Live News Terminal", layout="wide", initial_sidebar_state="collapsed")

# ---------------------------------------------------------------------
# HIGH-DENSITY CUSTOM CSS
# ---------------------------------------------------------------------
st.markdown("""
<style>
    /* Reduce overall padding and whitespace */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }
    
    /* Shrink font sizes for higher density */
    html, body, p, div, span, label {
        font-size: 13px !important;
    }
    h1 { font-size: 22px !important; margin-bottom: 0px !important; padding-bottom: 0px !important; }
    h2 { font-size: 18px !important; }
    h3 { font-size: 15px !important; }
    
    /* Ticker Tape Animation & Styling */
    .ticker-wrap {
        width: 100%;
        overflow: hidden;
        background-color: #1e1e1e;
        color: #ffffff;
        padding-left: 100%;
        box-sizing: content-box;
        border-bottom: 1px solid #333;
        margin-bottom: 15px;
    }
    .ticker {
        display: inline-block;
        white-space: nowrap;
        padding-right: 100%;
        animation: ticker 40s linear infinite;
        font-family: monospace;
        font-size: 14px;
        line-height: 25px;
    }
    .ticker__item {
        display: inline-block;
        padding: 0 20px;
    }
    @keyframes ticker {
        0% { transform: translate3d(0, 0, 0); }
        100% { transform: translate3d(-100%, 0, 0); }
    }
    
    /* KPI Cards Styling */
    .kpi-container {
        display: flex;
        gap: 15px;
        margin-bottom: 15px;
    }
    .kpi-card {
        flex: 1;
        padding: 10px 15px;
        border-radius: 4px;
        border: 1px solid #ddd;
        background-color: #f8f9fa;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    [data-theme="dark"] .kpi-card {
        background-color: #262730;
        border-color: #444;
    }
    .kpi-title { font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 5px; color: #555;}
    [data-theme="dark"] .kpi-title { color: #aaa; }
    .kpi-value { font-size: 18px; font-weight: bold; margin-bottom: 2px;}
    .kpi-change { font-size: 12px; font-weight: bold; }
    .color-green { color: #0f9d58; }
    .color-red { color: #d23f31; }
    .bg-green { background-color: rgba(15, 157, 88, 0.1); border: 1px solid rgba(15, 157, 88, 0.3); }
    .bg-red { background-color: rgba(210, 63, 49, 0.1); border: 1px solid rgba(210, 63, 49, 0.3); }
    
    /* Compact Dataframe */
    .stDataFrame { font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# MARKET DATA UTILITIES
# ---------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_market_data(symbols):
    """Fetches real-time market data for the ticker tape and KPIs."""
    data = {}
    try:
        tickers = " ".join([f"{sym}.NS" for sym in symbols] + ["^NSEI", "^NSEBANK"])
        df = yf.download(tickers, period="2d", interval="1d", progress=False)['Close']
        
        for sym in symbols + ["^NSEI", "^NSEBANK"]:
            lookup = f"{sym}.NS" if not sym.startswith("^") else sym
            if lookup in df.columns and len(df[lookup].dropna()) >= 2:
                latest = df[lookup].iloc[-1]
                prev = df[lookup].iloc[-2]
                pct_change = ((latest - prev) / prev) * 100
                data[sym] = {"price": latest, "change": pct_change}
    except Exception:
        pass
    return data

@st.cache_data(ttl=60)
def fetch_intraday_chart(symbol="^NSEI"):
    """Fetches intraday 5m data for the market chart."""
    try:
        df = yf.download(symbol, period="1d", interval="5m", progress=False)
        return df
    except Exception:
        return pd.DataFrame()

def get_market_status():
    now = dt.datetime.now(IST)
    if now.weekday() >= 5:
        return "CLOSED (WEEKEND)"
    current_time = now.time()
    if dt.time(9, 0) <= current_time < dt.time(9, 15):
        return "PRE-OPEN (09:00 - 09:15 IST)"
    elif dt.time(9, 15) <= current_time <= dt.time(15, 30):
        return "OPEN (09:15 - 15:30 IST)"
    return "CLOSED"

# ---------------------------------------------------------------------
# INITIALIZATION & STATE
# ---------------------------------------------------------------------
if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS"]

market_data = fetch_market_data(st.session_state["watchlist"][:15]) # Limit ticker to 15 stocks

# ---------------------------------------------------------------------
# TICKER TAPE
# ---------------------------------------------------------------------
ticker_html = '<div class="ticker-wrap"><div class="ticker">'
for sym, details in market_data.items():
    if not sym.startswith("^"):
        color = "#0f9d58" if details["change"] >= 0 else "#d23f31"
        sign = "+" if details["change"] >= 0 else ""
        ticker_html += f'<div class="ticker__item">{sym} <span style="color:{color}">{details["price"]:.2f} ({sign}{details["change"]:.2f}%)</span></div>'
ticker_html += '</div></div>'
st.markdown(ticker_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# NAVIGATION TABS
# ---------------------------------------------------------------------
tab_news, tab_setup = st.tabs(["LIVE NEWS TERMINAL", "WATCHLIST SETUP"])

with tab_setup:
    st.markdown("### Watchlist Configuration")
    uploaded_file = st.file_uploader("Upload Watchlist (CSV or Excel)", type=["csv", "xlsx"])
    
    if uploaded_file is not None:
        try:
            df_upload = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
            col_target = [c for c in df_upload.columns if "sym" in c.lower() or "stock" in c.lower()][0]
            new_symbols = df_upload[col_target].dropna().astype(str).str.strip().str.upper().tolist()
            st.session_state["watchlist"] = new_symbols
            st.success(f"Watchlist updated with {len(new_symbols)} symbols.")
        except Exception:
            st.error("Failed to parse file. Ensure it contains a column named 'Symbol'.")
            
    st.multiselect("Active Watchlist", options=st.session_state["watchlist"], default=st.session_state["watchlist"], disabled=True)

with tab_news:
    # -----------------------------------------------------------------
    # KPI CARDS ROW
    # -----------------------------------------------------------------
    kpi_html = '<div class="kpi-container">'
    for idx_name, idx_sym in [("NIFTY 50", "^NSEI"), ("NIFTY BANK", "^NSEBANK")]:
        if idx_sym in market_data:
            val = market_data[idx_sym]
            color_class = "color-green" if val["change"] >= 0 else "color-red"
            bg_class = "bg-green" if val["change"] >= 0 else "bg-red"
            sign = "+" if val["change"] >= 0 else ""
            kpi_html += f"""
            <div class="kpi-card {bg_class}">
                <div class="kpi-title">{idx_name}</div>
                <div class="kpi-value">{val["price"]:,.2f}</div>
                <div class="kpi-change {color_class}">{sign}{val["change"]:.2f}%</div>
            </div>
            """
    kpi_html += f"""
        <div class="kpi-card">
            <div class="kpi-title">MARKET STATUS</div>
            <div class="kpi-value" style="font-size: 14px; margin-top: 5px;">{get_market_status()}</div>
        </div>
    </div>
    """
    st.markdown(kpi_html, unsafe_allow_html=True)

    # -----------------------------------------------------------------
    # MAIN SPLIT LAYOUT (CHART vs NEWS)
    # -----------------------------------------------------------------
    col_chart, col_news = st.columns([0.35, 0.65])
    
    with col_chart:
        st.markdown("### NIFTY 50 Intraday")
        chart_df = fetch_intraday_chart("^NSEI")
        if not chart_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=chart_df.index, y=chart_df['Close'],
                fill='tozeroy',
                mode='lines',
                line=dict(color='#0f9d58' if chart_df['Close'].iloc[-1] >= chart_df['Open'].iloc[0] else '#d23f31', width=2),
                fillcolor='rgba(15, 157, 88, 0.1)' if chart_df['Close'].iloc[-1] >= chart_df['Open'].iloc[0] else 'rgba(210, 63, 49, 0.1)'
            ))
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                height=250,
                xaxis=dict(showgrid=False, visible=False),
                yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        st.markdown("### Terminal Controls")
        refresh_interval = st.selectbox("Auto-Refresh Interval", options=["Manual", "1 Minute", "3 Minutes", "5 Minutes"])
        lookback_hours = st.slider("Lookback Window (Hours)", 1, 72, 24)
        impact_filter = st.multiselect("Impact Level Filter", ["HIGH", "MEDIUM", "LOW"], ["HIGH", "MEDIUM", "LOW"])
        fetch_triggered = st.button("Manual Fetch", type="primary", use_container_width=True)

    with col_news:
        if refresh_interval != "Manual":
            interval_ms = int(refresh_interval.split()[0]) * 60000
            st_autorefresh(interval=interval_ms, key="data_refresh")

        if fetch_triggered or (refresh_interval != "Manual"):
            with st.spinner("Polling sources..."):
                raw_articles = fetch_all_sources(st.session_state["watchlist"], hours_back=lookback_hours)
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

        if "news_df" in st.session_state and not st.session_state["news_df"].empty:
            df = st.session_state["news_df"].copy()
            if "impact" in df.columns:
                df = df[df["impact"].isin(impact_filter)]
            
            col_search, col_export = st.columns([0.7, 0.3])
            with col_search:
                search_query = st.text_input("Global Search", placeholder="Filter by Ticker, Headline, or Source...", label_visibility="collapsed")
            with col_export:
                cols_to_export = [c for c in ["stock_symbol", "published_time", "impact", "category", "headline", "source", "source_type", "article_url"] if c in df.columns]
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df[cols_to_export].to_excel(writer, index=False, sheet_name='Live_News')
                st.download_button("Export Excel", data=buffer, file_name=f"NSE_News_{dt.datetime.now(IST).strftime('%Y%m%d_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

            if search_query:
                mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
                df = df[mask]
            
            def style_impact(val):
                if val == "HIGH": return "color: #d23f31; font-weight: bold;"
                elif val == "MEDIUM": return "color: #f2a900; font-weight: bold;"
                return "color: #0f9d58;"

            styled_df = df[cols_to_export].style.map(style_impact, subset=['impact'])
            
            st.dataframe(
                styled_df,
                column_config={
                    "article_url": st.column_config.LinkColumn("Link", display_text="Open"),
                    "published_time": "Time (IST)",
                    "stock_symbol": "Ticker",
                    "impact": "Impact",
                    "category": "Category",
                    "headline": "Headline",
                    "source": "Source",
                    "source_type": "Type"
                },
                use_container_width=True,
                hide_index=True,
                height=600  # Fixed height for high density scrolling
            )
        else:
            st.info("Execute 'Manual Fetch' or wait for auto-refresh to populate the terminal.")
