"""Thin wrapper around the `adb` CLI for screenshots and input events."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

import cv2
import numpy as np


class ADBError(RuntimeError):
    pass


@dataclass
class ADBClient:
    device: str = "127.0.0.1:7555"

    def connect(self) -> None:
        # Only TCP/IP devices (IP:port form, e.g. 127.0.0.1:7555) need an
        # explicit `adb connect`. USB-attached phones are already attached;
        # we just verify they show up in `adb devices`.
        if ":" in self.device:
            out = self._run(["connect", self.device], use_device=False)
            if "connected" not in out.lower() and "already" not in out.lower():
                raise ADBError(f"adb connect failed: {out.strip()}")
            return
        # USB serial — verify it's listed and authorized.
        out = self._run(["devices"], use_device=False)
        listed = False
        unauthorized = False
        for line in out.splitlines():
            if line.startswith(self.device + "\t") or line.startswith(self.device + " "):
                listed = True
                if "unauthorized" in line:
                    unauthorized = True
                break
        if not listed:
            raise ADBError(
                f"USB device '{self.device}' not found in `adb devices`. "
                "Plug it in, accept the 'Trust this computer' prompt on the phone, "
                "and run `adb devices` to confirm it appears."
            )
        if unauthorized:
            raise ADBError(
                f"USB device '{self.device}' is unauthorized. "
                "Look at the phone screen and tap 'Allow' on the USB-debugging prompt."
            )

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

    def tap(self, x: int, y: int, hold_ms: int = 200) -> None:
        """Tap at (x, y), held for `hold_ms` milliseconds.

        Implemented as a zero-distance swipe (`input swipe x y x y hold_ms`),
        which is more reliable than `input tap` because Android UIs sometimes
        silently drop sub-100ms taps during screen transitions. A 200ms hold
        is well within "tap" gesture range (Android long-press threshold is
        500ms) and gives Wild Rift's animation-settling logic time to accept
        the input. Set hold_ms=0 to use the original `input tap`.
        """
        if hold_ms > 0:
            self._run([
                "shell", "input", "swipe",
                str(x), str(y), str(x), str(y), str(hold_ms),
            ])
        else:
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
