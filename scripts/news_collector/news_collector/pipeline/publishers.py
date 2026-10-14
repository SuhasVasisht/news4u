"""Shared publisher identity and deterministic edition limits."""
from urllib.parse import urlparse
from collections import Counter
import hashlib
import json

# Public institutions use several domain conventions. A .org suffix alone does
# not establish authority; allow only explicit institutional roots/subdomains.
PUBLIC_INSTITUTIONS = {
    "imf.org": "International Monetary Fund", "worldbank.org": "World Bank",
    "un.org": "United Nations", "oecd.org": "OECD",
    "wto.org": "World Trade Organization", "ilo.org": "International Labour Organization",
    "unesco.org": "UNESCO", "iaea.org": "International Atomic Energy Agency",
    "unhcr.org": "UNHCR", "unicef.org": "UNICEF", "ohchr.org": "UN Human Rights Office",
    "canada.ca": "Government of Canada",
}
PUBLIC_SUFFIXES = (".gov", ".gov.uk", ".europa.eu", ".int", ".gov.in", ".gov.au",
                   ".gc.ca", ".gouv.fr", ".go.jp", ".govt.nz", ".gov.br", ".gov.za",
                   ".admin.ch", ".bund.de", ".gov.cn", ".gob.mx")
PUBLIC_ROOTS = {suffix[1:] for suffix in PUBLIC_SUFFIXES if "." in suffix[1:]}

PUBLISHER_NAMES = {"bbc.com": "BBC", "bbc.co.uk": "BBC", "techcrunch.com": "TechCrunch", "theguardian.com": "The Guardian", "apnews.com": "AP", "arxiv.org": "arXiv", "sec.gov": "SEC", "techmeme.com": "Techmeme", "news.ycombinator.com": "Hacker News",
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
            "salesforce.com": "Salesforce", "hawley.senate.gov": "Senator Hawley's office"}

def public_institution(host):
    host = host.lower().rstrip(".").removeprefix("www.")
    return next((name for root, name in PUBLIC_INSTITUTIONS.items()
                 if host == root or host.endswith("." + root)), None)

def authority_policy_fingerprint():
    return hashlib.sha256(json.dumps([PUBLIC_INSTITUTIONS, PUBLIC_SUFFIXES, sorted(PUBLIC_ROOTS), PUBLISHER_NAMES], sort_keys=True).encode()).hexdigest()

def authoritative_host(host: str) -> bool:
    host = host.lower().rstrip(".").removeprefix("www.")
    return (bool(public_institution(host)) or host in PUBLIC_ROOTS
            or host.endswith(PUBLIC_SUFFIXES))

def publisher(url: str) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    institution = public_institution(host)
    if institution:
        return institution
    return PUBLISHER_NAMES.get(host, host)


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
