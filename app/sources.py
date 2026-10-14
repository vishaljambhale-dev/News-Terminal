import asyncio
import datetime as dt
import urllib.parse
import email.utils as eut
import feedparser
import httpx
import pytz

IST = pytz.timezone("Asia/Kolkata")

# Publishers from rss_sources.py
INDIA_RSS_FEEDS = [
    ("Moneycontrol", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("Economic Times", "https://economictimes.indiatimes.com/rssfeedstopstories.cms"),
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/markets/1977021501.cms"),
    ("Business Standard", "https://www.business-standard.com/rss/markets/stock-market-news-10618.rss"),
    ("Mint (Livemint)", "https://www.livemint.com/rss/markets"),
    ("CNBC-TV18", "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml"),
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/stock-markets/feeder/default.rss"),
    ("The Hindu Markets", "https://www.thehindu.com/business/markets/feeder/default.rss"),
]

GLOBAL_RSS_FEEDS = [
    ("Financial Times", "https://www.ft.com/markets?format=rss"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("Investing.com", "https://www.investing.com/rss/news.rss"),
]

BSE_NOTICES_URL = "https://www.bseindia.com/data/xml/notices.xml"
NSE_WARMUP_URL = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
NSE_ANNOUNCEMENTS_API = "https://www.nseindia.com/api/corporate-announcements?index=equities"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}


def _parse_pubdate(entry) -> dt.datetime | None:
    for key in ("published", "updated", "pubDate"):
        raw = entry.get(key)
        if raw:
            try:
                parsed = eut.parsedate_to_datetime(raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                return parsed.astimezone(IST)
            except (TypeError, ValueError):
                continue
    if entry.get("published_parsed"):
        try:
            return dt.datetime(*entry.published_parsed[:6], tzinfo=dt.timezone.utc).astimezone(IST)
        except Exception:
            return None
    return None


async def fetch_rss(client: httpx.AsyncClient, name: str, url: str, source_type: str, timeout: float = 10.0) -> list[dict]:
    articles = []
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        for entry in parsed.entries:
            headline = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not headline or not link:
                continue
            pub_dt = _parse_pubdate(entry)
            articles.append({
                "headline": headline,
                "article_url": link,
                "source": name,
                "source_type": source_type,
                "published_dt": pub_dt or dt.datetime.now(IST),
                "published_time": (pub_dt or dt.datetime.now(IST)).strftime("%Y-%m-%d %H:%M IST"),
                "summary": (entry.get("summary") or entry.get("description") or "").strip()[:500],
            })
    except Exception:
        pass
    return articles


async def fetch_bse_notices(client: httpx.AsyncClient, timeout: float = 10.0) -> list[dict]:
    articles = []
    try:
        resp = await client.get(BSE_NOTICES_URL, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        for entry in parsed.entries:
            headline = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if headline:
                now_ist = dt.datetime.now(IST)
                articles.append({
                    "headline": headline,
                    "article_url": link or BSE_NOTICES_URL,
                    "source": "BSE Exchange",
                    "source_type": "BSE",
                    "published_dt": now_ist,
                    "published_time": now_ist.strftime("%Y-%m-%d %H:%M IST"),
                    "summary": (entry.get("summary") or "").strip()[:500],
                })
    except Exception:
        pass
    return articles


async def fetch_nse_announcements(client: httpx.AsyncClient, timeout: float = 10.0) -> list[dict]:
    articles = []
    try:
        await client.get(NSE_WARMUP_URL, timeout=timeout, headers=BROWSER_HEADERS, follow_redirects=True)
        resp = await client.get(NSE_ANNOUNCEMENTS_API, timeout=timeout, headers=BROWSER_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            for item in data:
                headline = (item.get("desc") or item.get("attchmntText") or "").strip()
                symbol = (item.get("symbol") or "").strip()
                if not headline:
                    continue
                display = f"{symbol}: {headline}" if symbol else headline
                pdf_url = item.get("attchmntFile") or ""
                raw_dt = item.get("an_dt") or item.get("sort_date")
                pub_dt = None
                if raw_dt:
                    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
                        try:
                            pub_dt = IST.localize(dt.datetime.strptime(raw_dt, fmt))
                            break
                        except ValueError:
                            continue
                pub_dt = pub_dt or dt.datetime.now(IST)
                articles.append({
                    "headline": display,
                    "article_url": pdf_url or NSE_ANNOUNCEMENTS_API,
                    "source": "NSE Exchange",
                    "source_type": "NSE",
                    "published_dt": pub_dt,
                    "published_time": pub_dt.strftime("%Y-%m-%d %H:%M IST"),
                    "summary": symbol,
                })
    except Exception:
        pass
    return articles


async def fetch_google_news_search(client: httpx.AsyncClient, query: str, timeout: float = 10.0) -> list[dict]:
    articles = []
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        for entry in parsed.entries:
            headline = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not headline or not link:
                continue
            source_label = "Google News"
            if " - " in headline:
                source_label = headline.rsplit(" - ", 1)[-1].strip() or source_label
            pub_dt = _parse_pubdate(entry) or dt.datetime.now(IST)
            articles.append({
                "headline": headline,
                "article_url": link,
                "source": source_label,
                "source_type": "SEARCH_RESULT",
                "published_dt": pub_dt,
                "published_time": pub_dt.strftime("%Y-%m-%d %H:%M IST"),
                "summary": (entry.get("summary") or "").strip()[:500],
            })
    except Exception:
        pass
    return articles


async def poll_all_sources_async(symbols: list[str]) -> list[dict]:
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        tasks = []
        
        # 1. India Publisher RSS
        for name, url in INDIA_RSS_FEEDS:
            tasks.append(fetch_rss(client, name, url, "RSS_INDIA"))
            
        # 2. Global Publisher RSS
        for name, url in GLOBAL_RSS_FEEDS:
            tasks.append(fetch_rss(client, name, url, "RSS_GLOBAL"))
            
        # 3. BSE Notices
        tasks.append(fetch_bse_notices(client))
        
        # 4. NSE Announcements
        tasks.append(fetch_nse_announcements(client))
        
        # 5. Google News per Watchlist Symbol
        for sym in symbols:
            tasks.append(fetch_google_news_search(client, f"{sym} stock news"))

        results = await asyncio.gather(*tasks)
        
        all_articles = []
        for res in results:
            all_articles.extend(res)
            
        return all_articles


def fetch_all_sources(symbols: list[str], hours_back: int = 24) -> list[dict]:
    # 1. Manually create and manage a new event loop for this specific Streamlit thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        raw_articles = loop.run_until_complete(poll_all_sources_async(symbols))
    finally:
        loop.close()
    
    # 2. Filter the results
    cutoff = dt.datetime.now(IST) - dt.timedelta(hours=hours_back)
    filtered_articles = []
    
    for art in raw_articles:
        if art["published_dt"] >= cutoff:
            text_check = f"{art['headline']} {art['summary']}".lower()
            matched_symbols = [sym for sym in symbols if sym.lower() in text_check]
            
            if matched_symbols:
                for sym in matched_symbols:
                    c = art.copy()
                    c["stock_symbol"] = sym
                    filtered_articles.append(c)
            elif art["source_type"] in ["SEARCH_RESULT"]:
                filtered_articles.append(art)

    return filtered_articles
