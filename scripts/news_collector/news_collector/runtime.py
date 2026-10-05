from __future__ import annotations

from news_collector.collectors import (
    APCollector,
    AlphaVantageMoversCollector,
    AlphaVantageNewsCollector,
    GDELTCollector,
    GuardianCollector,
    HackerNewsCollector,
    NewsAPICollector,
    ProductHuntCollector,
    RedditCollector,
    RSSCollector,
    TechmemeCollector,
    TLDRCollector,
    XSearchCollector,
)
from news_collector.collectors.base import CollectorContext
from news_collector.collectors.newsroom import NewsroomCollector
from news_collector.collectors.dol_claims import DOLClaimsCollector
from news_collector.collectors.alphasignal import AlphaSignalCollector
from news_collector.collectors.newsletter_mail import NewsletterMailCollector
from news_collector.config import load_config
from news_collector.settings import get_settings
from news_collector.storage.db import Database
from news_collector.storage.repository import Repository


COLLECTOR_TYPES = {
    "dol_claims": DOLClaimsCollector,
    "newsletter_mail": NewsletterMailCollector,
    "alphasignal": AlphaSignalCollector,
    "newsroom": NewsroomCollector,
    "rss": RSSCollector,
    "guardian": GuardianCollector,
    "hackernews": HackerNewsCollector,
    "gdelt": GDELTCollector,
    "alphavantage_news": AlphaVantageNewsCollector,
    "alphavantage_movers": AlphaVantageMoversCollector,
    "newsapi": NewsAPICollector,
    "producthunt": ProductHuntCollector,
    "reddit": RedditCollector,
    "tldr": TLDRCollector,
    "techmeme": TechmemeCollector,
    "ap": APCollector,
    "x": XSearchCollector,
}


def build_runtime():
    settings = get_settings()
    config = load_config()
    db = Database(settings.db_path)
    repository = Repository(db)
    collectors = []
    for collector_config in config["collectors"]:
        if not collector_config.get("enabled", True):
            continue
        collector_cls = COLLECTOR_TYPES[collector_config["type"]]
        collectors.append(
            collector_cls(
                CollectorContext(
                    name=collector_config["name"],
                    config=collector_config,
                    defaults=config["defaults"],
                    settings=settings,
                    repository=repository,
                )
            )
        )
    collectors.sort(key=lambda collector: 1 if collector.context.config.get("unofficial") else 0)
    return settings, config, repository, collectors
