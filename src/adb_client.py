"""Thin wrapper around the `adb` CLI for screenshots and input events."""
from __future__ import annotations

import subprocess
import time
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
        """Grab a screenshot and return it as a BGR numpy array.

        Uses RAW screencap (RGBA + 12/16-byte header) -- measured ~25% faster
        than PNG on this device (1.19s vs 1.56s: the device-side PNG encode
        costs more than the extra USB bytes). Falls back to PNG once if the
        raw format ever surprises us, and remembers the working mode.
        """
        if not getattr(self, "_png_only", False):
            proc = subprocess.run(
                ["adb", "-s", self.device, "exec-out", "screencap"],
                capture_output=True, check=False,
            )
            raw = proc.stdout
            if proc.returncode == 0 and len(raw) > 16:
                w = int.from_bytes(raw[0:4], "little")
                h = int.from_bytes(raw[4:8], "little")
                for hdr in (12, 16):
                    if 0 < w * h and len(raw) - hdr == w * h * 4:
                        rgba = np.frombuffer(raw[hdr:], dtype=np.uint8).reshape(h, w, 4)
                        return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
            self._png_only = True  # unexpected format: stick to PNG from now on
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

    # ---- persistent shell: one adb process for ALL input events ----------
    # Every subprocess-spawned `adb shell input ...` pays ~100-150ms process
    # startup before the event even reaches the device. A single long-lived
    # `adb shell` with commands written to its stdin removes that per-tap tax
    # (~0.7s per scraped profile). Commands execute serially in-order, which
    # is exactly the semantics the tap chains rely on.

    def _shell(self):
        proc = getattr(self, "_shell_proc", None)
        if proc is not None and proc.poll() is None:
            return proc
        proc = subprocess.Popen(
            ["adb", "-s", self.device, "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._shell_proc = proc
        return proc

    def _input(self, cmd: str) -> None:
        """Send one `input ...` line through the persistent shell; fall back
        to a one-shot subprocess if the shell pipe ever breaks."""
        try:
            proc = self._shell()
            proc.stdin.write((cmd + "\n").encode())
            proc.stdin.flush()
        except Exception:  # noqa: BLE001 -- dead pipe: respawn once, then one-shot
            self._shell_proc = None
            try:
                proc = self._shell()
                proc.stdin.write((cmd + "\n").encode())
                proc.stdin.flush()
            except Exception:  # noqa: BLE001
                self._run(["shell"] + cmd.split())

    def tap(self, x: int, y: int, hold_ms: int = 200) -> None:
        """Tap at (x, y), held for `hold_ms` milliseconds.

        Implemented as a zero-distance swipe (`input swipe x y x y hold_ms`),
        which is more reliable than `input tap` because Android UIs sometimes
        silently drop sub-100ms taps during screen transitions. Set hold_ms=0
        to use the original `input tap`.
        """
        if hold_ms > 0:
            self._input(f"input swipe {x} {y} {x} {y} {hold_ms}")
            # the persistent shell is fire-and-forget; keep the old BLOCKING
            # semantics callers' sleep timings were built on
            time.sleep(hold_ms / 1000 + 0.03)
        else:
            self._input(f"input tap {x} {y}")
            time.sleep(0.05)

    def back(self) -> None:
        """Press the Android system back key (KEYCODE_BACK)."""
        self._input("input keyevent 4")
        time.sleep(0.05)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._input(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
        time.sleep(duration_ms / 1000 + 0.05)  # blocking semantics, as before

    def _run(self, args: list[str], use_device: bool = True) -> str:
        cmd = ["adb"]
        if use_device:
            cmd += ["-s", self.device]
        cmd += args
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ADBError(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
        return proc.stdout
