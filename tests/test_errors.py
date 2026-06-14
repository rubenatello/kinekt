from __future__ import annotations

from kinekt.errors import format_error_json, normalize_exception


def test_normalize_exception_for_not_found() -> None:
    err = normalize_exception(FileNotFoundError("missing"))
    assert err.code == "ERR_NOT_FOUND"
    assert err.message == "missing"


def test_format_error_json_is_stable() -> None:
    payload = format_error_json(ValueError("invalid"))
    assert payload == '{"code": "ERR_INVALID_ARGUMENT", "message": "invalid"}'
