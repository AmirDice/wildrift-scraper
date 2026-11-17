"""An empty loadout data page is recorded as "no data", never captured.

On 2026-11-09 the app showed its no-data picture for Vayne baron at the top
rank; the walker captured it and the extractor read three blank rows, which
would have replaced her real baron loadout on the site.
"""
import json

from src.uiauto import Node
from scripts import walk_loadouts as W


def _node(text):
    return Node(text=text, desc="", cls="android.widget.TextView", clickable=False,
                bounds=(0, 0, 10, 10))


HEADER = [_node(t) for t in ("国服数据", "核心装备", "二级鞋", "胜率", "登场率", "最近更新：20261109")]


class _Client:
    """Nothing to dump: _has_rows must decide from the nodes it is given."""


def test_a_page_with_rate_rows_has_rows(monkeypatch):
    monkeypatch.setattr(W.uiauto, "dump", lambda client: HEADER)
    assert W._has_rows(_Client(), HEADER + [_node("1"), _node("63.83%"), _node("1.24%")], wait=0)


def test_the_empty_page_has_none(monkeypatch):
    monkeypatch.setattr(W.uiauto, "dump", lambda client: HEADER)
    assert not W._has_rows(_Client(), HEADER, wait=0)


def test_rows_that_render_late_are_waited_for(monkeypatch):
    later = HEADER + [_node("52.10%")]
    monkeypatch.setattr(W.uiauto, "dump", lambda client: later)
    assert W._has_rows(_Client(), HEADER, wait=1.0)


def test_empty_lanes_are_recorded_beside_champions(tmp_path):
    (tmp_path / W.NO_DATA_FILE).write_text(json.dumps(
        {"champions": {"Yunara": "never loads"}}), encoding="utf-8")
    W._write_no_data(tmp_path, {}, {"Vayne baron": "data page empty"})
    saved = json.loads((tmp_path / W.NO_DATA_FILE).read_text(encoding="utf-8"))
    assert saved["champions"] == {"Yunara": "never loads"}
    assert saved["lanes"] == {"Vayne baron": "data page empty"}


def test_no_data_is_settled_not_failed():
    assert W.NO_DATA_LANE in W.SETTLED


def test_the_export_skips_an_empty_capture_even_with_stale_boots():
    """The boots tab keeps the app's old numbers on an empty page, so a
    boots rate alone must not make an empty capture the newest one."""
    import inspect
    from scripts import export_loadouts_for_web as X
    src = inspect.getsource(X.main)
    assert 'if name != "boots"' in src and "no readable rows" in src


def test_star_guardian_is_not_the_guardian_rune():
    """7.3e (AAA ARAM only) named Star Guardian augments; matching that as
    the rune Guardian made it a Rift patch and shifted China's patch impact."""
    from scripts import export_loadouts_for_web as X
    calendar, changed = X._patch_calendar()
    assert "7.3e" not in [p for p, _ in calendar]
    assert "Guardian" not in changed.get("7.3e", set())
