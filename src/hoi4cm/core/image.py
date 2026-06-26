"""Pillow import helper.

Tries to import Pillow; if missing and not running from a frozen bundle,
attempts a one-shot ``pip install Pillow`` so the user's first launch works
without a manual install step. In a frozen (PyInstaller) binary the install
is skipped and the wizards fall back to placeholder text.

Exposes :data:`PIL_OK`, :data:`PILImage`, :data:`PILImageTk` for code that
wants to check availability before calling Pillow.
"""

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
    except Exception as e:
        _log.warning("Pillow auto-install failed: %s", e)
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
    if not _try_install_pillow():
        return None, None, False
    try:
        from PIL import Image, ImageTk

        _log.info("Pillow installed and imported OK")
        return Image, ImageTk, True
    except Exception as e:
        _log.warning("Pillow import still failed after install: %s", e)
        return None, None, False


PILImage, PILImageTk, PIL_OK = _import_pillow()


__all__ = ["PIL_OK", "PILImage", "PILImageTk"]
