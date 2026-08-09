from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger("advisory")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def emit(event: str, **fields: object) -> None:
    blocked = {
        "api_key",
        "cv_text",
        "file_name",
        "filename",
        "full_url",
        "job_text",
        "job_url",
        "prompt",
        "url",
    }
    safe = {key: value for key, value in fields.items() if key not in blocked}
    logger.info(json.dumps({"event": event, **safe}, sort_keys=True, default=str))


@contextmanager
def operation(name: str) -> Iterator[str]:
    run_id = uuid.uuid4().hex
    started = time.perf_counter()
    emit("operation.started", operation=name, run_id=run_id)
    try:
        yield run_id
    except Exception as exc:
        emit("operation.failed", operation=name, run_id=run_id, error_type=type(exc).__name__)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        emit("operation.finished", operation=name, run_id=run_id, duration_ms=duration_ms)
