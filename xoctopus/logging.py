"""Logging helpers."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "xoctopus.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )

