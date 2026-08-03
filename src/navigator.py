"""Leaderboard travel logic, extracted from scrape_timed so it can be tested
OFFLINE by simulating journeys against a virtual leaderboard -- including
replays of the exact failure frames captured in live runs. Every dependency
that touches the device (screenshot, drag, fling, scan, arbitration) is
injected, so the decision policy itself is pure and provable.

Policy summary (each rule earned by a real failure):
  - scans steer, ACTIONS are ground truth (the rows-moved ledger bounds travel)
  - a single-badge scan is never evidence (screen always shows 4+ rows)
  - journeys start seeded with the last verified position, so even the first
    scan is plausibility-checked
  - flings only for long hauls; overshoot flips lock travel to exact drags
  - a missing badge is not a missing row: neighbors + pitch give its position
"""
from __future__ import annotations

import time
from typing import Callable

import numpy as np

Scan = Callable[[np.ndarray, float | None], tuple[dict[int, int], float | None]]


class LeaderboardNavigator:
    def __init__(
        self,
        *,
        screenshot: Callable[[], np.ndarray],
        screenshot_fast: Callable[[], np.ndarray] | None = None,
        scan: Scan,
        drag_rows: Callable[[float, float], None],
        fling: Callable[[bool], None],
        arbitrate: Callable[[np.ndarray], dict[int, int]] | None = None,
        on_fling_calibrated: Callable[[float], None] | None = None,
        dump_frame: Callable[[np.ndarray, int], str | None] | None = None,
        fling_rows: float = 10.0,
        log: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
        max_cycles: int = 14,
    ) -> None:
        self.screenshot = screenshot
        self.screenshot_fast = screenshot_fast
        self.scan = scan
        self.drag_rows = drag_rows
        self.fling = fling
        self.arbitrate = arbitrate
        self.on_fling_calibrated = on_fling_calibrated
        self.dump_frame = dump_frame
        self.fling_rows = fling_rows
        self.log = log
        self.sleep = sleep
        self.max_cycles = max_cycles
        # learned state, persists across journeys
        self.last_pitch: float | None = None
        self.last_center: float | None = None
        self.screen_h: int | None = None
        self.last_frame: np.ndarray | None = None  # frame behind the last returned y
        self._debug_dumps = 0  # rejected-frame dumps this run (capped)

    def _dump_rejected(self, img: np.ndarray, rank: int) -> None:
        """Save a frame the policy refused to act on, so 'why did the scan
        fail' is answered from pixels instead of hypotheses."""
        if self.dump_frame is None or self._debug_dumps >= 8:
            return
        self._debug_dumps += 1
        path = self.dump_frame(img, rank)
        if path:
            self.log(f"  [debug] rejected frame saved -> {path}")

    def ensure_visible(self, rank: int) -> int | None:
        """Return the on-screen y of `rank`, travelling to it if needed.
        None = detection lost; the caller falls back to a manual prompt."""
        empty_scans = 0
        prev_sign = 0
        no_fling = False
        down_locked = False
        careful_used = False
        # Seed the sanity gate with where we last verifiably were, so even a
        # journey's FIRST scan is plausibility-checked. (A bad frame once read
        # a single badge, "10" as "1", and an unseeded journey believed it had
        # teleported to the top of the list.)
        expected: float | None = self.last_center
        net_down = 0.0                 # rows moved down this journey (from actions)
        down_budget: float | None = None
        img: np.ndarray | None = None
        pending: float | None = None   # center of a rejected (unconfirmed) scan
        rejects = 0
        # (pre-burst hi_r, n, sign, est): fling calibration measured on the
        # NEXT accepted scan, so bursts need no extra screenshot of their own.
        pending_fling: tuple[int, int, int, float] | None = None
        # Screenshots dominate profile cost (~1.2s each on this device), so
        # the happy path uses ONE fast frame; any rejection this journey
        # escalates to the stability-paired grabber for the remaining cycles.
        use_stable = self.screenshot_fast is None

        for _cycle in range(self.max_cycles):
            img = self.screenshot() if use_stable else self.screenshot_fast()
            if self.screen_h is None:
                self.screen_h = int(img.shape[0])
            H = self.screen_h
            ranks, pitch = self.scan(img, expected)
            if pitch:
                self.last_pitch = pitch
            if len(ranks) < 3 or pitch is None:
                # The screen always shows 4+ rows, so a scan with fewer than
                # THREE badges is a degraded frame: a misread overlay, or --
                # after a refresh -- rows still populating (skeleton rows have
                # no badge yet and pass the stability gate). Wait for the list
                # to finish loading instead of navigating on a partial read.
                empty_scans += 1
                if empty_scans >= 4:
                    self.last_center = None
                    return None
                use_stable = True
                if ranks:
                    self.log(f"  [scan] only {len(ranks)} badge(s) read -- "
                             f"rows may still be loading, waiting")
                self._dump_rejected(img, rank)
                self.sleep(0.5)
                continue
            empty_scans = 0
            # Once the ledger has proven the fast scan wrong, arbitrate every
            # subsequent frame with the careful reader.
            if down_locked and self.arbitrate is not None:
                careful = self.arbitrate(img)
                if careful:
                    ranks = careful
            lo_r, hi_r = min(ranks), max(ranks)
            center = (lo_r + hi_r) / 2
            # A scan far off the predicted position is more likely a misread
            # (or mid-inertia frame) than a real teleport. Legitimate movement
            # between accepted scans is at most ~4 rows (the max drag), so a
            # bigger jump is only accepted once a SECOND read confirms it --
            # real resets confirm; one-frame misreads do not.
            anomaly_confirmed = False
            if expected is not None and not down_locked and rejects < 2:
                gap = abs(center - expected)
                confirmed = pending is not None and abs(center - pending) <= 3
                # A well-chained TOP window is accepted instantly: resets
                # always land there, they happen every few profiles, and the
                # 1.5s confirmation tax was pure overhead once the badge
                # column stopped lying (the clipping fix). The action ledger
                # still bounds the pathological case.
                is_top_window = lo_r <= 2 and len(ranks) >= 4
                if gap > 5 and not confirmed and not is_top_window:
                    use_stable = True
                    rejects += 1
                    pending = center
                    self.log(f"  [detect] scan says ranks {lo_r}-{hi_r}, expected ~{expected:.0f}"
                             f" -- rescanning to confirm")
                    self._dump_rejected(img, rank)
                    self.sleep(0.3)
                    continue
                anomaly_confirmed = confirmed and gap > 5
            pending = None
            rejects = 0
            # A DETERMINISTIC misread confirms itself (same wrong pixels, same
            # wrong read, twice). Before acting on a confirmed teleport claim,
            # let the careful reader arbitrate -- it reads the badges through
            # an entirely different pipeline.
            if anomaly_confirmed and self.arbitrate is not None:
                careful = self.arbitrate(img)
                if careful:
                    c_center = (min(careful) + max(careful)) / 2
                    if abs(c_center - center) > 5:
                        self.log(f"  [detect] arbitration overrules confirmed scan: screen shows "
                                 f"ranks {min(careful)}-{max(careful)} (scan claimed {lo_r}-{hi_r})")
                        ranks = careful
                        lo_r, hi_r = min(ranks), max(ranks)
                        center = (lo_r + hi_r) / 2
            if pending_fling is not None:
                b_hi, n_f, s_f, est = pending_fling
                pending_fling = None
                moved = abs(hi_r - b_hi) / n_f
                if moved >= 2:
                    self.fling_rows = 0.7 * self.fling_rows + 0.3 * moved
                    if self.on_fling_calibrated is not None:
                        self.on_fling_calibrated(self.fling_rows)
                    # Correct the ledger with the measured movement.
                    net_down += (moved * n_f * s_f) - est
            if down_budget is None:
                # Journey start: how far down could the target possibly be?
                down_budget = max(0.0, rank - hi_r) + 6.0
            p = self.last_pitch or (H * 0.135)
            self.log(f"  [scan] reads ranks {lo_r}-{hi_r}"
                     + (f" -- {rank} MISSING from OCR"
                        if lo_r < rank < hi_r and rank not in ranks else ""))
            if rank in ranks:
                y = ranks[rank]
                # Only tap rows fully inside the safe zone; a row hugging the
                # screen edge may be partially clipped.
                if H * 0.13 <= y <= H * 0.87:
                    self.last_center = center
                    self.last_frame = img
                    return y
                nudge = 0.8 if y > H * 0.87 else -0.8
                self.drag_rows(nudge, p)
                net_down += nudge
                expected = center + nudge
                continue
            # GRID INFERENCE: badges can fail to OCR (trophy styling on ranks
            # 1-2, highlight state, edge compression) while their ROWS are
            # plainly on screen. Rows sit on a fixed grid, so any read rank
            # within a few rows gives the target's y as pure geometry -- but
            # ONLY where a row provably exists: between read badges, or above
            # the topmost one (the list clamps at rank 1). BELOW the lowest
            # read badge the list may simply end (the pinned self-row owns
            # the bottom edge and rows compress there), so never guess
            # downward -- scroll one row and read it properly instead.
            if pitch and rank < hi_r:
                known = sorted(ranks, key=lambda r: abs(r - rank))
                nb = known[0]
                if abs(nb - rank) <= 4:
                    y_inf = int(round(ranks[nb] + (rank - nb) * pitch))
                    if H * 0.13 <= y_inf <= H * 0.87:
                        self.log(f"  [detect] rank {rank}'s badge did not OCR; "
                                 f"row inferred at y={y_inf} from rank {nb} + grid")
                        self.last_center = center
                        self.last_frame = img
                        return y_inf
            delta = rank - hi_r if rank > hi_r else rank - lo_r
            sign = 1 if delta > 0 else -1
            # ACTION LEDGER: refuse impossible downward travel. If we already
            # moved farther down than the target ever was, the target is
            # above us no matter what the scan claims.
            if sign > 0 and net_down >= down_budget:
                if not down_locked:
                    down_locked = True
                    no_fling = True
                    self.log(f"  [detect] moved ~{net_down:.0f} rows down but the target was only "
                             f"~{down_budget - 6:.0f} away -- it CANNOT be below us. "
                             f"Locking downward travel, walking back up.")
                    if not careful_used and self.arbitrate is not None:
                        careful_used = True
                        careful = self.arbitrate(img)
                        if rank in careful:
                            y = careful[rank]
                            if H * 0.13 <= y <= H * 0.87:
                                self.last_center = (min(careful) + max(careful)) / 2
                                self.last_frame = img
                                return y
                        if careful:
                            ranks = careful
                            lo_r, hi_r = min(ranks), max(ranks)
                sign = -1
                delta = -3
            if prev_sign and sign != prev_sign and not no_fling:
                no_fling = True
                self.log("  [detect] overshoot detected -- switching to exact drags")
            prev_sign = sign
            if no_fling or abs(delta) <= 12:
                # Slow drags are inertia-free and therefore exact: walk to the
                # target in bounded steps. When far, chain a second drag blind
                # -- exactness means no scan is needed between them.
                step = float(max(-4, min(4, delta)))
                self.drag_rows(step, p)
                net_down += step
                remaining = delta - step
                if abs(remaining) >= 4:
                    step2 = float(max(-4, min(4, remaining)))
                    self.drag_rows(step2, p)
                    net_down += step2
                    step += step2
                expected = center + step
                continue
            # Long haul: BLIND fling burst sized to land just short of the
            # target. The next loop cycle corrects the remainder and (via
            # pending_fling) re-learns rows-per-fling -- no extra screenshot.
            n = max(1, min(4, int(abs(delta) - 2) // max(4, int(self.fling_rows))))
            for _ in range(n):
                self.fling(sign > 0)
            moved_est = sign * self.fling_rows * n
            net_down += moved_est
            expected = center + moved_est
            pending_fling = (hi_r, n, sign, moved_est)

        dump_path = None
        if self.dump_frame is not None and img is not None:
            dump_path = self.dump_frame(img, rank)
        self.log(f"  [detect] journey exhausted (net movement ~{net_down:+.0f} rows) -- handing over"
                 + (f"; last frame saved to {dump_path}" if dump_path else ""))
        self.last_center = None
        return None
