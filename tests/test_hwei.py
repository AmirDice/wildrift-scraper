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


class HweiTests(unittest.TestCase):
    def run_kit(self, window=8, level=15, choices=None, **stats):
        st = {"ap":100,"haste":0,"mana":2000,"as":0.75,"hweiChoices":choices or {}, **stats}
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
        self.assertEqual(r["damage"]["2"],3*(60+15))

    def test_ultimate_waits_for_explosion(self):
        before, after = self.run_kit(window=4.59), self.run_kit(window=4.61)
        self.assertEqual(before["damage"]["4"],2*35)
        self.assertEqual(after["damage"]["4"],3*35+525)

    def test_ww_trades_away_we(self):
        r = self.run_kit(choices={"2":"WW"})
        self.assertEqual(r["damage"]["2"],0)
        self.assertEqual(r["empoweredHits"],0)
        self.assertEqual(r["shield"],168+71)
        self.assertAlmostEqual(r["allyShield"],(168+71)*0.85)
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

    def test_published_data_is_complete(self):
        for filename in ("engine","roster","builds","champion_details"):
            data=json.loads((ROOT/f"web-next/src/data/{filename}.json").read_text(encoding="utf-8"))
            if filename=="engine":
                self.assertIn("Hwei",data["champions"])
                self.assertIn("hwei",data["formulas"]["Hwei"])
            else: self.assertIn("hwei" if filename=="champion_details" else "Hwei",data)


if __name__ == "__main__": unittest.main()
