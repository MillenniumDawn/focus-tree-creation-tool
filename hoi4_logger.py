import logging
import os
import sys

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

log = logging.getLogger("HOI4CM")


def log_startup():
    log.info("=== HOI4 Content Maker starting ===")
    log.info(f"Python {sys.version}")
    log.info(f"Platform: {sys.platform}")
    log.info(f"DISPLAY={os.environ.get('DISPLAY', '(unset)')}")
