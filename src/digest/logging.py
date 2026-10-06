import json
import logging
from typing import Any

logger = logging.getLogger("digest")


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(message)s")
    # HTTP debug logging can expose endpoint IDs or request metadata.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def event(name: str, **fields: Any) -> None:
    # Callers pass only correlation IDs, metrics and error class names.
    logger.info(json.dumps({"event": name, **fields}, separators=(",", ":")))
