"""Regression and full-engine parity tests for Hwei; stdlib only.

python -m unittest tests.test_hwei
"""
import itertools
import json
import subprocess
import unittest
from pathlib import Path
from web.hwei import timeline
from web import fight_engine as fe

ROOT = Path(__file__).resolve().parent.parent
KIT = json.loads((ROOT / "data/hwei_kit.json").read_text(encoding="utf-8"))
TARGET = {"hp":4000,"armor":90,"mr":60,"bonusHp":1000}
AP = 100

# Expected damage is read from the KIT, not typed in. These tests are about
# the timeline -- what gets cast, when R explodes, that WW and WE exclude
# each other -- and pinning a patch's numbers here meant they quietly tested
# 7.3 values for three weeks after 7.3a, because hwei_kit.json had not been
# updated and nothing compared it with the live kit.
SPELLS = KIT["spells"]
WE_HIT = SPELLS["WE"]["base"][3] + SPELLS["WE"]["ap"] * AP
R_TICK = SPELLS["R"]["tickBase"][2] + SPELLS["R"]["tickAp"] * AP
R_BLAST = SPELLS["R"]["base"][2] + SPELLS["R"]["ap"] * AP
WW_MAX = SPELLS["WW"]["maxShieldBase"][3] + SPELLS["WW"]["maxShieldAp"] * AP


class HweiTests(unittest.TestCase):
    def run_kit(self, window=8, level=15, choices=None, **stats):
        st = {"ap":AP,"haste":0,"mana":2000,"as":0.75,"hweiChoices":choices or {}, **stats}
        return timeline(KIT,st,TARGET,window,level)

    def test_level_one_has_only_q(self):
        r = self.run_kit(level=1)
        self.assertEqual(r["casts"],{"1":1,"2":0,"3":0,"4":0})
        self.assertEqual(r["passives"],0)

    def test_shared_cooldowns_and_three_lights(self):
        r = self.run_kit(window=5)
        self.assertEqual(r["casts"],{"1":1,"2":1,"3":1,"4":1})
        self.assertEqual(r["empoweredHits"],3)
        self.assertEqual(r["manaRestored"],180)
        self.assertEqual(r["passives"],2)
        self.assertAlmostEqual(r["damage"]["2"],3*WE_HIT)

    def test_ultimate_waits_for_explosion(self):
        before, after = self.run_kit(window=4.59), self.run_kit(window=4.61)
        self.assertAlmostEqual(before["damage"]["4"],2*R_TICK)
        self.assertAlmostEqual(after["damage"]["4"],3*R_TICK+R_BLAST)

    def test_ww_trades_away_we(self):
        r = self.run_kit(choices={"2":"WW"})
        self.assertEqual(r["damage"]["2"],0)
        self.assertEqual(r["empoweredHits"],0)
        self.assertAlmostEqual(r["shield"],WW_MAX)
        self.assertAlmostEqual(r["allyShield"],WW_MAX*SPELLS["WW"]["allyMultiplier"])
        self.assertEqual(self.run_kit()["shield"],0)

    def test_mana_is_required(self):
        r = self.run_kit(window=1,mana=0)
        self.assertEqual(sum(r["casts"].values()),0)
        self.assertEqual(sum(r["damage"].values()),0)

    def test_subject_options_are_exclusive(self):
        for q,w,e in itertools.product(("QQ","QW","QE"),("WQ","WW","WE"),("EQ","EW","EE")):
            r = self.run_kit(window=5,choices={"1":q,"2":w,"3":e})
            self.assertEqual(r["casts"]["1"],1)
            self.assertEqual(r["casts"]["3"],1)
            self.assertLessEqual(r["passives"],2)
            if w!="WE": self.assertEqual(r["empoweredHits"],0)

    def test_frontend_and_python_engines_agree(self):
        cases = []
        for level, window in itertools.product((1,5,15),(0.5,1,3,4.59,4.61,8,20)):
            cases.append({"level":level,"window":window,"items":[],"runes":[],"choices":{}})
        for q,w,e in itertools.product(("QQ","QW","QE"),("WQ","WW","WE"),("EQ","EW","EE")):
            cases.append({"level":15,"window":8,"items":["blackfire-torch","rabadons-deathcap","void-staff"],
                          "runes":["Arcane Comet","Manaflow Band","Transcendence","Scorch","Bone Plating"],
                          "choices":{"1":q,"2":w,"3":e}})
        proc = subprocess.run(["node",str(ROOT/"web-next/scripts/hwei-parity.cjs")],
                              input=json.dumps(cases),text=True,capture_output=True,check=True)
        results = json.loads(proc.stdout)
        for c, ts in zip(cases,results):
            with self.subTest(c=c):
                st=fe.resolve_stats("Hwei",c["level"],c["items"],c["runes"])
                st["hweiChoices"]=c["choices"]
                r=fe.rotation("Hwei",st,TARGET,c["window"],c["level"])
                raw=timeline(KIT,st,TARGET,c["window"],c["level"])
                self.assertAlmostEqual(r["total"],ts["rotation"]["damage"],delta=0.01)
                self.assertEqual(r["nAutos"],ts["rotation"]["autos"])
                for slot in raw["damage"]:
                    self.assertAlmostEqual(raw["damage"][slot],ts["timeline"]["damage"][slot],delta=0.01)
                for key, val in ts["stats"].items(): self.assertAlmostEqual(st[key],val,delta=0.01)
                shield=fe.kit_heal("Hwei",st,c["level"],c["window"],"self")
                self.assertAlmostEqual(shield,ts["shield"],delta=0.01)

    def test_kit_matches_the_live_kit(self):
        # Both engines read Hwei from ability_formulas.json. hwei_kit.json is
        # what add_hwei.py builds him FROM, so if the two drift apart a re-run
        # of that generator silently rolls Hwei back a patch.
        live = json.loads((ROOT / "data/ability_formulas.json")
                          .read_text(encoding="utf-8"))["Hwei"]["hwei"]
        self.assertEqual(KIT["passive"], live["passive"])
        self.assertEqual(KIT["spells"], live["spells"])

    def test_published_data_is_complete(self):
        for filename in ("engine","roster","builds","champion_details"):
            data=json.loads((ROOT/f"web-next/src/data/{filename}.json").read_text(encoding="utf-8"))
            if filename=="engine":
                self.assertIn("Hwei",data["champions"])
                self.assertIn("hwei",data["formulas"]["Hwei"])
            else: self.assertIn("hwei" if filename=="champion_details" else "Hwei",data)


if __name__ == "__main__": unittest.main()
