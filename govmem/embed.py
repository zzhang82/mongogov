"""Voyage embeddings with a disk cache, so reruns and the eval do not spend rate limit."""
import hashlib
import json
import math
import time
from pathlib import Path

from . import config

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "embeddings.json"
_cache = None


def _load():
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    return _cache


def _key(text):
    return hashlib.sha256((config.EMBED_MODEL + "\n" + text).encode()).hexdigest()


def embed(texts):
    """Return one 1024-dim vector per text. All missing texts go in one API call."""
    cache = _load()
    missing = [t for t in dict.fromkeys(texts) if _key(t) not in cache]
    if missing:
        import voyageai
        if not config.VOYAGE_API_KEY:
            raise SystemExit("VOYAGE_API_KEY is not set. Put it in .env.")
        client = voyageai.Client(api_key=config.VOYAGE_API_KEY, max_retries=0)
        for attempt in range(4):
            try:
                out = client.embed(missing, model=config.EMBED_MODEL)
                break
            except Exception as exc:
                if "rate" not in str(exc).lower() or attempt == 3:
                    raise
                print("  voyage rate limit; waiting 25s (attempt %d of 4)" % (attempt + 1), flush=True)
                time.sleep(25)
        for text, vec in zip(missing, out.embeddings):
            if len(vec) != config.EMBED_DIMS:
                raise SystemExit("Voyage returned %d dims, expected %d" % (len(vec), config.EMBED_DIMS))
            cache[_key(text)] = vec
        CACHE.parent.mkdir(exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache))
        tmp.replace(CACHE)
    return [cache[_key(t)] for t in texts]


def cosine(a, b):
    """Exact cosine similarity. This raw value is what every threshold is compared with."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def ticket_text(ticket):
    return (ticket["subject"].strip() + "\n" + ticket["body"].strip())
