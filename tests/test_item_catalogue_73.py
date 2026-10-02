import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _item(catalogue, slug: str):
    return next(item for item in catalogue if item["slug"] == slug)


def test_patch_73_catalogue_values_match_web_export():
    source = _load("data/items.json")
    exported = _load("web-next/src/data/items.json")

    for slug in (
        "youmuus-ghostblade",
        "rod-of-ages",
        "knights-vow",
        "chainlaced-crushers",
        "armored-advance",
    ):
        source_item = _item(source, slug)
        exported_item = _item(exported, slug)
        assert source_item["stats"] == exported_item["stats"]
        cleaned = [
            text.replace("[physicalPen] ", "")
            .replace(" [moveSpeed]", "")
            .replace(" [hp]", "")
            for text in source_item["passives"]
        ]
        assert cleaned == exported_item["passives"]

    ghostblade = _item(source, "youmuus-ghostblade")
    assert ghostblade["stats"]["moveSpeed"] == {"value": 4, "percent": True}

    vow = _item(source, "knights-vow")
    assert "12%" in vow["passives"][1]
    assert "10%" in vow["passives"][1]
    assert "Killing a neutral monster" not in " ".join(vow["passives"])


def test_patch_73_extracted_engine_values_are_current():
    effects = _load("data/item_engine.json")

    assert effects["rod-of-ages"] == {
        "hpFlatPassive": 150,
        "manaFlatPassive": 300,
        "apFlatPassive": 40,
    }
    assert effects["knights-vow"] == {}
    assert effects["chainlaced-crushers"] == {
        "shieldFlat": {"lvlRange": [20, 140]},
        "shieldPctMaxHp": 5,
    }
    assert effects["armored-advance"] == {
        "shieldFlat": {"lvlRange": [20, 140]},
        "shieldPctMaxHp": 5,
    }
