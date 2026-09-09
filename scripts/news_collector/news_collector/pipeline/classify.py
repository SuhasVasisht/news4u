from __future__ import annotations

import re

from news_collector.models import RawItem


TECH_TERMS = {"ai", "model", "chip", "semiconductor", "cloud", "startup", "software", "openai", "anthropic"}
FINANCE_TERMS = {"earnings", "guidance", "stock", "market", "merger", "acquisition", "ipo", "downgrade"}
POLITICS_TERMS = {"election", "white house", "parliament", "congress", "ministry", "sanctions", "supreme court"}


def classify_item(item: RawItem) -> str:
    text = " ".join(filter(None, [item.title, item.summary or "", " ".join(item.tags)])).lower()
    tokens = set(re.findall(r"\b[a-z]+\b", text))
    if FINANCE_TERMS & tokens:
        return "finance"
    if item.source in {"alphavantage_news", "alphavantage_movers", "sec_press"}:
        return "finance"
    if any(term in text for term in POLITICS_TERMS):
        return "politics"
    if any(term in text for term in TECH_TERMS if " " in term) or (TECH_TERMS & tokens):
        return "tech"
    return item.category
