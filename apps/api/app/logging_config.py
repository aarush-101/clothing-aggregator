"""Structured logging.

Log records carry a machine-readable event name plus arbitrary key/value
context. In production (``LOG_FORMAT=json``) each record is emitted as a single
JSON line suitable for Railway/Render/Fly log drains; in development a compact
human-readable format is used instead.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
search_id_var: ContextVar[Optional[str]] = ContextVar("search_id", default=None)

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName", "taskName", "context",
}

# Keys whose values must never reach the logs.
_REDACTED_KEYS = {"api_key", "anthropic_api_key", "authorization", "token", "password"}


def _ambient_context() -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    request_id = request_id_var.get()
    if request_id:
        ctx["request_id"] = request_id
    search_id = search_id_var.get()
    if search_id:
        ctx["search_id"] = search_id
    return ctx


def _redact(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: ("[redacted]" if key.lower() in _REDACTED_KEYS else value)
        for key, value in fields.items()
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
        }
        payload.update(_ambient_context())
        payload.update(_redact(getattr(record, "context", {}) or {}))
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    _COLOURS = {
        "DEBUG": "\033[38;5;245m",
        "INFO": "\033[38;5;39m",
        "WARNING": "\033[38;5;214m",
        "ERROR": "\033[38;5;203m",
        "CRITICAL": "\033[38;5;203m",
    }
    _RESET = "\033[0m"

    def __init__(self, use_colour: bool = True) -> None:
        super().__init__()
        self.use_colour = use_colour and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        fields = dict(_ambient_context())
        fields.update(_redact(getattr(record, "context", {}) or {}))
        stamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S")
        level = record.levelname.ljust(7)
        if self.use_colour:
            colour = self._COLOURS.get(record.levelname, "")
            level = f"{colour}{level}{self._RESET}"
        suffix = " ".join(f"{k}={v}" for k, v in fields.items())
        line = f"{stamp} {level} {record.getMessage()}"
        if suffix:
            line = f"{line}  {suffix}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


class StructuredLogger:
    """Thin wrapper giving every log call keyword context."""

    __slots__ = ("_logger",)

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _log(self, level: int, event: str, exc_info: bool = False, **fields: Any) -> None:
        if self._logger.isEnabledFor(level):
            self._logger.log(level, event, extra={"context": fields}, exc_info=exc_info)

    def debug(self, event: str, **fields: Any) -> None:
        self._log(logging.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._log(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._log(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._log(logging.ERROR, event, **fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._log(logging.ERROR, event, exc_info=True, **fields)


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    formatter: logging.Formatter = JsonFormatter() if fmt == "json" else ConsoleFormatter()
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn duplicates access logs through its own handlers; route them here.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(noisy)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(logging.getLogger(name))


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]
