from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .query import QueryResult

_DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
_DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
_DEFAULT_TIMEOUT_SECONDS = 20
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class GenerationResult:
    text: str
    backend: str


def _is_loopback_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.hostname is None:
        return False
    return parsed.hostname in _LOCAL_HOSTS


def _deterministic_reply(
    workspace: str,
    session_id: str,
    user_message: str,
    hits: list[QueryResult],
    prior_user_count: int,
) -> str:
    lines: list[str] = []
    lines.append(f"Session: {session_id}")
    lines.append(f"Workspace: {workspace}")
    if prior_user_count > 0:
        lines.append(f"Prior turns in this session: {prior_user_count}")

    if hits:
        lines.append("Relevant indexed context:")
        for idx, hit in enumerate(hits, start=1):
            preview = " ".join(hit.content.split())[:140]
            lines.append(f"{idx}. {hit.file_path} [{hit.source}] score={hit.score:.3f} :: {preview}")
    else:
        lines.append("No indexed context found for this query. Run `kinekt ingest <workspace>`.")

    lines.append(f"Question: {user_message}")
    lines.append("Next: refine the query or ask for specific file-level details.")
    return "\n".join(lines)


def _ollama_reply(
    endpoint: str,
    model: str,
    timeout_seconds: int,
    workspace: str,
    session_id: str,
    user_message: str,
    hits: list[QueryResult],
    prior_user_count: int,
) -> str:
    context_lines: list[str] = []
    context_lines.append(f"Session ID: {session_id}")
    context_lines.append(f"Workspace: {workspace}")
    context_lines.append(f"Prior turns: {prior_user_count}")
    context_lines.append("Indexed context hits:")
    if hits:
        for idx, hit in enumerate(hits, start=1):
            context_lines.append(
                f"{idx}. path={hit.file_path} source={hit.source} score={hit.score:.3f} content={hit.content[:500]}"
            )
    else:
        context_lines.append("none")

    prompt = (
        "You are Kinekt, a local-first developer context assistant.\n"
        "Use only the provided indexed context when relevant.\n"
        "If context is missing, say so clearly and ask for a more specific query.\n\n"
        f"{chr(10).join(context_lines)}\n\n"
        f"User message: {user_message}\n"
        "Answer concisely with actionable next steps."
    )

    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout_seconds) as resp:
        body = resp.read()
    decoded = json.loads(body.decode("utf-8"))
    response = decoded.get("response")
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Ollama response did not contain text")
    return response.strip()


def generate_agent_reply(
    workspace: str,
    session_id: str,
    user_message: str,
    hits: list[QueryResult],
    prior_user_count: int,
) -> GenerationResult:
    backend = os.getenv("KINEKT_GENERATION_BACKEND", "deterministic").strip().lower()
    if backend != "ollama":
        return GenerationResult(
            text=_deterministic_reply(
                workspace=workspace,
                session_id=session_id,
                user_message=user_message,
                hits=hits,
                prior_user_count=prior_user_count,
            ),
            backend="deterministic",
        )

    endpoint = os.getenv("KINEKT_OLLAMA_GENERATE_URL", _DEFAULT_OLLAMA_URL).strip()
    model = os.getenv("KINEKT_OLLAMA_GENERATE_MODEL", _DEFAULT_OLLAMA_MODEL).strip() or _DEFAULT_OLLAMA_MODEL
    timeout_raw = os.getenv("KINEKT_OLLAMA_GENERATE_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        timeout_seconds = max(1, min(int(timeout_raw), 60))
    except ValueError:
        timeout_seconds = _DEFAULT_TIMEOUT_SECONDS

    if not _is_loopback_endpoint(endpoint):
        return GenerationResult(
            text=_deterministic_reply(
                workspace=workspace,
                session_id=session_id,
                user_message=user_message,
                hits=hits,
                prior_user_count=prior_user_count,
            ),
            backend="deterministic",
        )

    try:
        text = _ollama_reply(
            endpoint=endpoint,
            model=model,
            timeout_seconds=timeout_seconds,
            workspace=workspace,
            session_id=session_id,
            user_message=user_message,
            hits=hits,
            prior_user_count=prior_user_count,
        )
        return GenerationResult(text=text, backend="ollama")
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return GenerationResult(
            text=_deterministic_reply(
                workspace=workspace,
                session_id=session_id,
                user_message=user_message,
                hits=hits,
                prior_user_count=prior_user_count,
            ),
            backend="deterministic",
        )
