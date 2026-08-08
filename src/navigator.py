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
        off_leaderboard: Callable[[np.ndarray], str] | None = None,
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
        # Names the screen when it is clearly NOT a leaderboard (main menu,
        # quit dialog). Without it a run ejected to the main menu spends four
        # scan cycles plus sleeps -- a minute or more -- waiting for rows that
        # can never load, before recovery even starts.
        self.off_leaderboard = off_leaderboard
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
        None = detection lost; the caller falls back to a manual prompt.

        When None is returned WITH `self.bottom_rank` set, nothing is lost:
        the list bottomed out with the target below its last row, meaning the
        board simply has fewer entries than asked for. NA boards do this
        routinely (Xin Zhao's ends at 45), and treating it as detection loss
        sent a healthy overnight run into recovery against a screen that was
        never wrong."""
        self.bottom_rank: int | None = None
        # (hi_r, y of hi_r) from the last good scan that wanted to go DOWN;
        # two identical bottoms across a down-drag = the list cannot move.
        last_bottom: tuple[int, int] | None = None
        bottom_stalls = 0
        empty_scans = 0
        prev_sign = 0
        no_fling = False
        down_locked = False
        careful_used = False
        # A fling's inertia can keep the list gliding after a frame that
        # LOOKS static: rank 29's row read at y=765, the list slid one more
        # row before the taps landed, and the chain opened rank 30's profile.
        # While this flag is set, no tap or inference may come from a single
        # frame -- two consecutive reads must agree first. Drags clear it:
        # touching the list kills inertia, so drag releases are exact.
        settle_pending = False
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
        impossible_scans = 0   # confirmed downward teleports refused by physics
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
                # Before assuming "still loading", ask whether this is even a
                # leaderboard. Waiting out four cycles on the main menu is a
                # minute of guaranteed failure, and the caller's recovery is
                # the only thing that can fix it.
                if self.off_leaderboard is not None:
                    where = self.off_leaderboard(img)
                    if where:
                        self.log(f"  [detect] not on a leaderboard any more ({where})"
                                 f" -- handing over to recovery immediately")
                        self._dump_rejected(img, rank)
                        self.last_center = None
                        return None
                empty_scans += 1
                if empty_scans >= 4:
                    self.last_center = None
                    return None
                use_stable = True
                self._dump_rejected(img, rank)
                # The FIRST degraded read gets the benefit of the doubt: rows
                # really may still be populating. After that, stop waiting.
                # A degraded read is usually DETERMINISTIC, not transient --
                # three rejected frames from one live incident, taken 47s
                # apart, scanned to identical results down to the row
                # y-coordinates, because the screen never changed. Re-reading
                # the same pixels re-derives the same answer at 45s a try,
                # then gives up. A half-row nudge re-renders every glyph
                # against a different slice of the panel's luminance
                # gradient, which is what the misread depends on in the first
                # place; alternating the direction leaves the position where
                # it was. A list that genuinely is still loading loses
                # nothing: it gets the same 0.5s wait either way.
                if ranks:
                    self.log(f"  [scan] only {len(ranks)} badge(s) read -- "
                             + ("rows may still be loading, waiting"
                                if empty_scans < 2 else
                                "same pixels re-read the same way, nudging the list"))
                # Only a PARTIAL read is nudged. A scan that returned nothing
                # at all is not a misread of the list, it is evidence we may
                # not be looking at the list -- the main-menu ejection reads
                # exactly like this -- and moving blind on a screen we cannot
                # identify is how whole champions got lost. That path waits,
                # then hands over to recovery.
                if ranks and empty_scans >= 2:
                    nudge = 0.5 if empty_scans % 2 else -0.5
                    self.drag_rows(nudge, self.last_pitch or (H * 0.135))
                    net_down += nudge
                    settle_pending = False
                    if expected is not None:
                        expected += nudge
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
            if anomaly_confirmed:
                careful = self.arbitrate(img) if self.arbitrate is not None else {}
                # The arbiter reads the badges through a different pipeline,
                # but not through a different FONT, and it makes the same
                # tens-digit mistake: on a real frame plainly showing 33-36
                # the fast scan read 33-36 and Gemini "overruled" it with
                # 52-57, throwing the run 20 rows off.
                #
                # A disagreement of exactly one tens digit cannot be settled
                # by asking who spoke last, but it can be settled by
                # DIRECTION. The misread has only one direction: the glyph
                # binarizes thicker, closing an open top, so 3 reads as 5 and
                # 2 reads as 4. It never thins a 5 into a 3. So of two
                # readings exactly 20 apart, the LOWER one is the true one --
                # whichever side said it. That keeps the Rengar rescue (scan
                # 50-54, arbiter 30-34, arbiter wins) and refuses the Lucian
                # override (scan 32-37, arbiter 52-57, scan wins).
                if careful and abs(abs((min(careful) + max(careful)) / 2 - center) - 20) <= 2:
                    if (min(careful) + max(careful)) / 2 > center:
                        self.log(f"  [detect] arbitration says {min(careful)}-{max(careful)}, one "
                                 f"tens digit ABOVE the scan's {lo_r}-{hi_r}: that is the 3-reads-"
                                 f"as-5 misread, which only ever reads HIGH -- keeping the scan")
                        careful = {}
                if careful:
                    c_center = (min(careful) + max(careful)) / 2
                    if abs(c_center - center) > 5:
                        self.log(f"  [detect] arbitration overrules confirmed scan: screen shows "
                                 f"ranks {min(careful)}-{max(careful)} (scan claimed {lo_r}-{hi_r})")
                        ranks = careful
                        lo_r, hi_r = min(ranks), max(ranks)
                        center = (lo_r + hi_r) / 2
                elif center - expected > 5 and net_down < (center - expected) - 4:
                    # Arbitration is unavailable, but PHYSICS still rules: the
                    # list only teleports UPWARD (resets snap to rank 1). A
                    # confirmed downward jump bigger than our downward actions
                    # can explain is a deterministic misread ('30-34' read as
                    # '50-54' survived every OCR pass on a real frame). Refuse
                    # it; give arbitration fresh chances, then hand over.
                    impossible_scans += 1
                    self.log(f"  [detect] scan claims ranks {lo_r}-{hi_r} but nothing scrolled "
                             f"us down there -- refusing a downward teleport"
                             + (" (giving up)" if impossible_scans >= 3 else ""))
                    self._dump_rejected(img, rank)
                    if impossible_scans >= 3:
                        self.last_center = None
                        return None
                    use_stable = True
                    self.sleep(0.4)
                    continue
            if settle_pending and (rank in ranks or rank < max(ranks)):
                # This scan could produce a tap. Confirm the list is truly
                # stationary: a second frame (~1.2s later) must show the same
                # rows at the same ys. A gliding list cannot pass this.
                img2 = self.screenshot() if use_stable else self.screenshot_fast()
                ranks2, pitch2 = self.scan(img2, center)
                if pitch2:
                    self.last_pitch = pitch2
                shared = set(ranks) & set(ranks2)
                still = bool(shared) and all(abs(ranks[r] - ranks2[r]) <= 8 for r in shared)
                if len(ranks2) >= 3 and still:
                    settle_pending = False
                    ranks, img = ranks2, img2   # freshest truth wins
                    lo_r, hi_r = min(ranks), max(ranks)
                    center = (lo_r + hi_r) / 2
                    pitch = pitch2 or pitch
                else:
                    self.log("  [detect] list still settling after fling -- re-reading")
                    if len(ranks2) >= 3:
                        expected = (min(ranks2) + max(ranks2)) / 2
                    continue
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
                settle_pending = False
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
            # END-OF-BOARD: the target is below the window, we dragged down,
            # and the bottom row did not move a pixel. A board with fewer
            # entries than requested is a fact about the ladder, not a
            # detection failure -- report it as such instead of burning
            # recovery attempts against a list that cannot scroll further.
            # Guarded by the ledger: a TRUE bottom is reached within the
            # journey's downward budget, while a frozen misread (the scan
            # claiming ranks 1-6 forever as we scroll) has already spent more
            # downward travel than the target could need -- that case belongs
            # to the ledger lock and arbitration, not to end-of-board.
            if rank > hi_r and (down_budget is None or net_down < down_budget):
                bottom_sig = (hi_r, int(ranks[hi_r]))
                if last_bottom is not None and bottom_sig[0] == last_bottom[0] \
                        and abs(bottom_sig[1] - last_bottom[1]) <= 8:
                    bottom_stalls += 1
                    if bottom_stalls >= 2:
                        self.log(f"  [detect] the list will not scroll below rank {hi_r} "
                                 f"-- this board ends there (rank {rank} does not exist)")
                        self.bottom_rank = hi_r
                        self.last_center = (lo_r + hi_r) / 2
                        return None
                else:
                    bottom_stalls = 0
                last_bottom = bottom_sig
            else:
                bottom_stalls = 0
                last_bottom = None
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
                settle_pending = False
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
            settle_pending = True
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
