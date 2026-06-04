"""Display helpers for OpenCV-based tools.

Detects the actual screen size and computes a scale factor that keeps the
displayed image inside the visible work area (after taskbar + window chrome).
"""
from __future__ import annotations

import numpy as np

# Leave room for the Windows taskbar, title bar, menu chrome, etc.
DEFAULT_MARGIN_W = 60
DEFAULT_MARGIN_H = 140


def screen_size() -> tuple[int, int]:
    """Return (width, height) of the primary monitor in pixels.

    Falls back to (1280, 720) if tkinter is unavailable for any reason.
    """
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.destroy()
        return w, h
    except Exception:
        return 1280, 720


def compute_fit_scale(
    image: np.ndarray,
    margin_w: int = DEFAULT_MARGIN_W,
    margin_h: int = DEFAULT_MARGIN_H,
) -> float:
    """Return a scale factor in (0, 1] that fits `image` within the visible
    screen area minus margins. Never upscales (caps at 1.0)."""
    sw, sh = screen_size()
    max_w = max(200, sw - margin_w)
    max_h = max(200, sh - margin_h)
    h, w = image.shape[:2]
    return min(max_w / w, max_h / h, 1.0)
