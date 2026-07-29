"""Escalation routing: explicit playstyles leave the cheap model.

gemini-3.5-flash-lite ignores explicit playstyle requests that contradict its
prior about a champion -- a Rhaast BURST request produced the drain-bruiser
build four runs out of four, with the model calling the choice deliberate,
while gemini-3.6-flash honoured the identical prompt. Routing is the fix the
prompt could not be: standard/adaptive stays cheap, explicit playstyles
escalate to ADVISOR_MODEL_PREMIUM when it is configured.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _advisor(monkeypatch, base: str, premium: str):
    monkeypatch.setenv("ADVISOR_MODEL", base)
    if premium:
        monkeypatch.setenv("ADVISOR_MODEL_PREMIUM", premium)
    else:
        monkeypatch.delenv("ADVISOR_MODEL_PREMIUM", raising=False)
    spec = importlib.util.spec_from_file_location("adv_routing", ROOT / "web" / "build_advisor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestModelRouting:
    def test_explicit_playstyles_escalate(self, monkeypatch):
        adv = _advisor(monkeypatch, "gemini-3.5-flash-lite", "gemini-3.6-flash")
        for style in ("burst", "oneshot", "tanky", "vamp", "damage"):
            assert adv.model_for_request(style) == "gemini-3.6-flash", style

    def test_standard_and_adaptive_stay_cheap(self, monkeypatch):
        adv = _advisor(monkeypatch, "gemini-3.5-flash-lite", "gemini-3.6-flash")
        for style in ("standard", "adaptive"):
            assert adv.model_for_request(style) == "gemini-3.5-flash-lite", style

    def test_unset_premium_means_no_escalation(self, monkeypatch):
        adv = _advisor(monkeypatch, "gemini-3.5-flash-lite", "")
        assert adv.model_for_request("burst") == "gemini-3.5-flash-lite"

    def test_never_escalates_across_providers(self, monkeypatch):
        """Mixing providers per-request would change auth and the response
        contract mid-pipeline; a DeepSeek base ignores a Gemini premium."""
        adv = _advisor(monkeypatch, "deepseek-v4-flash", "gemini-3.6-flash")
        assert adv.model_for_request("burst") == "deepseek-v4-flash"
