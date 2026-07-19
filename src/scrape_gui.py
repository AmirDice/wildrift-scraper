"""Floating always-on-top GUI for the fully automated scraper.

Small Tkinter window that sits over MuMu. Click "Start Automation" and the bot 
will run continuously, tracking ranks via quick rank-badge OCR, executing macro-swipes 
automatically to scroll the page, and recovering gracefully if Wild Rift snaps back 
to the top.
"""
from __future__ import annotations

import argparse
import queue
import re
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import ttk
from typing import Any

import cv2

from .adb_client import ADBClient, ADBError
from .champions import CHAMPIONS
from .config import (
    ROWS_PER_PAGE,
    SCREEN_2_BADGE_X_RANGE,
    SCREEN_2_NAME_HEIGHT,
    SCREEN_2_NAME_X_RANGE,
    SCREEN_2_NAME_Y_OFFSET,
    SCREEN_2_SAFE_Y_BOTTOM,
    SCREEN_2_SAFE_Y_TOP,
    load_screen_points,
)
from .ocr import read_player_name, read_text
from .storage import CSVWriter, LeaderboardRow
from .strip import find_target_in_strip


class PauseRequested(Exception):
    """Raised mid-profile when the GUI's Pause button is clicked, so the
    worker can abort the current tap chain and retry the same rank on resume."""
    pass


def auto_scroll_down(client: ADBClient, target_x: int, expected_rank: int) -> None:
    """Calculates and executes momentum swipes to bring the list down to the expected rank."""
    pages_to_swipe = (expected_rank - 1) // ROWS_PER_PAGE
    print(f"\n[Auto-Scroll] Advancing down to rank block matching Rank {expected_rank} ({pages_to_swipe} swipes)...")
    
    for _ in range(pages_to_swipe):
        client.swipe(
            x1=target_x, 
            y1=SCREEN_2_SAFE_Y_BOTTOM - 40, 
            x2=target_x, 
            y2=SCREEN_2_SAFE_Y_TOP + 40, 
            duration_ms=200
        )
        time.sleep(0.18)
    time.sleep(0.7)


# ---- Worker side ---------------------------------------------------------

class Scraper:
    """The automated scraping state machine. Runs in a worker thread.

    Communicates with the GUI via two queues:
        - cmd_q: GUI -> worker  (strings: 'start', 'stop')
        - status_q: worker -> GUI  (dicts with telemetry data)
    """

    def __init__(
        self,
        args: argparse.Namespace,
        cmd_q: queue.Queue[str],
        status_q: queue.Queue[dict[str, Any]],
    ) -> None:
        self.args = args
        self.cmd_q = cmd_q
        self.status_q = status_q

        self.client = ADBClient(device=args.device)
        self.writer = CSVWriter(args.output)

        self.current_rank = args.start_rank
        self.end_rank = args.start_rank + args.n - 1
        self.successes = 0
        self.running = False

    def run(self) -> None:
        if not self.args.no_connect:
            try:
                self.client.connect()
            except ADBError as e:
                self.status_q.put({"event": "error", "msg": f"ADB connect failed: {e}"})
                return

        try:
            s2_pts = load_screen_points(2)
            s3_pts = load_screen_points(3)
            s4_pts = load_screen_points(4)
            s5_pts = load_screen_points(5)

            # New key scheme (phone remap): player_row_1..5, profile,
            # champion_lane, recent, back.
            target_x, start_y = s2_pts["player_row_1"]
            # Prefer explicit per-row ys when all 5 are mapped (rank spacing
            # isn't uniform — rank 1->2 has extra header padding).
            row_ys: list[int] = []
            for i in range(1, 6):
                k = f"player_row_{i}"
                if k not in s2_pts:
                    break
                row_ys.append(s2_pts[k][1])
            if len(row_ys) >= 2:
                pitch_y = (row_ys[-1] - row_ys[0]) / (len(row_ys) - 1)
            else:
                pitch_y = 0.0

            s3_view = s3_pts["profile"]
            s4_lane = s4_pts["champion_lane"]
            s5_recent = s5_pts["recent"]
            s5_back = s5_pts["back"]
        except Exception:
            self.status_q.put({"event": "error", "msg": "Failed to load point calibrations from JSON files."})
            return

        self.status_q.put({"event": "status", "text": "Ready. Click 'Start Automation'"})

        while True:
            # Block until we get a command to kick off processing
            cmd = self.cmd_q.get()
            if cmd == "stop_script":
                break
            if cmd != "start":
                continue

            self.running = True
            self.status_q.put({"event": "running_state", "val": True})
            
            print(f"Starting auto-scrape loop for {self.args.target}, ranks {self.current_rank} to {self.end_rank}")

            try:
                # Continuous scraping loop running entirely on its own parameters
                while self.running and self.current_rank <= self.end_rank:
                    
                    # Handle internal pause/stop requests queued by user interactions
                    while not self.cmd_q.empty():
                        c = self.cmd_q.get_nowait()
                        if c == "stop":
                            self.running = False
                        if c == "stop_script":
                            return

                    if not self.running:
                        break

                    # Work inside the current 5-row viewport layout. Prefer
                    # the explicit per-row y when all rows are mapped (more
                    # accurate than uniform pitch).
                    idx = (self.current_rank - 1) % ROWS_PER_PAGE
                    if row_ys and idx < len(row_ys):
                        row_y = row_ys[idx]
                    else:
                        row_y = int(round(start_y + idx * pitch_y))

                    # --- 1. STATE VERIFICATION AND AUTO-SCROLL GUARDRAIL ---
                    # Validate before EVERY tap: OCR current slot's rank badge
                    # and verify it matches self.current_rank. If slot 0 OCR
                    # is empty AND we expect rank >= 6, that's likely rank 1's
                    # gold-trophy badge (which doesn't OCR) — verify via slot 1
                    # (whose plain badge OCRs reliably).
                    try:
                        img_check = self.client.screenshot()

                        def _ocr_rank_at(yc: int) -> int | None:
                            crop = img_check[
                                int(yc - 22):int(yc + 22),
                                SCREEN_2_BADGE_X_RANGE[0]:SCREEN_2_BADGE_X_RANGE[1],
                            ]
                            text = read_text(crop).text
                            digits = re.sub(r"\D", "", text)
                            if not digits:
                                return None
                            try:
                                v = int(digits)
                            except ValueError:
                                return None
                            if 1 <= v <= 250:  # sanity bounds
                                return v
                            return None

                        detected = _ocr_rank_at(row_y)
                        needs_recovery = False

                        if detected is not None:
                            if detected != self.current_rank:
                                needs_recovery = True
                        elif self.current_rank >= 6 and idx == 0:
                            slot_1_y = start_y + pitch_y
                            det_s1 = _ocr_rank_at(slot_1_y)
                            if det_s1 is not None and det_s1 < self.current_rank:
                                needs_recovery = True

                        if needs_recovery:
                            auto_scroll_down(self.client, target_x, self.current_rank)
                            continue
                    except Exception:
                        pass  # Blurry frame / missing text: push forward safely

                    # --- 2. EXECUTE THE METRIC PROFILE EXTRACTION ---
                    self.status_q.put({
                        "event": "progress",
                        "text": f"Scraping Rank {self.current_rank}...",
                        "rank": self.current_rank,
                        "successes": self.successes
                    })

                    winrate, score, games = None, None, None
                    player_name: str | None = None
                    attempt = 0

                    def _check_pause_or_raise() -> None:
                        """Drain non-stop commands from the queue; if 'pause'
                        is queued, raise PauseRequested to abort cleanly.
                        Re-queue 'stop'/'stop_script' so the outer loop handles them."""
                        keep: list[str] = []
                        paused = False
                        while not self.cmd_q.empty():
                            try:
                                c = self.cmd_q.get_nowait()
                            except queue.Empty:
                                break
                            if c == "pause":
                                paused = True
                            else:
                                keep.append(c)
                        for c in keep:
                            self.cmd_q.put(c)
                        if paused:
                            raise PauseRequested()

                    # Loop wraps the retry block so a mid-profile Pause click
                    # redoes the whole rank from scratch instead of advancing.
                    profile_complete = False
                    while not profile_complete:
                        attempt = 0
                        paused_mid_profile = False
                        while attempt < self.args.max_retries_per_player:
                            attempt += 1
                            try:
                                # OCR the player name from the leaderboard
                                # row BEFORE we tap in. Cheaper than reading
                                # from the profile, and we keep the name even
                                # if the downstream tap chain fails.
                                try:
                                    pre_img = self.client.screenshot()
                                    name_x0, name_x1 = SCREEN_2_NAME_X_RANGE
                                    name_region = (
                                        name_x0,
                                        max(0, int(row_y) + SCREEN_2_NAME_Y_OFFSET),
                                        name_x1 - name_x0,
                                        SCREEN_2_NAME_HEIGHT,
                                    )
                                    player_name = read_player_name(pre_img, name_region)
                                except Exception:
                                    pass  # leave player_name as whatever it was

                                # Single tap per transition (phone UI is fast
                                # enough that taps don't get dropped). Pause is
                                # polled between steps so a mid-profile click
                                # aborts within ~step_wait seconds.
                                self.client.tap(target_x, row_y, hold_ms=self.args.tap_hold_ms)
                                time.sleep(self.args.step_wait)
                                _check_pause_or_raise()

                                self.client.tap(*s3_view, hold_ms=self.args.tap_hold_ms)
                                time.sleep(self.args.step_wait)
                                _check_pause_or_raise()

                                self.client.tap(*s4_lane, hold_ms=self.args.tap_hold_ms)
                                time.sleep(self.args.step_wait)
                                _check_pause_or_raise()

                                # Tap RECENT to switch sort/filter before the
                                # strip OCR.
                                self.client.tap(*s5_recent, hold_ms=self.args.tap_hold_ms)
                                time.sleep(self.args.step_wait)
                                _check_pause_or_raise()

                                wr, sc, gm, _, _, last_img = find_target_in_strip(
                                    self.client,
                                    self.args.target,
                                    max_swipes=self.args.max_strip_swipes,
                                    swipe_scale=self.args.strip_swipe_scale,
                                    swipe_duration_ms=self.args.strip_swipe_duration_ms,
                                    wait_after_swipe=self.args.step_wait,
                                )
                                _check_pause_or_raise()

                                if wr is not None:
                                    winrate, score, games = wr, sc, gm

                                if self.args.save_screenshots:
                                    out_p = Path(f"data/screenshots/{self.args.target.lower()}_{self.current_rank}.png")
                                    out_p.parent.mkdir(parents=True, exist_ok=True)
                                    cv2.imwrite(str(out_p), last_img)

                                self.client.tap(*s5_back, hold_ms=self.args.tap_hold_ms)
                                time.sleep(self.args.step_wait)
                                break

                            except PauseRequested:
                                paused_mid_profile = True
                                break

                            except Exception:
                                traceback.print_exc()
                                for _ in range(4):
                                    self.client.back()
                                    time.sleep(0.2)

                        if not paused_mid_profile:
                            profile_complete = True
                            break

                        # Mid-profile pause: tell GUI we paused, wait for resume,
                        # then redo this rank from scratch.
                        self.status_q.put({
                            "event": "paused_mid_profile",
                            "rank": self.current_rank,
                        })
                        while True:
                            c = self.cmd_q.get()  # blocks
                            if c == "stop_script":
                                return
                            if c == "stop":
                                self.running = False
                                break
                            if c in ("resume", "start"):
                                break
                        if not self.running:
                            break
                        self.status_q.put({"event": "resumed", "rank": self.current_rank})
                        # Loop continues and retries the same rank

                    self.writer.write(LeaderboardRow(
                        champion=self.args.target,
                        rank=self.current_rank,
                        player_name=player_name or "",
                        score=score,
                        games=games,
                        winrate=winrate,
                    ))

                    if winrate is not None:
                        self.successes += 1

                    self.current_rank += 1

                # Loop termination conditions reached gracefully
                if self.current_rank > self.end_rank:
                    self.status_str = "Completed Processing Dataset!"
                else:
                    self.status_str = "Automation Interrupted."
                
                self.running = False
                self.status_q.put({"event": "running_state", "val": False})
                self.status_q.put({"event": "status", "text": f"Finished. Clean entries: {self.successes}"})

            except Exception as loop_err:
                self.running = False
                self.status_q.put({"event": "running_state", "val": False})
                self.status_q.put({"event": "error", "msg": f"Fatal Crash: {loop_err}"})


# ---- UI Side -------------------------------------------------------------

def build_gui(cmd_q: queue.Queue[str], status_q: queue.Queue[dict[str, Any]]) -> None:
    root = tk.Tk()
    root.title("WR Auto-Scraper Engine")
    root.attributes("-topmost", True)
    root.geometry("340x240")
    root.resizable(False, False)

    style = ttk.Style()
    style.theme_use("clam")

    main_frame = ttk.Frame(root, padding="12")
    main_frame.pack(fill=tk.BOTH, expand=True)

    status_lbl = ttk.Label(main_frame, text="Initializing...", font=("Segoe UI", 10, "bold"), wraplength=300, anchor="center")
    status_lbl.pack(pady=8, fill=tk.X)

    progress_lbl = ttk.Label(main_frame, text="Progress: Ready", font=("Segoe UI", 9))
    progress_lbl.pack(pady=4)

    btn_action = ttk.Button(main_frame, text="Start Automation")
    btn_action.pack(pady=(8, 4), fill=tk.X, ipady=6)

    btn_pause = ttk.Button(main_frame, text="Pause (redo current profile)")
    btn_pause.pack(pady=4, fill=tk.X)
    btn_pause.state(["disabled"])

    is_running = False
    is_paused_mid_profile = False

    def on_action_click():
        if not is_running:
            cmd_q.put("start")
        else:
            cmd_q.put("stop")

    def on_pause_click():
        if is_paused_mid_profile:
            # Currently paused — clicking acts as resume
            cmd_q.put("resume")
        else:
            cmd_q.put("pause")
            # Optimistic UI hint; worker confirms via paused_mid_profile event
            status_lbl.config(
                text="Pause requested — aborting current profile, will redo on resume.",
                foreground="orange",
            )

    btn_action.config(command=on_action_click)
    btn_pause.config(command=on_pause_click)

    def poll():
        nonlocal is_running, is_paused_mid_profile
        while not status_q.empty():
            try:
                msg = status_q.get_nowait()
                event = msg.get("event")
                if event == "status":
                    status_lbl.config(text=msg["text"], foreground="black")
                elif event == "error":
                    status_lbl.config(text=msg["msg"], foreground="red")
                elif event == "progress":
                    status_lbl.config(text=msg["text"], foreground="blue")
                    progress_lbl.config(text=f"Rank Thresholds: {msg['rank']} | Parsed: {msg['successes']}")
                elif event == "paused_mid_profile":
                    is_paused_mid_profile = True
                    status_lbl.config(
                        text=f"PAUSED on rank {msg['rank']}. Fix Wild Rift then click 'Resume'.",
                        foreground="orange",
                    )
                    btn_pause.config(text="Resume (re-do this profile)")
                elif event == "resumed":
                    is_paused_mid_profile = False
                    status_lbl.config(text=f"Resumed — re-doing rank {msg['rank']}", foreground="blue")
                    btn_pause.config(text="Pause (redo current profile)")
                elif event == "running_state":
                    is_running = msg["val"]
                    if is_running:
                        btn_action.config(text="Stop Engine")
                        btn_pause.state(["!disabled"])
                    else:
                        btn_action.config(text="Start Automation")
                        btn_pause.state(["disabled"])
                        is_paused_mid_profile = False
                        btn_pause.config(text="Pause (redo current profile)")
            except queue.Empty:
                break
        root.after(100, poll)

    root.protocol("WM_DELETE_WINDOW", lambda: (cmd_q.put("stop_script"), root.destroy()))
    root.after(100, poll)
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--start-rank", type=int, default=1)
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=0.8,
                        help="Wait after each tap. Lower if your device's UI transitions are fast.")
    parser.add_argument("--tap-hold-ms", type=int, default=60,
                        help="How long each tap is held (ms). 60 is fast and reliable on phone; raise if taps get dropped.")
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"))
    parser.add_argument("--save-screenshots", action="store_true")
    parser.add_argument("--max-strip-swipes", type=int, default=3)
    parser.add_argument("--strip-swipe-scale", type=float, default=0.7)
    parser.add_argument("--strip-swipe-duration-ms", type=int, default=400)
    parser.add_argument("--max-retries-per-player", type=int, default=3)
    args = parser.parse_args()

    cmd_q: queue.Queue[str] = queue.Queue()
    status_q: queue.Queue[dict[str, Any]] = queue.Queue()

    scraper = Scraper(args, cmd_q, status_q)
    worker_thread = threading.Thread(target=scraper.run, daemon=True)
    worker_thread.start()

    build_gui(cmd_q, status_q)
    return 0


if __name__ == "__main__":
    sys.exit(main())