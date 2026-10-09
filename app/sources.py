import feedparser
import datetime as dt
from dateutil import parser as dt_parser
import pytz

IST = pytz.timezone("Asia/Kolkata")

def fetch_news_for_symbols(symbols, hours_back=24):
    cutoff_time = dt.datetime.now(IST) - dt.timedelta(hours=hours_back)
    all_articles = []

    for symbol in symbols:
        url = f"https://news.google.com/rss/search?q={symbol}+stock+news&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)
        
        for entry in feed.entries:
            try:
                published = dt_parser.parse(entry.published).astimezone(IST)
            except Exception:
                published = dt.datetime.now(IST)
                
            if published >= cutoff_time:
                all_articles.append({
                    "stock_symbol": symbol,
                    "headline": entry.title,
                    "published_time": published.strftime("%Y-%m-%d %H:%M IST"),
                    "published_dt": published,
                    "source": getattr(entry, "source", {}).get("title", "Google News"),
                    "article_url": entry.link,
                })

    return all_articles
