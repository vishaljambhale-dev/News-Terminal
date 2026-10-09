import re
from rapidfuzz import fuzz

CATEGORY_RULES = [
    ("EARNINGS", [r"\bq[1-4]\b", r"\bearnings\b", r"\bresults\b", r"\bnet profit\b", r"\bnet loss\b"]),
    ("REVENUE", [r"\brevenue\b", r"\btop.?line\b", r"\bsales grow"]),
    ("PROFIT", [r"\bprofit\b", r"\bnet income\b", r"\bpat\b"]),
    ("CONTRACT", [r"\border\b", r"\bcontract\b", r"\bdeal\b", r"\bacquisition\b"]),
]

IMPACT_RULES = {
    "HIGH": [r"\bcbi\b", r"\braid\b", r"\bfraud\b", r"\bresign\b", r"\bacquisition\b", r"\bprofit up\b", r"\bprofit down\b"],
    "MEDIUM": [r"\bcontract\b", r"\bdeal\b", r"\brevenue\b", r"\bpartnership\b"],
}

def classify_categories(headline):
    matched = []
    headline_lower = headline.lower()
    for cat, patterns in CATEGORY_RULES:
        if any(re.search(pat, headline_lower) for pat in patterns):
            matched.append(cat)
    return matched if matched else ["GENERAL"]

def classify_impact(headline):
    headline_lower = headline.lower()
    for level, patterns in IMPACT_RULES.items():
        if any(re.search(pat, headline_lower) for pat in patterns):
            return level
    return "LOW"

def deduplicate_articles(articles):
    unique_articles = []
    seen_headlines = []
    
    for article in articles:
        norm_h = re.sub(r"[^\w\s]", "", article["headline"].lower())
        is_dup = False
        for seen in seen_headlines:
            if fuzz.ratio(norm_h, seen) > 80:
                is_dup = True
                break
        if not is_dup:
            seen_headlines.append(norm_h)
            unique_articles.append(article)
            
    return unique_articles
