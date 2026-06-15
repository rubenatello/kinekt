from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedError:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def normalize_exception(exc: Exception) -> NormalizedError:
    if isinstance(exc, FileNotFoundError):
        return NormalizedError(code="ERR_NOT_FOUND", message=str(exc))
    if isinstance(exc, PermissionError):
        return NormalizedError(code="ERR_PERMISSION_DENIED", message=str(exc))
    if isinstance(exc, sqlite3.Error):
        return NormalizedError(code="ERR_STORAGE", message=str(exc))
    if isinstance(exc, subprocess.CalledProcessError):
        return NormalizedError(code="ERR_GIT_COMMAND", message=str(exc))
    if isinstance(exc, ValueError):
        return NormalizedError(code="ERR_INVALID_ARGUMENT", message=str(exc))
    if isinstance(exc, RuntimeError):
        return NormalizedError(code="ERR_RUNTIME", message=str(exc))
    return NormalizedError(code="ERR_INTERNAL", message=str(exc) or exc.__class__.__name__)


def format_error_json(exc: Exception) -> str:
    return json.dumps(normalize_exception(exc).as_dict(), sort_keys=True)
