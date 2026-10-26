"""Regression mot den levererade HTML-modellen och dess 40 referensutfall."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import model_adapter as adapter


class ModelRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        adapter.ensure_node()
        base = dict(adapter.DEFAULTS)
        cls.fixtures = [base]
        cls.fixtures += [{**base, "projectSpecies": species, "analysisYears": years}
                         for species, years in (("pine",50),("beech",100),("oak",150),
                                                ("mixed",200),("conifers",100))]
        cls.fixtures += [{**base, "projectType": "landscape", "currentLandUse": "forest",
                          "referenceScenario": "conventionalForest", "projectForestScenario": scenario,
                          "systemBoundary": boundary, "analysisYears": 100}
                         for scenario, boundary in (("conventional","ecosystem"),
                                                   ("continuous","hwp"),
                                                   ("extended","substitution"),
                                                   ("intensive","substitution"),
                                                   ("mix","hwp"))]
        cls.fixtures += [{**base,"projectType":"existing","projectStartAge":60,
                          "referenceStartAge":60,"initialLiveC":100,"currentLandUse":"forest",
                          "projectForestScenario":"continuous","referenceScenario":"conventionalForest",
                          "ccfMethod":"interval","ccfInterval":15,"ccfRemoval":0.2,
                          "systemBoundary":"substitution","structuralShareProject":0.1,
                          "structuralShareReference":0.05,"areaHa":7.5},
                         {**base,"soilType":"organic","analysisYears":50},
                         {**base,"currentLandUse":"sealed","restorationScenario":"partial"},
                         {**base,"referenceSoilMethod":"gisDirect","gisRefSocChange":-0.2,
                          "gisRefDomChange":0.05,"analysisYears":75},
                         {**base,"includeSoilDom":False,"areaHa":10,"analysisYears":300}]
        driver = r'''
const fs=require('node:fs'),vm=require('node:vm');
const req=JSON.parse(fs.readFileSync(0,'utf8'));
const scripts=fs.readFileSync(req.html,'utf8').matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g);
const ctx=vm.createContext({});ctx.self=ctx;
for(const [n,s] of Array.from(scripts).entries()) if(n<3) vm.runInContext(s[1],ctx);
process.stdout.write(JSON.stringify(req.inputs.map(i=>ctx.ForestModel.simulate(i))));
'''
        node = adapter.original.os.environ["SKOGS_NODE"]
        done = subprocess.run([node,"-e",driver],input=json.dumps({"html":str(ROOT/"webbmodell.html"),
                              "inputs":cls.fixtures}),capture_output=True,text=True,check=True,timeout=120)
        cls.html_results=json.loads(done.stdout)

    def test_source_hashes(self):
        manifest=json.loads((ROOT/"original_hashes.json").read_text())
        for name, expected in manifest.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected)

    def test_identical_javascript_sources(self):
        scripts=re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',(ROOT/"webbmodell.html").read_text())
        for original, script in zip([adapter.original._JS_MODEL,adapter.original._JS_STUDIES,
                                     adapter.original._JS_CONTROLS],scripts[:3]):
            self.assertEqual(original.strip(),script.strip())

    def test_all_inputs_covered(self):
        self.assertEqual(len(adapter.FIELDS),84)
        self.assertEqual(adapter.DEFAULTS,adapter.original.default_inputs())
        self.assertEqual(set(adapter.FIELDS),set(adapter.DEFAULTS))

    def test_full_results_identical_to_html(self):
        for index,(inputs,expected) in enumerate(zip(self.fixtures,self.html_results)):
            with self.subTest(scenario=index):
                self.assertEqual(adapter.simulate(inputs),expected)

    def test_default_numeric_baseline(self):
        summary=adapter.simulate(adapter.DEFAULTS)["summary"]
        self.assertAlmostEqual(summary["netCumulativeCo2PerHa"],1158.4161511633881,places=8)
        self.assertAlmostEqual(summary["projectBonitet"],6.9,places=10)

    def test_net_and_area_consistency(self):
        result=adapter.simulate({**adapter.DEFAULTS,"areaHa":7.5})
        s=result["summary"]
        self.assertAlmostEqual(s["netTotalCo2"],s["netCumulativeCo2PerHa"]*7.5,places=8)
        for row in result["rows"]:
            self.assertAlmostEqual(row["netCumulativeCo2"],row["grossCumulativeCo2"]-row["referenceCumulativeCo2"],places=8)
            self.assertAlmostEqual(row["netCumulativeCo2"],row["netCumulativeC"]*44/12,places=8)

    def test_json_round_trip(self):
        raw={**adapter.DEFAULTS,"projectName":"Åkermark till skog – kommunens försök", "areaHa":12.75}
        self.assertEqual(adapter.read_scenario(adapter.scenario_bytes(raw)),raw)
        self.assertEqual(adapter.read_scenario(json.dumps(raw).encode()),raw)

    def test_reject_invalid_scenario(self):
        for content in (b'[]',b'{',b'{"areaHa":-1}',b'{"areaHa":NaN}',
                        b'{"projectType":"bad"}',b'{"includeSoilDom":"false"}',
                        b'{"inputs":[]}',b'{"analysisYears":100.4}'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                adapter.read_scenario(content)

    def test_all_40_reference_outputs_match_delivery(self):
        expected=json.loads((ROOT/"tests/original_referenskontroll.json").read_text())["records"]
        actual=adapter.reference_checks()
        self.assertEqual(len(actual),40)
        self.assertEqual([v["id"] for v in actual],[v["id"] for v in expected])
        for a,b in zip(actual,expected):
            with self.subTest(reference=a["id"]):
                for field in ("value","low","high"):
                    if a[field] is None or b[field] is None:
                        self.assertEqual(a[field],b[field])
                    else:
                        self.assertAlmostEqual(a[field],b[field],places=7)
                self.assertEqual(a["status"],b["status"])

    def test_comparison_matches_separate_runs(self):
        base={**adapter.DEFAULTS,"analysisYears":50}
        values=adapter.compare(base)
        self.assertEqual(len(values),6)
        for value in values:
            result=adapter.simulate({**base,"projectForestScenario":value["scenario"]})
            self.assertEqual(value["netAtEnd"],result["summary"]["netCumulativeCo2PerHa"])
            self.assertEqual(value["series"],[r["netCumulativeCo2"] for r in result["rows"]])


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "Streamlit är inte installerat i testmiljön")
class StreamlitIntegration(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/"streamlit_app.py"),default_timeout=90).run()

    def test_initial_results_and_area_change(self):
        app=self.app()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric),4)
        app.number_input(key="field_areaHa").set_value(2.0).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[3].value,"2 317")

    def test_change_project_type_and_scenario(self):
        app=self.app()
        app.selectbox(key="field_projectType").set_value("landscape").run()
        app.selectbox(key="field_currentLandUse").set_value("forest").run()
        app.selectbox(key="field_referenceScenario").set_value("conventionalForest").run()
        app.selectbox(key="field_projectForestScenario").set_value("continuous").run()
        self.assertFalse(app.exception)
        app.checkbox(key="field_includeSoilDom").set_value(False).run()
        app.checkbox(key="field_includeSoilDom").set_value(True).run()
        self.assertFalse(app.exception)

    def test_reference_checks_page(self):
        app=self.app()
        app.sidebar.radio[0].set_value("Referenskontroller").run()
        next(b for b in app.button if b.label=="Kör referenskontroller").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)

    def test_original_and_guide_pages(self):
        app=self.app()
        for page in ("Original webbmodell","Publicera och använd"):
            app.sidebar.radio[0].set_value(page).run()
            self.assertFalse(app.exception)


if __name__=="__main__":
    unittest.main(verbosity=2)
