from __future__ import annotations

MAX_QUERY_LIMIT = 20
MAX_READ_CHARS = 50_000
MAX_HISTORY_LIMIT = 100
MAX_AGENT_QUERY_LIMIT = 10
MAX_AGENT_HISTORY_WINDOW = 20
MAX_QUERY_CHARS = 10_000
MAX_USER_MESSAGE_CHARS = 20_000
MAX_STORED_MESSAGE_CHARS = 100_000
MAX_SESSION_ID_CHARS = 200
MAX_RESULT_CONTENT_CHARS = 20_000


def _clamp(value: int, maximum: int) -> int:
    return max(1, min(value, maximum))


def clamp_query_limit(limit: int) -> int:
    return _clamp(limit, MAX_QUERY_LIMIT)


def clamp_read_chars(max_chars: int) -> int:
    return _clamp(max_chars, MAX_READ_CHARS)


def clamp_history_limit(limit: int) -> int:
    return _clamp(limit, MAX_HISTORY_LIMIT)


def clamp_agent_query_limit(limit: int) -> int:
    return _clamp(limit, MAX_AGENT_QUERY_LIMIT)


def clamp_agent_history_window(window: int) -> int:
    return _clamp(window, MAX_AGENT_HISTORY_WINDOW)


def validate_text(value: str, *, field: str, maximum: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    if len(cleaned) > maximum:
        raise ValueError(f"{field} exceeds the maximum length of {maximum} characters")
    return cleaned
