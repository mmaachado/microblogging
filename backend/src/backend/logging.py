import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.config import Settings

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_installed: list[logging.Handler] = []


def configure_logging(settings: Settings) -> None:
    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(FORMAT)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(
            settings.log_file, maxBytes=5 * 1024 * 1024, backupCount=3
        ),
    ]
    root = logging.getLogger()
    for old in _installed:
        root.removeHandler(old)
        old.close()
    _installed[:] = handlers
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.getLogger("backend").setLevel(settings.log_level)
    for name in ("aiosqlite", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
    access = logging.getLogger("uvicorn.access")
    access.setLevel(logging.WARNING)
    access.propagate = False
