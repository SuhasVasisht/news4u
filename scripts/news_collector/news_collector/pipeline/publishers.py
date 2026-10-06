"""Shared publisher identity and deterministic edition limits."""
from urllib.parse import urlparse
from collections import Counter

def publisher(url: str) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return {"bbc.com": "BBC", "bbc.co.uk": "BBC", "techcrunch.com": "TechCrunch", "theguardian.com": "The Guardian", "apnews.com": "AP", "arxiv.org": "arXiv", "sec.gov": "SEC", "techmeme.com": "Techmeme", "news.ycombinator.com": "Hacker News",
            "lennysnewsletter.com": "Lenny's Newsletter", "dwarkesh.com": "Dwarkesh Podcast",
            "simonwillison.net": "Simon Willison", "interconnects.ai": "Interconnects",
            "latent.space": "Latent Space", "arstechnica.com": "Ars Technica",
            "theverge.com": "The Verge", "ft.com": "Financial Times",
            "federalreserve.gov": "Federal Reserve", "openai.com": "OpenAI",
            "anthropic.com": "Anthropic", "huggingface.co": "Hugging Face",
            "deepmind.google": "Google DeepMind", "marketwatch.com": "MarketWatch",
            "justice.gov": "US Department of Justice", "aljazeera.com": "Al Jazeera",
            "npr.org": "NPR", "krebsonsecurity.com": "Krebs on Security",
            "spectrum.ieee.org": "IEEE Spectrum", "macrumors.com": "MacRumors",
            "alphasignal.ai": "AlphaSignal", "blog.bytebytego.com": "ByteByteGo",
            "dol.gov": "US Department of Labor", "ecb.europa.eu": "European Central Bank",
            "salesforce.com": "Salesforce", "hawley.senate.gov": "Senator Hawley's office"}.get(host, host)


def limit_publishers(selection, packets, maximum=4):
    by_id = {packet["id"]: packet for packet in packets}
    counts, selected, removed = Counter(), [], []
    for key in selection["selected_ids"]:
        name = publisher(by_id[key]["url"])
        if counts[name] >= maximum:
            removed.append({"id": key, "reason": f"Publisher limit: at most {maximum} selected stories from {name}"})
        else:
            selected.append(key)
            counts[name] += 1
    if not removed:
        return selection
    return {**selection, "selected_ids": selected, "excluded": [*selection.get("excluded", []), *removed]}
