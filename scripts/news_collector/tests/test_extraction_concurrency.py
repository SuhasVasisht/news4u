from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time

from news_collector.pipeline import extract


def test_native_text_extraction_is_serialized(monkeypatch):
    active, peak = 0, 0
    counter_lock = Lock()

    def native(*args, **kwargs):
        nonlocal active, peak
        with counter_lock:
            active += 1
            peak = max(peak, active)
        time.sleep(.005)
        with counter_lock:
            active -= 1
        return "Extracted source text"

    monkeypatch.setattr(extract.trafilatura, "extract", native)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: extract.extract_text_from_html("<p>Source</p>", "https://example.com"), range(24)))
    assert peak == 1
    assert results == ["Extracted source text"] * 24
