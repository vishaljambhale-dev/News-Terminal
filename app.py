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
    .block-container { padding: 1rem 2rem !important; max-width: 100% !important; }
    html, body, p, div, span, label, th, td { font-size: 13px !important; }
    h1 { font-size: 22px !important; margin-bottom: 0px !important; }
    h2 { font-size: 18px !important; }
    h3 { font-size: 14px !important; font-weight: bold; margin-bottom: 5px; text-transform: uppercase; color: #555;}
    
    .ticker-wrap { width: 100%; overflow: hidden; background-color: #1e1e1e; color: #ffffff; padding-left: 100%; border-bottom: 1px solid #333; margin-bottom: 15px; }
    .ticker { display: inline-block; white-space: nowrap; padding-right: 100%; animation: ticker 40s linear infinite; font-family: monospace; font-size: 14px; line-height: 25px; }
    .ticker__item { display: inline-block; padding: 0 20px; }
    @keyframes ticker { 0% { transform: translate3d(0, 0, 0); } 100% { transform: translate3d(-100%, 0, 0); } }
    
    .kpi-container { display: flex; gap: 15px; margin-bottom: 15px; }
    .kpi-card { flex: 1; padding: 10px 15px; border-radius: 4px; border: 1px solid #ddd; background-color: #f8f9fa; }
    [data-theme="dark"] .kpi-card { background-color: #262730; border-color: #444; }
    .kpi-title { font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 5px; color: #555;}
    [data-theme="dark"] .kpi-title { color: #aaa; }
    .kpi-value { font-size: 18px; font-weight: bold; margin-bottom: 2px;}
    .kpi-change { font-size: 12px; font-weight: bold; }
    .color-green { color: #0f9d58; } .color-red { color: #d23f31; }
    .bg-green { background-color: rgba(15, 157, 88, 0.1); border: 1px solid rgba(15, 157, 88, 0.3); }
    .bg-red { background-color: rgba(210, 63, 49, 0.1); border: 1px solid rgba(210, 63, 49, 0.3); }
    
    .movers-table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }
    .movers-table th, .movers-table td { padding: 4px 8px; text-align: left; border-bottom: 1px solid #ddd; }
    [data-theme="dark"] .movers-table th, [data-theme="dark"] .movers-table td { border-bottom: 1px solid #444; }
    .movers-table th { background-color: rgba(0,0,0,0.05); font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# MCP INTEGRATION LAYER (NSE OFFICIAL DATA)
# ---------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_mcp_market_data(symbols):
    """
    INTEGRATION POINT: Replace the yfinance logic below with your MCP client call.
    Example MCP Call: client.call_tool("cm_get_live_market_data", {"symbols": symbols})
    """
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
def fetch_mcp_market_movers():
    """
    INTEGRATION POINT: Replace with MCP tool 'nse_get_market_movers'.
    Returns two dataframes: Top Gainers and Top Losers.
    """
    try:
        # Fallback simulation for structure
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
    if dt.time(9, 0) <= t < dt.time(9, 15): return "PRE-OPEN (09:00 - 09:15 IST)"
    elif dt.time(9, 15) <= t <= dt.time(15, 30): return "OPEN (09:15 - 15:30 IST)"
    return "CLOSED"

# ---------------------------------------------------------------------
# APP STATE & TICKER TAPE
# ---------------------------------------------------------------------
if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS"]

market_data = fetch_mcp_market_data(st.session_state["watchlist"][:15])

ticker_html = '<div class="ticker-wrap"><div class="ticker">'
for sym, details in market_data.items():
    if not sym.startswith("^"):
        color = "#0f9d58" if details["change"] >= 0 else "#d23f31"
        sign = "+" if details["change"] >= 0 else ""
        ticker_html += f'<div class="ticker__item">{sym} <span style="color:{color}">{details["price"]:.2f} ({sign}{details["change"]:.2f}%)</span></div>'
ticker_html += '</div></div>'
st.markdown(ticker_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# KPI CARDS
# ---------------------------------------------------------------------
kpi_html = '<div class="kpi-container">\n'
for idx_name, idx_sym in [("NIFTY 50", "^NSEI"), ("NIFTY BANK", "^NSEBANK")]:
    if idx_sym in market_data:
        val = market_data[idx_sym]
        color_class = "color-green" if val["change"] >= 0 else "color-red"
        bg_class = "bg-green" if val["change"] >= 0 else "bg-red"
        sign = "+" if val["change"] >= 0 else ""
        kpi_html += f'<div class="kpi-card {bg_class}">\n<div class="kpi-title">{idx_name}</div>\n<div class="kpi-value">{val["price"]:,.2f}</div>\n<div class="kpi-change {color_class}">{sign}{val["change"]:.2f}%</div>\n</div>\n'
kpi_html += f'<div class="kpi-card">\n<div class="kpi-title">MARKET STATUS</div>\n<div class="kpi-value" style="font-size: 14px; margin-top: 5px;">{get_market_status()}</div>\n</div>\n</div>'
st.markdown(kpi_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# ROW 1: CHART & MCP MARKET MOVERS
# ---------------------------------------------------------------------
col_chart, col_movers = st.columns([0.65, 0.35])

with col_chart:
    st.markdown("### NIFTY 50 INTRADAY")
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
            line=dict(color='#0f9d58' if is_positive else '#d23f31', width=2)
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0), height=220,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', autorange=True),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with col_movers:
    st.markdown("### MCP MARKET MOVERS")
    gainers, losers = fetch_mcp_market_movers()
    
    col_g, col_l = st.columns(2)
    with col_g:
        if not gainers.empty:
            html = '<table class="movers-table"><tr><th>Top Gainers</th><th>%</th></tr>'
            for _, row in gainers.iterrows():
                html += f'<tr><td>{row["Symbol"]}</td><td class="color-green">+{row["Change (%)"]:.2f}%</td></tr>'
            html += '</table>'
            st.markdown(html, unsafe_allow_html=True)
            
    with col_l:
        if not losers.empty:
            html = '<table class="movers-table"><tr><th>Top Losers</th><th>%</th></tr>'
            for _, row in losers.iterrows():
                html += f'<tr><td>{row["Symbol"]}</td><td class="color-red">{row["Change (%)"]:.2f}%</td></tr>'
            html += '</table>'
            st.markdown(html, unsafe_allow_html=True)

# ---------------------------------------------------------------------
# ROW 2: LIVE NEWS DESK & CONTROLS
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown("### LIVE NEWS DESK")

col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([0.2, 0.2, 0.4, 0.2])
with col_ctrl1:
    refresh_interval = st.selectbox("Auto-Refresh", options=["Manual", "1 Minute", "3 Minutes", "5 Minutes"], label_visibility="collapsed")
with col_ctrl2:
    lookback_hours = st.number_input("Lookback (Hrs)", min_value=1, max_value=72, value=24, label_visibility="collapsed")
with col_ctrl3:
    search_query = st.text_input("Global Search", placeholder="Search ticker, headline...", label_visibility="collapsed")
with col_ctrl4:
    fetch_triggered = st.button("Manual Fetch", type="primary", use_container_width=True)

if refresh_interval != "Manual":
    st_autorefresh(interval=int(refresh_interval.split()[0]) * 60000, key="data_refresh")

if fetch_triggered or (refresh_interval != "Manual"):
    with st.spinner("Polling sources..."):
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
        lambda v: "color: #d23f31; font-weight: bold;" if v == "HIGH" else ("color: #f2a900; font-weight: bold;" if v == "MEDIUM" else "color: #0f9d58;"), 
        subset=['impact']
    )
    
    st.dataframe(
        styled_df,
        column_config={
            "article_url": st.column_config.LinkColumn("Link", display_text="Open"),
            "published_time": "Time (IST)", "stock_symbol": "Ticker", "impact": "Impact", "category": "Category", "headline": "Headline", "source": "Source", "source_type": "Type"
        },
        use_container_width=True, hide_index=True, height=500
    )
else:
    st.info("Execute 'Manual Fetch' or wait for auto-refresh to populate the terminal.")
