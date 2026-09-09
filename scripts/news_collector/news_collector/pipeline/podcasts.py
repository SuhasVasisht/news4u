"""Local, cached full-audio transcription when publishers do not provide text."""
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import threading
import fcntl

import httpx
from news_collector.pipeline.images import download

_transcription_lock = threading.Lock()


def transcribe_episode(url, repository, user_agent):
    cache_dir = repository.db.path.parent / "transcripts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = sha256(url.encode()).hexdigest()
    cache = cache_dir / f"{key}.json"
    model_name = os.environ.get("NEWS_TRANSCRIPTION_MODEL", "small.en")
    with _transcription_lock, (cache_dir / f"{key}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if cache.exists():
            cached = json.loads(cache.read_text())
            if cached.get("model") == model_name:
                return cached
        from faster_whisper import WhisperModel
        with httpx.Client(timeout=60, follow_redirects=False, headers={"User-Agent": user_agent}) as client:
            audio, _ = download(client, url, 180_000_000)
        model = WhisperModel(model_name,
                             device="cpu", compute_type="int8", cpu_threads=8)
        segments, info = model.transcribe(BytesIO(audio), beam_size=5, vad_filter=True)
        if info.duration > 4 * 3600:
            raise ValueError("Episode exceeds the four-hour transcription budget")
        lines, last_end = [], 0
        for segment in segments:
            lines.append(f"[{int(segment.start) // 60:02d}:{int(segment.start) % 60:02d}] {segment.text.strip()}")
            last_end = segment.end
            if len(lines) % 200 == 0:
                print(f"Transcribed {int(last_end / 60)} / {int(info.duration / 60)} minutes", flush=True)
        if not lines or last_end < info.duration * 0.9:
            raise ValueError("Incomplete audio transcript; episode held")
        result = {"text": "\n".join(lines), "duration": info.duration,
                  "model": model_name, "audio": url}
        temp = cache.with_suffix(".tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False))
        temp.replace(cache)
        return result
