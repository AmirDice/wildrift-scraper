"""Offline journey simulations for the leaderboard navigator.

FakeBoard models the real phone geometry measured from captured frames
(pitch 146px, first row at y=226, 1080px screen, ~6 visible rows) and
replays the exact failure frames live runs hit, so the travel policy is
proven end-to-end without a device.
"""
from __future__ import annotations

import math

import numpy as np

from src.navigator import LeaderboardNavigator

PITCH = 146.0
H = 1080
TOP_Y = 226.0  # y of the row whose rank equals the top position (real frames)


class FakeBoard:
    def __init__(self, pos: float = 1.0, fling_step: float = 11.4) -> None:
        self.pos = pos              # rank currently sitting at TOP_Y
        self.fling_step = fling_step
        self.actions: list[tuple] = []
        self.frame = 0
        self.scan_script: dict[int, tuple[dict[int, int], float | None]] = {}

    def truth(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for r in range(max(1, math.ceil(self.pos)), math.ceil(self.pos) + 8):
            y = TOP_Y + (r - self.pos) * PITCH
            if 0 <= y <= H:
                out[r] = int(round(y))
        return out

    def true_y(self, rank: int) -> float:
        return TOP_Y + (rank - self.pos) * PITCH

    # ---- injected dependencies ----
    def screenshot(self) -> np.ndarray:
        self.frame += 1
        return np.zeros((H, 8, 3), dtype=np.uint8)

    def scan(self, img: np.ndarray, hint: float | None):
        if self.frame in self.scan_script:
            return self.scan_script[self.frame]
        t = self.truth()
        return (t, PITCH) if len(t) >= 2 else (t, None)

    def drag(self, rows: float, pitch: float) -> None:
        self.actions.append(("drag", rows))
        self.pos = max(1.0, self.pos + rows)

    def fling(self, down: bool) -> None:
        self.actions.append(("fling", down))
        self.pos = max(1.0, self.pos + (self.fling_step if down else -self.fling_step))

    def arbitrate_truth(self, img: np.ndarray) -> dict[int, int]:
        return self.truth()


def make_nav(board: FakeBoard, **kw) -> LeaderboardNavigator:
    return LeaderboardNavigator(
        screenshot=board.screenshot,
        scan=board.scan,
        drag_rows=board.drag,
        fling=board.fling,
        arbitrate=board.arbitrate_truth,
        sleep=lambda _s: None,
        log=lambda _m: None,
        **kw,
    )


def test_single_badge_scan_rejected_frame_013_replay():
    """Session 1755 frame 013: one badge read, '10' misread as '1'. The old
    loop believed it had teleported to the top and scrolled away. Now: the
    frame is rejected outright, no movement happens, the next (clean) frame
    resolves the target."""
    b = FakeBoard(pos=9.5)          # window ~10-16, like the real run
    nav = make_nav(b)
    nav.last_center = 11.5
    b.scan_script[1] = ({1: 310}, None)   # the bad frame, verbatim
    y = nav.ensure_visible(13)
    assert y is not None
    assert abs(y - b.true_y(13)) <= 2
    assert b.actions == []          # the lie produced zero movement


def test_seeded_gate_full_window_lie_stays_bounded():
    """A whole window misread 9 ranks low (dropped-digit style) at journey
    start. Since the speed rework, a well-chained TOP window is accepted
    instantly (real resets look exactly like this and happen constantly, so
    confirming each cost 1.5s). The acceptable price: a lying top window may
    cause ONE bounded drag before the plausibility gate catches the
    contradiction on the next scan -- the journey must still converge."""
    b = FakeBoard(pos=9.5)
    nav = make_nav(b)
    nav.last_center = 11.5
    lie = {r - 9: y for r, y in b.truth().items() if r - 9 >= 1}
    b.scan_script[1] = (lie, PITCH)
    y = nav.ensure_visible(13)
    assert y is not None
    assert abs(y - b.true_y(13)) <= 3
    assert len(b.actions) <= 2, f"lie caused runaway movement: {b.actions}"


def test_genuine_reset_recovers_with_drags():
    """Snap-back to rank 1 while we believed we were at ~13: the first scan is
    double-checked (teleport claim), confirmed real, then the journey walks
    down on exact drags only -- no flings for a ~7-row haul."""
    b = FakeBoard(pos=1.0)
    nav = make_nav(b)
    nav.last_center = 13.0
    y = nav.ensure_visible(13)
    assert y is not None
    assert abs(y - b.true_y(13)) <= 2
    assert all(a[0] == "drag" for a in b.actions)
    assert len(b.actions) <= 5


def test_overshooting_fling_flips_to_drags_and_converges():
    """A fling that moves 30 rows when ~11 were expected: the direction flip
    locks flings off and exact drags walk back. This was live failure #1/#2."""
    b = FakeBoard(pos=1.0, fling_step=30.0)
    nav = make_nav(b, fling_rows=10.0)
    y = nav.ensure_visible(25)
    assert y is not None
    assert abs(y - b.true_y(25)) <= 2
    fling_idx = [i for i, a in enumerate(b.actions) if a[0] == "fling"]
    assert fling_idx, "long haul should start with a fling"
    assert all(a[0] == "drag" for a in b.actions[fling_idx[-1] + 1:]), \
        "after the overshoot only drags are allowed"


def test_frozen_lie_hits_ledger_lock_then_arbitration_rescues():
    """Scans keep claiming ranks 1-6 no matter how far we scroll (the
    'impossible: I am at rank 11 and swiped down 10 times' case). The action
    ledger must lock downward travel and arbitration must finish the job."""
    b = FakeBoard(pos=1.0)
    nav = make_nav(b)
    frozen = (FakeBoard(pos=1.0).truth(), PITCH)
    b.scan_script = {i: frozen for i in range(1, 40)}
    y = nav.ensure_visible(15)
    assert y is not None
    assert abs(y - b.true_y(15)) <= 2
    assert b.pos < 23, f"ran away to {b.pos} despite the ledger"


def test_missing_target_badge_grid_inference():
    """Rank 12's badge absent from an otherwise clean scan: its row position
    is inferred from a neighbor + pitch, with zero movement."""
    b = FakeBoard(pos=9.5)
    nav = make_nav(b)
    nav.last_center = 12.0
    t = b.truth()
    true_y = t.pop(12)
    b.scan_script[1] = (t, PITCH)
    y = nav.ensure_visible(12)
    assert y is not None
    assert abs(y - true_y) <= 3
    assert b.actions == []


class GlidingBoard(FakeBoard):
    """A fling leaves residual inertia: each subsequent frame catches the
    list a bit further along until the glide dies. Frames themselves look
    perfectly static -- exactly the live rank-29 failure."""

    def __init__(self, *a, glide=(1.0, 0.4), **kw) -> None:
        super().__init__(*a, **kw)
        self.glide_profile = list(glide)
        self.pending_glide: list[float] = []

    def fling(self, down: bool) -> None:
        super().fling(down)
        self.pending_glide = [g if down else -g for g in self.glide_profile]

    def drag(self, rows: float, pitch: float) -> None:
        self.pending_glide = []   # touching the list kills inertia
        super().drag(rows, pitch)

    def screenshot(self):
        img = super().screenshot()
        # this frame captured the CURRENT position; the glide continues after
        if self.pending_glide:
            self.pos = max(1.0, self.pos + self.pending_glide.pop(0))
        return img


def test_post_fling_glide_is_never_trusted_rank29_replay():
    """Garen rank 29: the journey's last fling left the list gliding; a scan
    read rank 29 at y=765, the list slid one more row before the taps landed,
    and the chain opened rank 30's profile believing it was 29's. The
    navigator must never act on a single post-fling frame: it re-reads until
    two consecutive frames agree, and only then returns a tap y."""
    b = GlidingBoard(pos=1.0, fling_step=12.0)
    nav = make_nav(b, fling_rows=10.0)
    nav.last_center = 3.0          # journey starts from a post-reset top window
    y = nav.ensure_visible(29)
    assert y is not None
    assert not b.pending_glide, "returned a tap y while the list was still gliding"
    assert abs(y - b.true_y(29)) <= 8, \
        f"tap y {y} vs settled row {b.true_y(29):.0f} -- stale by {abs(y - b.true_y(29)):.0f}px"


def test_drag_journeys_pay_no_settle_tax():
    """Drags are inertia-free, so short journeys must not spend extra frames
    on settle confirmation -- the speed pass depends on the one-screenshot
    happy path."""
    b = FakeBoard(pos=9.5)
    nav = make_nav(b)
    nav.last_center = 11.5
    y = nav.ensure_visible(14)     # 2 rows away: pure drag territory
    assert y is not None
    assert abs(y - b.true_y(14)) <= 2
    assert b.frame <= 3, f"drag journey took {b.frame} frames"


def test_top_ranks_reachable_when_trophy_badges_fail():
    """Live failure: 'it sees only 3-5' -- ranks 1-2's trophy badges don't
    OCR at the top of the list. Multi-step grid inference must still reach
    both rows without any movement."""
    for target in (1, 2):
        b = FakeBoard(pos=1.0)
        nav = make_nav(b)
        t = {r: y for r, y in b.truth().items() if r >= 3}   # scan sees only 3+
        b.scan_script = {i: (t, PITCH) for i in range(1, 20)}
        y = nav.ensure_visible(target)
        assert y is not None, f"rank {target} unreachable"
        assert abs(y - b.true_y(target)) <= 3
        assert b.actions == []


def test_bottom_edge_scrolls_instead_of_guessing_downward():
    """Live failure: window read 6-10, target 11 not yet visible, and the bot
    inferred 11 BELOW the lowest read badge and tapped a phantom row.
    Downward inference is banned: it must scroll first, then read 11."""
    b = FakeBoard(pos=5.2)                       # truth window 6-11, 11 at bottom
    nav = make_nav(b)
    nav.last_center = 8.0
    t1 = {r: y for r, y in b.truth().items() if r <= 10}  # 11 unreadable
    b.scan_script[1] = (t1, PITCH)
    y = nav.ensure_visible(11)
    assert y is not None
    assert abs(y - b.true_y(11)) <= 3
    assert any(a[0] == "drag" for a in b.actions), "must scroll, not guess"


def test_partially_loaded_page_waits_instead_of_acting():
    """Live log: after a reset the refreshed rows populate progressively, so a
    scan can read only '11-12' while 13+ are still skeletons. A <3 badge scan
    must WAIT for the page, not navigate on it."""
    b = FakeBoard(pos=8.4)                       # truth window 9-14
    nav = make_nav(b)
    nav.last_center = 10.0
    t = b.truth()
    partial = {r: t[r] for r in (11, 12) if r in t}
    b.scan_script[1] = (partial, PITCH)          # frame 1: two badges only
    b.scan_script[2] = (partial, PITCH)          # still loading
    y = nav.ensure_visible(13)
    assert y is not None
    assert abs(y - b.true_y(13)) <= 3
    # the two partial frames must not have produced any movement
    assert b.actions == [] or b.actions[0][0] != "fling"


def test_never_finds_target_bails_to_manual():
    """If scans stay garbage, the journey must end at the manual prompt --
    never wander indefinitely."""
    b = FakeBoard(pos=1.0)
    nav = make_nav(b)
    b.scan_script = {i: ({}, None) for i in range(1, 40)}
    assert nav.ensure_visible(13) is None
    assert b.actions == []          # no movement without evidence
