from __future__ import annotations

import hashlib
import json
import math
import os
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

EMBED_DIM = 256
_DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings"
_DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
_DEFAULT_TIMEOUT_SECONDS = 10
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_DETERMINISTIC_MODEL = "sha256-token-hash-v1"
_MAX_OLLAMA_RESPONSE_BYTES = 8_000_000


def _deterministic_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    normalized = " ".join(text.lower().split())
    if not normalized:
        return vec

    for token in normalized.split(" "):
        h = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest()
        idx = int.from_bytes(h[:2], "big") % dim
        sign = -1.0 if (h[2] & 1) else 1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def _is_loopback_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.hostname is None:
        return False
    return parsed.hostname in _LOCAL_HOSTS


def _ollama_embed(text: str, endpoint: str, model: str, timeout_seconds: int) -> list[float]:
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout_seconds) as resp:
        body = resp.read(_MAX_OLLAMA_RESPONSE_BYTES + 1)
    if len(body) > _MAX_OLLAMA_RESPONSE_BYTES:
        raise ValueError("Ollama embedding response exceeded the maximum size")
    decoded = json.loads(body.decode("utf-8"))
    embedding = decoded.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise ValueError("Ollama response did not contain an embedding vector")
    return [float(v) for v in embedding]


def embedding_identity() -> tuple[str, str]:
    backend = os.getenv("KINEKT_EMBEDDING_BACKEND", "deterministic").strip().lower()
    if backend == "deterministic":
        return backend, _DETERMINISTIC_MODEL
    if backend != "ollama":
        raise ValueError(f"Unsupported embedding backend: {backend}")
    model = os.getenv("KINEKT_OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL).strip() or _DEFAULT_OLLAMA_MODEL
    return backend, model


def embed_text(text: str) -> list[float]:
    backend, model = embedding_identity()
    if backend == "deterministic":
        return _deterministic_embed(text)

    endpoint = os.getenv("KINEKT_OLLAMA_URL", _DEFAULT_OLLAMA_URL).strip()
    timeout_raw = os.getenv("KINEKT_OLLAMA_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        timeout_seconds = max(1, min(int(timeout_raw), 30))
    except ValueError:
        timeout_seconds = _DEFAULT_TIMEOUT_SECONDS

    if not _is_loopback_endpoint(endpoint):
        raise ValueError("Ollama embedding endpoint must use a loopback host")

    try:
        return _ollama_embed(text, endpoint=endpoint, model=model, timeout_seconds=timeout_seconds)
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Ollama embedding failed for model {model!r}; fix the local endpoint or use "
            "KINEKT_EMBEDDING_BACKEND=deterministic"
        ) from exc
