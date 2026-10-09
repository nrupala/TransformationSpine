# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ops logging contract (G10) for TransformationSpine services.

JSON-lines: ts/level/service/version/msg + ctx fields. One canonical file per
service (logs/<name>.log) + ERROR mirror (logs/errors.log), size-rotated.
Stdlib only. Mirrors the mesh-gateway / PortLedger contract so the whole
local stack shares one log shape.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import time
from pathlib import Path

SERVICE = "spine"
VERSION = "0.2.0"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "service": SERVICE,
            "version": getattr(record, "component_version", VERSION),
            "msg": record.getMessage(),
        }
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            rec.update(ctx)
        if record.exc_info:
            rec["error"] = self.formatException(record.exc_info)
        return json.dumps(rec)


def setup_logging(
    service: str = SERVICE,
    version: str = VERSION,
    log_dir: str | None = None,
) -> logging.Logger:
    """Configure and return the service logger (idempotent)."""
    resolved = Path(log_dir or os.environ.get("SPINE_LOG_DIR") or "./logs")
    resolved.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(service)
    if logger.handlers:  # already configured
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    main_h = logging.handlers.RotatingFileHandler(
        resolved / f"{service}.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    main_h.setFormatter(JsonFormatter())
    err_h = logging.handlers.RotatingFileHandler(
        resolved / "errors.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    err_h.setFormatter(JsonFormatter())
    err_h.setLevel(logging.ERROR)
    logger.addHandler(main_h)
    logger.addHandler(err_h)
    return logger


def get_logger(
    service: str = SERVICE, version: str = VERSION, log_dir: str | None = None
) -> logging.Logger:
    return setup_logging(service, version, log_dir)


def log(
    logger: logging.Logger, msg: str, level: int = logging.INFO, **ctx: object
) -> None:
    logger.log(level, msg, extra={"ctx": ctx})
