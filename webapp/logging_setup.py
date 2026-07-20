"""Central logging setup shared by the web app and the standalone worker.

Plain text on **stdout** (container-friendly). ``LOG_LEVEL`` applies to *our* namespaces
only — the root logger deliberately stays at WARNING so third-party DEBUG chatter
(urllib3 logs a line per connection on every DigiKey call) can't drown the log when
someone sets LOG_LEVEL=DEBUG. Third-party warnings and errors still surface.
"""
import logging
import sys
from typing import Optional

from webapp.config import settings

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
OUR_NAMESPACES = ("capinator", "webapp")


def configure_logging(level: Optional[str] = None) -> None:
    """Send logs to stdout and raise only our namespaces to ``level`` (default LOG_LEVEL)."""
    resolved = (level or settings.log_level).upper()
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format=FORMAT)
    logging.getLogger().setLevel(logging.WARNING)  # explicit: basicConfig no-ops if configured
    for name in OUR_NAMESPACES:
        logging.getLogger(name).setLevel(resolved)
