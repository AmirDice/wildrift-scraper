"""Thin wrapper around the `adb` CLI for screenshots and input events."""
from __future__ import annotations

import random
import subprocess
import time
from dataclasses import dataclass

import cv2
import numpy as np


def jittered_sleep(seconds: float, jitter_ms: int = 0) -> None:
    """time.sleep with optional uniform jitter in milliseconds. Clamps to >=0.05s."""
    if jitter_ms > 0:
        delta = random.uniform(-jitter_ms, jitter_ms) / 1000.0
    else:
        delta = 0.0
    time.sleep(max(0.05, seconds + delta))


class ADBError(RuntimeError):
    pass


@dataclass
class ADBClient:
    device: str = "127.0.0.1:7555"

    def connect(self) -> None:
        out = self._run(["connect", self.device], use_device=False)
        if "connected" not in out.lower() and "already" not in out.lower():
            raise ADBError(f"adb connect failed: {out.strip()}")

    def screenshot(self) -> np.ndarray:
        """Grab a screenshot from the device and return it as a BGR numpy array."""
        proc = subprocess.run(
            ["adb", "-s", self.device, "exec-out", "screencap", "-p"],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ADBError(f"screencap failed: {proc.stderr.decode(errors='ignore')}")
        arr = np.frombuffer(proc.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ADBError("Failed to decode screenshot PNG")
        return img

    def tap(self, x: int, y: int, jitter_px: int = 0) -> None:
        """Tap at (x, y). If jitter_px > 0, randomizes the actual tap point
        within a uniform [-jitter_px, +jitter_px] box around (x, y). Helps
        avoid pixel-perfect-repeat behavioral fingerprinting."""
        if jitter_px > 0:
            x += random.randint(-jitter_px, jitter_px)
            y += random.randint(-jitter_px, jitter_px)
        self._run(["shell", "input", "tap", str(x), str(y)])

    def back(self) -> None:
        """Press the Android system back key (KEYCODE_BACK)."""
        self._run(["shell", "input", "keyevent", "4"])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._run([
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms),
        ])

    def _run(self, args: list[str], use_device: bool = True) -> str:
        cmd = ["adb"]
        if use_device:
            cmd += ["-s", self.device]
        cmd += args
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ADBError(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
        return proc.stdout
