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
st.set_page_config(page_title="NSE Live Terminal", layout="wide", initial_sidebar_state="collapsed")

# ---------------------------------------------------------------------
# BLOOMBERG-STYLE HIGH-DENSITY TERMINAL STYLING
# ---------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;600;700&display=swap');

    /* Global Monospace & Terminal Reset */
    html, body, [class*="css"], div, p, span, label, th, td, input, button {
        font-family: 'Roboto Mono', 'Courier New', monospace !important;
        font-size: 11px !important;
        color: #e0e0e0 !important;
    }

    .stApp {
        background-color: #000000 !important;
    }

    /* Zero out padding for max density */
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }

    /* Full-Width Scrolling Ticker Tape */
    .ticker-wrap {
        width: 100%;
        overflow: hidden;
        background-color: #050505;
        color: #ff9900;
        border-top: 1px solid #222;
        border-bottom: 1px solid #333;
        margin-bottom: 8px;
        padding: 4px 0;
    }
    .ticker {
        display: inline-block;
        white-space: nowrap;
        animation: ticker 35s linear infinite;
        font-size: 12px !important;
        font-weight: 600;
    }
    .ticker__item {
        display: inline-block;
        padding: 0 25px;
    }
    @keyframes ticker {
        0% { transform: translate3d(0, 0, 0); }
        100% { transform: translate3d(-100%, 0, 0); }
    }

    /* Terminal KPI Panels */
    .kpi-container {
        display: flex;
        gap: 8px;
        margin-bottom: 8px;
    }
    .kpi-card {
        flex: 1;
        padding: 6px 10px;
        border: 1px solid #333;
        background-color: #080808;
    }
    .kpi-title {
        font-size: 10px !important;
        color: #888 !important;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .kpi-value {
        font-size: 16px !important;
        font-weight: 700 !important;
        color: #ffffff !important;
        margin: 2px 0;
    }
    .kpi-change { font-size: 11px !important; font-weight: 700; }
    
    /* Neon Semantic Colors */
    .neon-green { color: #00ff66 !important; }
    .neon-red { color: #ff3333 !important; }
    .amber-text { color: #ff9900 !important; }

    /* Terminal Border Boxes */
    .terminal-box {
        border: 1px solid #222;
        background-color: #050505;
        padding: 6px;
        margin-bottom: 8px;
    }
    
    .panel-header {
        font-size: 11px !important;
        font-weight: 700 !important;
        color: #ff9900 !important;
        text-transform: uppercase;
        border-bottom: 1px solid #222;
        padding-bottom: 4px;
        margin-bottom: 6px;
        letter-spacing: 0.5px;
    }

    /* Compact Movers Table */
    .movers-table {
        width: 100%;
        border-collapse: collapse;
    }
    .movers-table th {
        color: #666 !important;
        border-bottom: 1px solid #222;
        text-align: left;
        padding: 2px 4px;
        font-size: 10px !important;
    }
    .movers-table td {
        padding: 3px 4px;
        border-bottom: 1px solid #111;
        font-size: 11px !important;
    }

    /* Customizing Streamlit Controls */
    div[data-baseweb="select"] > div {
        background-color: #0a0a0a !important;
        border: 1px solid #333 !important;
        color: #e0e0e0 !important;
        border-radius: 0px !important;
    }
    .stButton>button {
        background-color: #111 !important;
        color: #ff9900 !important;
        border: 1px solid #ff9900 !important;
        border-radius: 0px !important;
        font-weight: 700 !important;
        text-transform: uppercase;
    }
    .stButton>button:hover {
        background-color: #ff9900 !important;
        color: #000000 !important;
    }
    .stDataFrame {
        border: 1px solid #222 !important;
    }
    .streamlit-expanderHeader {
        font-size: 12px !important;
        color: #ff9900 !important;
        background-color: #111 !important;
        border-bottom: 1px solid #333;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# DATA LAYER & UTILITIES
# ---------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_mcp_market_data(symbols):
    data = {}
    try:
        tickers = " ".join([f"{sym}.NS" for sym in symbols] + ["^NSEI", "^NSEBANK"])
        df = yf.download(tickers, period="2d", interval="1d", progress=False)['Close']
        for sym in symbols + ["^NSEI", "^NSEBANK"]:
            lookup = f"{sym}.NS" if not sym.startswith("^") else sym
            if lookup in df.columns and len(df[lookup].dropna()) >= 2:
                latest = float(df[lookup].iloc[-1])
                prev = float(df[lookup].iloc[-2])
                pct_change = ((latest - prev) / prev) * 100
                data[sym] = {"price": latest, "change": pct_change}
    except Exception:
        pass
    return data

@st.cache_data(ttl=60)
def fetch_mcp_market_movers():
    try:
        syms = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "TATAMOTORS.NS", "ITC.NS", "L&T.NS", "AXISBANK.NS"]
        df = yf.download(syms, period="2d", interval="1d", progress=False)['Close']
        changes = ((df.iloc[-1] - df.iloc[-2]) / df.iloc[-2] * 100).dropna()
        
        gainers = changes.nlargest(5).reset_index()
        gainers.columns = ["Symbol", "Change (%)"]
        gainers["Symbol"] = gainers["Symbol"].str.replace(".NS", "")
        
        losers = changes.nsmallest(5).reset_index()
        losers.columns = ["Symbol", "Change (%)"]
        losers["Symbol"] = losers["Symbol"].str.replace(".NS", "")
        
        return gainers, losers
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=60)
def fetch_intraday_chart(symbol="^NSEI"):
    try:
        return yf.download(symbol, period="1d", interval="5m", progress=False)
    except Exception:
        return pd.DataFrame()

def get_market_status():
    now = dt.datetime.now(IST)
    if now.weekday() >= 5: return "CLOSED (WEEKEND)"
    t = now.time()
    if dt.time(9, 0) <= t < dt.time(9, 15): return "PRE-OPEN"
    elif dt.time(9, 15) <= t <= dt.time(15, 30): return "OPEN"
    return "CLOSED"

# ---------------------------------------------------------------------
# INITIALIZATION & TICKER TAPE
# ---------------------------------------------------------------------
if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS"]

# Watchlist Configuration Expander
with st.expander("WATCHLIST CONFIGURATION (CSV/XLSX)", expanded=False):
    uploaded_file = st.file_uploader("UPLOAD WATCHLIST FILE", type=["csv", "xlsx"])
    if uploaded_file is not None:
        try:
            df_upload = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
            col_target = [c for c in df_upload.columns if "sym" in c.lower() or "stock" in c.lower()][0]
            new_symbols = df_upload[col_target].dropna().astype(str).str.strip().str.upper().tolist()
            st.session_state["watchlist"] = new_symbols
            st.success(f"LOADED {len(new_symbols)} STOCKS FROM UPLOAD.")
        except Exception:
            st.error("FAILED TO PARSE. ENSURE IT CONTAINS A 'SYMBOL' COLUMN.")
            
    st.multiselect("CURRENT WATCHLIST", options=st.session_state["watchlist"], default=st.session_state["watchlist"], disabled=True)

market_data = fetch_mcp_market_data(st.session_state["watchlist"][:15])

# Continuous Terminal Ticker
ticker_html = '<div class="ticker-wrap"><div class="ticker">'
for sym, details in market_data.items():
    if not sym.startswith("^"):
        color_class = "neon-green" if details["change"] >= 0 else "neon-red"
        sign = "+" if details["change"] >= 0 else ""
        ticker_html += f'<div class="ticker__item">{sym} <span class="{color_class}">{details["price"]:.2f} ({sign}{details["change"]:.2f}%)</span></div>'
ticker_html += '</div></div>'
st.markdown(ticker_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# HEADER & KPI ROW
# ---------------------------------------------------------------------
kpi_html = '<div class="kpi-container">\n'
for idx_name, idx_sym in [("NIFTY 50", "^NSEI"), ("NIFTY BANK", "^NSEBANK")]:
    if idx_sym in market_data:
        val = market_data[idx_sym]
        color_class = "neon-green" if val["change"] >= 0 else "neon-red"
        sign = "+" if val["change"] >= 0 else ""
        kpi_html += f'<div class="kpi-card">\n<div class="kpi-title">{idx_name}</div>\n<div class="kpi-value">{val["price"]:,.2f}</div>\n<div class="kpi-change {color_class}">{sign}{val["change"]:.2f}%</div>\n</div>\n'

kpi_html += f'<div class="kpi-card">\n<div class="kpi-title">MARKET STATUS</div>\n<div class="kpi-value amber-text" style="font-size: 14px; margin-top: 2px;">{get_market_status()}</div>\n</div>\n'
kpi_html += f'<div class="kpi-card">\n<div class="kpi-title">TERMINAL TIME</div>\n<div class="kpi-value" style="font-size: 14px; margin-top: 2px;">{dt.datetime.now(IST).strftime("%H:%M:%S IST")}</div>\n</div>\n</div>'
st.markdown(kpi_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# ROW 1: CHART & MCP MARKET MOVERS
# ---------------------------------------------------------------------
col_chart, col_movers = st.columns([0.65, 0.35])

with col_chart:
    st.markdown('<div class="panel-header">NIFTY 50 INTRADAY REAL-TIME</div>', unsafe_allow_html=True)
    chart_df = fetch_intraday_chart("^NSEI")
    if not chart_df.empty:
        if isinstance(chart_df.columns, pd.MultiIndex):
            close_col, open_col = chart_df['Close'].squeeze(), chart_df['Open'].squeeze()
        else:
            close_col, open_col = chart_df['Close'], chart_df['Open']
            
        last_close, first_open = float(close_col.iloc[-1]), float(open_col.iloc[0])
        is_positive = last_close >= first_open
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df.index, y=close_col, mode='lines',
            line=dict(color='#00ff66' if is_positive else '#ff3333', width=1.5)
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0), height=180,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=True, gridcolor='#222', autorange=True, tickfont=dict(size=9, color='#666')),
            plot_bgcolor='#000000', paper_bgcolor='#000000'
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with col_movers:
    st.markdown('<div class="panel-header">MCP TOP MARKET MOVERS</div>', unsafe_allow_html=True)
    gainers, losers = fetch_mcp_market_movers()
    
    col_g, col_l = st.columns(2)
    with col_g:
        if not gainers.empty:
            html = '<table class="movers-table"><tr><th>GAINERS</th><th>%</th></tr>'
            for _, row in gainers.iterrows():
                html += f'<tr><td>{row["Symbol"]}</td><td class="neon-green">+{row["Change (%)"]:.2f}%</td></tr>'
            html += '</table>'
            st.markdown(html, unsafe_allow_html=True)
            
    with col_l:
        if not losers.empty:
            html = '<table class="movers-table"><tr><th>LOSERS</th><th>%</th></tr>'
            for _, row in losers.iterrows():
                html += f'<tr><td>{row["Symbol"]}</td><td class="neon-red">{row["Change (%)"]:.2f}%</td></tr>'
            html += '</table>'
            st.markdown(html, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# ROW 2: LIVE NEWS TERMINAL
# ---------------------------------------------------------------------
st.markdown('<div class="panel-header" style="margin-top: 10px;">LIVE NEWS & CORPORATE ANNOUNCEMENT DESK</div>', unsafe_allow_html=True)

col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([0.2, 0.2, 0.4, 0.2])
with col_ctrl1:
    refresh_interval = st.selectbox("Auto-Refresh", options=["Manual", "1 Minute", "3 Minutes", "5 Minutes"], label_visibility="collapsed")
with col_ctrl2:
    lookback_hours = st.number_input("Lookback (Hrs)", min_value=1, max_value=72, value=24, label_visibility="collapsed")
with col_ctrl3:
    search_query = st.text_input("Global Search", placeholder="FILTER BY TICKER, HEADLINE, SOURCE...", label_visibility="collapsed")
with col_ctrl4:
    fetch_triggered = st.button("RUN FETCH", type="primary", use_container_width=True)

if refresh_interval != "Manual":
    st_autorefresh(interval=int(refresh_interval.split()[0]) * 60000, key="data_refresh")

if fetch_triggered or (refresh_interval != "Manual"):
    with st.spinner("POLLING SOURCES..."):
        raw_articles = fetch_all_sources(st.session_state["watchlist"], hours_back=lookback_hours)
        if raw_articles:
            processed = [{"category": ", ".join(classify_categories(a["headline"])), "impact": classify_impact(a["headline"]), **a} for a in raw_articles]
            st.session_state["news_df"] = pd.DataFrame(deduplicate_articles(processed))
        else:
            st.session_state["news_df"] = pd.DataFrame()

if "news_df" in st.session_state and not st.session_state["news_df"].empty:
    df = st.session_state["news_df"].copy()
    if search_query:
        df = df[df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)]
    
    cols_to_export = [c for c in ["stock_symbol", "published_time", "impact", "category", "headline", "source", "source_type", "article_url"] if c in df.columns]
    
    styled_df = df[cols_to_export].style.map(
        lambda v: "color: #ff3333; font-weight: bold;" if v == "HIGH" else ("color: #ff9900; font-weight: bold;" if v == "MEDIUM" else "color: #00ff66;"), 
        subset=['impact']
    )
    
    st.dataframe(
        styled_df,
        column_config={
            "article_url": st.column_config.LinkColumn("LINK", display_text="OPEN"),
            "published_time": "TIME (IST)", "stock_symbol": "TICKER", "impact": "IMPACT", "category": "CATEGORY", "headline": "HEADLINE", "source": "SOURCE", "source_type": "TYPE"
        },
        use_container_width=True, hide_index=True, height=520
    )
else:
    st.info("PRESS 'RUN FETCH' OR WAIT FOR AUTO-REFRESH CYCLE.")
