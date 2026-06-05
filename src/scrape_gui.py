"""Floating always-on-top GUI for the manual-scroll scraper.

Small Tkinter window that sits over MuMu. One big button to scrape the
next batch of 5, plus pause/stop and a status panel. The scraper runs
in a background thread so the UI stays responsive.

Run:
    python -m src.scrape_gui --target Aatrox --start-rank 1 --n 200

Workflow:
    1. Open MuMu, scroll the leaderboard so rank --start-rank is at slot 0.
    2. Click "Scrape next 5".
    3. While the bot scrapes, scroll MuMu to the next batch in advance.
    4. When the bot finishes, click "Scrape next 5" again.
    5. Repeat until you hit --n or click Stop.

The GUI window stays on top of MuMu so you don't have to alt-tab.
"""
from __future__ import annotations

import argparse
import queue
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
from .config import ROWS_PER_PAGE, load_screen_points
from .storage import CSVWriter, LeaderboardRow
from .strip import find_target_in_strip


# ---- Worker side ---------------------------------------------------------

class Scraper:
    """The actual scraping state machine. Runs in a worker thread.

    Communicates with the GUI via two queues:
        - cmd_q: GUI -> worker  (strings: 'next', 'pause', 'resume', 'stop')
        - status_q: worker -> GUI  (dicts: {kind, ...})
    """

    def __init__(self, args, cmd_q: "queue.Queue[str]", status_q: "queue.Queue[dict[str, Any]]"):
        self.args = args
        self.cmd_q = cmd_q
        self.status_q = status_q
        self.target = args.target  # mutable — can be changed mid-session via 'target:NAME'
        self.current_rank = args.start_rank
        self.successes = 0
        self.stop = False
        self.paused = False

    def emit(self, **kwargs: Any) -> None:
        self.status_q.put(kwargs)

    def wait_for_cmd(self, timeout: float | None = None) -> str | None:
        try:
            return self.cmd_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain_cmds(self) -> list[str]:
        out: list[str] = []
        while True:
            try:
                out.append(self.cmd_q.get_nowait())
            except queue.Empty:
                break
        return out

    def check_for_pause(self) -> None:
        """If a 'pause' command was queued during scraping, block until resume."""
        for c in self.drain_cmds():
            if c == "pause":
                self.paused = True
            elif c == "resume":
                self.paused = False
            elif c == "stop":
                self.stop = True
                return
        if self.paused:
            self.emit(kind="paused")
            while not self.stop:
                c = self.wait_for_cmd(timeout=0.2)
                if c == "resume":
                    self.paused = False
                    self.emit(kind="resumed")
                    return
                if c == "stop":
                    self.stop = True
                    return

    def run(self) -> None:
        args = self.args
        try:
            s2 = load_screen_points(2)
            s3 = load_screen_points(3)
            s4 = load_screen_points(4)
            s5 = load_screen_points(5)
        except FileNotFoundError as e:
            self.emit(kind="error", msg=f"missing coord file: {e}")
            return

        rank_1_x, rank_1_y = s2["aatrox"]
        if "player_row_5" in s2:
            _, deep_y = s2["player_row_5"]
            row_pitch = (deep_y - rank_1_y) / 4
        elif "player_row_3" in s2:
            _, deep_y = s2["player_row_3"]
            row_pitch = (deep_y - rank_1_y) / 2
        else:
            _, deep_y = s2["player_row_2"]
            row_pitch = deep_y - rank_1_y

        view_profile_tap = s3["aatrox"]
        champ_and_lane_tap = s4["aatrox"]
        back_tap = s5["back"]

        def slot_xy(slot: int) -> tuple[int, int]:
            return (rank_1_x, int(round(rank_1_y + slot * row_pitch)))

        client = ADBClient(device=args.device)
        if not args.no_connect:
            try:
                client.connect()
            except ADBError as e:
                self.emit(kind="error", msg=str(e))
                return

        writer = CSVWriter(args.output)
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)

        def scrape_one(rank: int, slot: int) -> tuple[float | None, int | None, int | None]:
            px, py = slot_xy(slot)
            client.tap(px, py)
            time.sleep(args.step_wait)
            client.tap(*view_profile_tap)
            time.sleep(args.step_wait)
            client.tap(*champ_and_lane_tap)
            time.sleep(0.4)
            client.tap(*champ_and_lane_tap)
            time.sleep(args.step_wait)
            winrate, score, games, found, swipes_done, img = find_target_in_strip(
                client,
                self.target,
                max_swipes=args.max_strip_swipes,
                swipe_scale=args.strip_swipe_scale,
                swipe_duration_ms=args.strip_swipe_duration_ms,
            )
            if args.save_screenshots:
                cv2.imwrite(str(data_dir / f"run_rank_{rank:03d}.png"), img)
            client.tap(*back_tap)
            time.sleep(args.step_wait)
            return winrate, score, games

        def end_rank() -> int:
            return self.args.start_rank + self.args.n - 1

        self.emit(kind="ready", target=self.target, current_rank=self.current_rank, end_rank=end_rank())

        while not self.stop and self.current_rank <= end_rank():
            cmd = self.wait_for_cmd()
            if cmd is None or cmd == "stop":
                self.stop = True
                break
            if cmd == "pause":
                self.paused = True
                self.check_for_pause()
                continue
            if cmd == "resume":
                continue
            if cmd.startswith("target:"):
                new_target = cmd.split(":", 1)[1].strip()
                if new_target:
                    self.target = new_target
                    self.current_rank = self.args.start_rank
                    self.successes = 0
                    self.emit(
                        kind="target_changed",
                        target=self.target,
                        current_rank=self.current_rank,
                        end_rank=end_rank(),
                    )
                continue
            if cmd != "next":
                continue

            batch_start = self.current_rank
            self.emit(kind="batch_start", rank=batch_start, target=self.target)
            for slot in range(ROWS_PER_PAGE):
                if self.current_rank > end_rank() or self.stop:
                    break
                self.check_for_pause()
                if self.stop:
                    break
                self.emit(kind="scraping", rank=self.current_rank, slot=slot, target=self.target)
                winrate: float | None = None
                score: int | None = None
                games: int | None = None
                for attempt in range(1, args.max_retries_per_player + 1):
                    try:
                        winrate, score, games = scrape_one(self.current_rank, slot)
                    except Exception:
                        self.emit(kind="error", msg=traceback.format_exc(limit=2))
                        winrate, score, games = None, None, None
                    if winrate is not None:
                        break
                writer.write(LeaderboardRow(
                    champion=self.target,
                    rank=self.current_rank,
                    player_name="",
                    score=score,
                    games=games,
                    winrate=winrate,
                ))
                if winrate is not None:
                    self.successes += 1
                self.emit(
                    kind="scraped",
                    rank=self.current_rank,
                    winrate=winrate,
                    score=score,
                    games=games,
                    successes=self.successes,
                )
                self.current_rank += 1

            self.emit(kind="batch_done", current_rank=self.current_rank, end_rank=end_rank(), target=self.target)

        self.emit(kind="done", successes=self.successes, total=self.current_rank - args.start_rank)


# ---- GUI side ------------------------------------------------------------

def build_gui(args, cmd_q: "queue.Queue[str]", status_q: "queue.Queue[dict[str, Any]]") -> None:
    root = tk.Tk()
    root.title("WR Scraper")
    root.attributes("-topmost", True)
    root.geometry("300x340+50+50")
    root.minsize(280, 330)

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass

    target_var = tk.StringVar(value=f"Target: {args.target}")
    rank_var = tk.StringVar(value="Current rank: —")
    last_var = tk.StringVar(value="Last scrape: —")
    state_var = tk.StringVar(value="Connecting…")
    selector_var = tk.StringVar(value=args.target)

    ttk.Label(root, textvariable=target_var, anchor="center", font=("TkDefaultFont", 10, "bold")).pack(fill="x", padx=8, pady=(8, 0))
    ttk.Label(root, textvariable=rank_var, anchor="center").pack(fill="x", padx=8)
    ttk.Label(root, textvariable=last_var, anchor="center", foreground="#1a6b1a").pack(fill="x", padx=8, pady=(0, 4))

    # Champion picker + Switch button
    picker_frame = ttk.Frame(root)
    picker_frame.pack(fill="x", padx=8, pady=(4, 2))
    ttk.Label(picker_frame, text="Next champion:").pack(side="left")
    picker = ttk.Combobox(
        picker_frame, textvariable=selector_var, values=sorted(CHAMPIONS), width=14, state="readonly",
    )
    picker.pack(side="right", fill="x", expand=True)

    def switch_target() -> None:
        new = selector_var.get().strip()
        if not new:
            return
        cmd_q.put(f"target:{new}")

    btn_switch = ttk.Button(root, text="Switch target", command=switch_target)
    btn_switch.pack(fill="x", padx=8, pady=(0, 6))

    btn_next = ttk.Button(root, text="Scrape next 5", command=lambda: cmd_q.put("next"))
    btn_next.pack(fill="x", padx=8, pady=(4, 2))
    btn_next.state(["disabled"])

    btn_pause = ttk.Button(root, text="Pause", command=lambda: cmd_q.put("pause"))
    btn_pause.pack(fill="x", padx=8, pady=2)
    btn_pause.state(["disabled"])

    btn_resume = ttk.Button(root, text="Resume", command=lambda: cmd_q.put("resume"))
    btn_resume.pack(fill="x", padx=8, pady=2)
    btn_resume.state(["disabled"])

    btn_stop = ttk.Button(root, text="Stop", command=lambda: (cmd_q.put("stop"), root.after(500, root.destroy)))
    btn_stop.pack(fill="x", padx=8, pady=(2, 4))

    ttk.Label(root, textvariable=state_var, anchor="center", foreground="#444", wraplength=280, justify="center").pack(fill="x", padx=8, pady=(4, 8))

    def poll() -> None:
        try:
            while True:
                msg = status_q.get_nowait()
                kind = msg.get("kind")
                if kind == "ready":
                    state_var.set("Ready. Scroll to the starting rank, then click 'Scrape next 5'.")
                    target_var.set(f"Target: {msg.get('target', args.target)}")
                    rank_var.set(f"Current rank: {msg['current_rank']} / {msg['end_rank']}")
                    btn_next.state(["!disabled"])
                    btn_pause.state(["disabled"])
                    btn_resume.state(["disabled"])
                elif kind == "target_changed":
                    target_var.set(f"Target: {msg['target']}")
                    rank_var.set(f"Current rank: {msg['current_rank']} / {msg['end_rank']}")
                    last_var.set("Last scrape: —")
                    state_var.set(
                        f"Target switched to {msg['target']}. Navigate Wild Rift to that champion's "
                        "leaderboard and scroll to the starting rank, then click 'Scrape next 5'."
                    )
                    btn_next.state(["!disabled"])
                    btn_pause.state(["disabled"])
                    btn_resume.state(["disabled"])
                elif kind == "batch_start":
                    state_var.set(f"Scraping batch starting at rank {msg['rank']} …")
                    btn_next.state(["disabled"])
                    btn_pause.state(["!disabled"])
                    btn_resume.state(["disabled"])
                elif kind == "scraping":
                    state_var.set(f"Tapping rank {msg['rank']} (slot {msg['slot']}) …")
                elif kind == "scraped":
                    wr = msg.get("winrate")
                    score = msg.get("score")
                    games = msg.get("games")
                    last_var.set(
                        f"Rank {msg['rank']}: "
                        + (f"{wr}% / score {score} / games {games}" if wr is not None else "FAILED (None)")
                    )
                elif kind == "batch_done":
                    state_var.set(
                        f"Batch done. {msg['current_rank'] - 1} / {msg['end_rank']} scraped. "
                        "Scroll to next batch then click 'Scrape next 5'."
                    )
                    rank_var.set(f"Current rank: {msg['current_rank']} / {msg['end_rank']}")
                    btn_next.state(["!disabled"])
                    btn_pause.state(["disabled"])
                elif kind == "paused":
                    state_var.set("PAUSED. Fix Wild Rift, then click Resume.")
                    btn_pause.state(["disabled"])
                    btn_resume.state(["!disabled"])
                elif kind == "resumed":
                    state_var.set("Resumed.")
                    btn_resume.state(["disabled"])
                    btn_pause.state(["!disabled"])
                elif kind == "done":
                    state_var.set(f"DONE. {msg['successes']} / {msg['total']} winrates parsed.")
                    btn_next.state(["disabled"])
                    btn_pause.state(["disabled"])
                    btn_resume.state(["disabled"])
                elif kind == "error":
                    state_var.set(f"ERROR: {msg['msg']}")
        except queue.Empty:
            pass
        root.after(100, poll)

    root.after(100, poll)
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--start-rank", type=int, default=1)
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"))
    parser.add_argument("--save-screenshots", action="store_true")
    parser.add_argument("--max-strip-swipes", type=int, default=3)
    parser.add_argument("--strip-swipe-scale", type=float, default=0.7)
    parser.add_argument("--strip-swipe-duration-ms", type=int, default=800)
    parser.add_argument("--max-retries-per-player", type=int, default=3)
    args = parser.parse_args()

    cmd_q: "queue.Queue[str]" = queue.Queue()
    status_q: "queue.Queue[dict[str, Any]]" = queue.Queue()

    scraper = Scraper(args, cmd_q, status_q)
    worker = threading.Thread(target=scraper.run, daemon=True)
    worker.start()

    build_gui(args, cmd_q, status_q)
    # When the user closes the window, signal the worker to stop.
    cmd_q.put("stop")
    worker.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
