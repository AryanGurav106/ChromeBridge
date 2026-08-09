"""Standalone, dependency-free logger.

The original project logged through Logfire (a hosted SaaS). For a fully local,
offline setup we provide a drop-in replacement backed by the Python standard
library `logging` module. It keeps the exact public surface the rest of the
codebase relies on (``debug/info/warn/error/...``, ``set_job_id``) and tolerates
the arbitrary structured keyword arguments that Logfire accepted (e.g.
``logger.error(msg, exc_info=True)`` or ``logger.warn(msg, tool_id=...)``).
"""

import logging
import os
import sys
from contextvars import ContextVar
from typing import Any, Optional

_job_id_ctx: ContextVar[Optional[str]] = ContextVar("job_id", default=None)

_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Page content (and our own status strings) routinely contain non-ASCII characters.
# On Windows the console defaults to cp1252, so logging them would raise
# UnicodeEncodeError. Make the streams tolerant rather than crash the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

_root = logging.getLogger("chromebridge")
if not _root.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
    )
    _root.addHandler(_handler)
    _root.setLevel(getattr(logging, _LEVEL, logging.INFO))
    _root.propagate = False


class Logger:
    """Singleton logger with a Logfire-compatible signature."""

    _instance: Optional["Logger"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, environment: str = "dev", scrubbing: bool = False):
        # Nothing to configure; the module-level handler above does it once.
        self._logger = _root

    # -- internal helpers ---------------------------------------------------
    @staticmethod
    def _format(message: str, kwargs: dict) -> str:
        job_id = _job_id_ctx.get()
        prefix = f"[{job_id}] " if job_id else ""
        # Render any extra structured kwargs (minus logging-native ones) inline.
        extras = {k: v for k, v in kwargs.items() if k not in ("exc_info", "stack_info", "extra")}
        suffix = f" | {extras}" if extras else ""
        return f"{prefix}{message}{suffix}"

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        exc_info = kwargs.get("exc_info", False)
        self._logger.log(level, self._format(str(message), kwargs), exc_info=exc_info)

    # -- public API (mirrors the original Logfire-backed Logger) ------------
    def trace(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)

    def notice(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warn(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def fatal(self, message: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, message, **kwargs)

    def set_job_id(self, job_id) -> "Logger":
        if job_id:
            _job_id_ctx.set(str(job_id))
        return self
