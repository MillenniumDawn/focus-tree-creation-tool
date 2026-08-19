"""Pillow import helper.

Tries to import Pillow. If it is missing, the wizards fall back to placeholder
text; the app does not shell out to ``pip`` unless the user opts in by setting
``HOI4CM_AUTO_INSTALL_PILLOW`` (a network install at import time is a supply-
chain surface, so it is off by default). Frozen (PyInstaller) binaries never
attempt an install.

Exposes :data:`PIL_OK`, :data:`PILImage`, :data:`PILImageTk` for code that
wants to check availability before calling Pillow.
"""

import os
import subprocess
import sys

from hoi4cm.core.logger import get_logger

_log = get_logger("image")


def _try_install_pillow():
    """Best-effort ``pip install Pillow``. Silent on failure."""
    try:
        _log.info("Pillow missing, attempting pip install...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "Pillow"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
        _log.warning("Pillow auto-install failed: %s", exc)
        return False


def _import_pillow():
    """Import Pillow, installing it first if it's missing and not frozen."""
    try:
        from PIL import Image, ImageTk

        return Image, ImageTk, True
    except ImportError:
        pass
    if getattr(sys, "frozen", False):
        _log.warning("Pillow not available in frozen binary — image previews disabled")
        return None, None, False
    if not os.environ.get("HOI4CM_AUTO_INSTALL_PILLOW"):
        _log.info(
            "Pillow not installed — run `pip install Pillow` to enable image previews"
        )
        return None, None, False
    if not _try_install_pillow():
        return None, None, False
    try:
        from PIL import Image, ImageTk

        _log.info("Pillow installed and imported OK")
        return Image, ImageTk, True
    except (ImportError, OSError, RuntimeError, ValueError, AttributeError) as exc:
        _log.warning("Pillow import still failed after install: %s", exc)
        return None, None, False


PILImage, PILImageTk, PIL_OK = _import_pillow()


__all__ = ["PIL_OK", "PILImage", "PILImageTk"]
