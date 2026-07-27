"""The Vercel Python function that replaced the subprocess spawn.

The generation itself is not exercised here (it costs a real DeepSeek call);
what matters is that the wrapper validates, sanitises and fails safely, because
it is now a publicly reachable endpoint that spends money.
"""
from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
advisor_api = importlib.import_module("api.advisor")


class TestRequestValidation:
    def test_a_missing_champion_is_rejected_before_any_model_call(self):
        status, payload = advisor_api.build_from_request({})
        assert status == 400
        assert "champion is required" in payload["error"]

    def test_counter_mode_requires_an_enemy(self):
        status, payload = advisor_api.build_from_request(
            {"champion": "Hecarim", "mode": "counter", "enemies": []})
        assert status == 400
        assert "enemy is required" in payload["error"]

    def test_an_unknown_playstyle_is_reported_not_crashed(self, monkeypatch):
        status, payload = advisor_api.build_from_request(
            {"champion": "Hecarim", "role": "Jungle", "playstyle": "nonsense"})
        assert status == 400
        assert "error" in payload


class TestSanitising:
    def test_shell_and_markup_characters_are_stripped(self):
        assert advisor_api._clean("Hec$(rm -rf /)arim") == "Hecrm -rf arim"
        assert advisor_api._clean("<script>alert(1)</script>") == "scriptalert1script"

    def test_legitimate_champion_names_survive(self):
        for name in ("Kai'Sa", "Dr. Mundo", "Nunu & Willump", "Vel'Koz",
                     "Master Yi", "Lee Sin"):
            assert advisor_api._clean(name) == name

    def test_input_length_is_capped(self):
        assert len(advisor_api._clean("A" * 500)) == 40

    def test_lists_are_capped_and_emptied_of_junk(self):
        assert advisor_api._clean_list(["Ashe", "", "  ", "Jinx"]) == ["Ashe", "Jinx"]
        assert len(advisor_api._clean_list([f"Champ{i}" for i in range(20)])) == 5
        assert advisor_api._clean_list("not a list") == []
        assert advisor_api._clean_list([{"nested": "object"}]) == []

    def test_locks_are_capped_to_the_advisor_limits(self):
        assert len(advisor_api._clean_list(["a", "b", "c", "d", "e"], limit=3)) == 3
        assert len(advisor_api._clean_list(["a", "b", "c"], limit=2)) == 2


class TestFailureHandling:
    def test_an_advisor_exception_becomes_a_502_without_leaking_a_traceback(
            self, monkeypatch, capsys):
        def explode(**_kwargs):
            raise RuntimeError("deepseek 500: upstream on fire")
        monkeypatch.setattr(advisor_api, "advise", explode)

        status, payload = advisor_api.build_from_request(
            {"champion": "Hecarim", "role": "Jungle"})
        assert status == 502
        assert "advisor failed" in payload["error"]
        # The detail goes to the log, not the response.
        assert "Traceback" not in payload["error"]
        assert "Traceback" in capsys.readouterr().err

    def test_a_missing_api_key_is_a_500_not_a_crash(self, monkeypatch):
        def no_key(**_kwargs):
            raise SystemExit("DEEPSEEK_API_KEY is not set")
        monkeypatch.setattr(advisor_api, "advise", no_key)

        status, payload = advisor_api.build_from_request(
            {"champion": "Hecarim", "role": "Jungle"})
        assert status == 500
        assert "DEEPSEEK_API_KEY" in payload["error"]

    def test_a_successful_build_passes_straight_through(self, monkeypatch):
        monkeypatch.setattr(advisor_api, "advise",
                            lambda **_kwargs: {"items": ["black-cleaver"]})
        status, payload = advisor_api.build_from_request(
            {"champion": "Hecarim", "role": "Jungle"})
        assert status == 200
        assert payload["items"] == ["black-cleaver"]


class TestDeploymentShape:
    def test_the_function_can_import_the_advisor_from_the_repo_root(self):
        """It sits in api/ while the advisor is in web/, so sys.path matters."""
        assert callable(advisor_api.advise)

    def test_the_advisor_function_config_asks_for_a_long_enough_timeout(self):
        """Read from vercel.json.advisor, which is NOT named vercel.json.

        A vercel.json at the repo root breaks the SITE project's build, even
        though that project's Root Directory is web-next: its `functions`
        pattern matches nothing there. Committing one failed the deployment
        before any build ran, twice. So the advisor's intended function config
        lives here as a record of the settings to apply, and the values are
        applied in the Vercel dashboard instead.
        """
        import json
        config = json.loads((ROOT / "vercel.json.advisor").read_text(encoding="utf-8"))
        fn = config["functions"]["api/advisor.py"]
        # The TS route's own timeout is 240s; the function must outlast it.
        assert fn["maxDuration"] >= 240
        # No `runtime` key on purpose. Vercel detects Python from the .py
        # extension, and `runtime` is only valid for COMMUNITY runtimes -- a
        # value like "python3.12" fails config validation and breaks the build.
        assert "runtime" not in fn, (
            "drop `runtime`: Python is detected from the extension, and setting "
            "it fails Vercel config validation")

    def test_no_vercel_json_sits_at_the_repo_root(self):
        """The one that breaks the site project's deployment.

        Proven twice: commit 6ec257b's version, and again on 2026-07-27 with a
        functions-only version, both of which failed the site deployment at
        config time. Anything that recreates this file re-breaks the site.
        """
        assert not (ROOT / "vercel.json").exists(), (
            "a repo-root vercel.json fails the site project's build; the advisor's "
            "settings belong in vercel.json.advisor and the Vercel dashboard")

    def test_the_function_only_needs_what_requirements_txt_installs(self):
        """requirements.txt is the advisor bundle, and it has a 250MB ceiling.

        It used to carry streamlit, pandas, opencv and numpy, none of which the
        function imports, which would very likely have breached that limit the
        first time anyone tried to deploy it.
        """
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        listed = {line.split(">=")[0].split("==")[0].strip().lower()
                  for line in text.splitlines()
                  if line.strip() and not line.strip().startswith("#")}
        assert listed == {"requests"}, (
            f"unexpected packages in the advisor bundle: {sorted(listed - {'requests'})}. "
            "Scraper and Streamlit deps belong in requirements-scrape.txt.")

    def test_the_body_size_cap_is_small(self):
        """This endpoint spends money, so it should not accept large payloads."""
        assert advisor_api.MAX_BODY_BYTES <= 32_768
