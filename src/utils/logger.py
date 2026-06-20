"""Logging utilities providing consistent logging across project modules."""

import logging

_DEFAULT_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Create (or retrieve) a configured logger.

    Ensures that calling this function multiple times for the same
    ``name`` does not attach duplicate handlers.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.
        level: Logging level as a string (e.g. ``"INFO"``, ``"DEBUG"``).
            Defaults to ``"INFO"``.

    Returns:
        logging.Logger: A configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(fmt=_DEFAULT_FORMAT, datefmt=_DEFAULT_DATEFMT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False

    return logger