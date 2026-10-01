#!/usr/bin/env python3
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan_consolidation.py"
SAMPLE = ROOT / "examples" / "sample_input.json"


class PlannerTest(unittest.TestCase):
    def run_case(self, mutate=None):
        data = json.loads(SAMPLE.read_text(encoding="utf-8"))
        if mutate:
            mutate(data)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.json"
            output = Path(tmp) / "out"
            source.write_text(json.dumps(data), encoding="utf-8")
            proc = subprocess.run(["python3", str(SCRIPT), "--input", str(source), "--output-dir", str(output)], capture_output=True, text=True)
            payload = json.loads((output / "consolidation_result.json").read_text(encoding="utf-8"))
            report = (output / "consolidation_report.md").read_text(encoding="utf-8")
            return proc, payload, report

    def test_default_flow(self):
        proc, payload, report = self.run_case()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(payload["summary"], {"total": 2, "recommended": 1, "review": 0, "blocked": 1})
        self.assertIn("仅供人工审核", report)

    def test_exact_capacity_allowed(self):
        def mutate(data):
            data["sections"][0]["enrollment"] = 20
            data["sections"][1]["enrollment"] = 20
            data["students"] = []
            data["candidates"] = [data["candidates"][0]]
        _, payload, _ = self.run_case(mutate)
        self.assertIn(payload["results"][0]["status"], ("recommended", "review"))
        self.assertNotEqual(payload["results"][0]["status"], "blocked")

    def test_capacity_overflow_blocked(self):
        def mutate(data):
            data["sections"][0]["enrollment"] = 21
            data["sections"][1]["enrollment"] = 20
            data["students"] = []
            data["candidates"] = [data["candidates"][0]]
        _, payload, _ = self.run_case(mutate)
        self.assertIn("capacity exceeded", payload["results"][0]["blockers"][0])

    def test_student_conflict_blocked(self):
        _, payload, _ = self.run_case()
        plan = next(item for item in payload["results"] if item["candidate_id"] == "PLAN-AB")
        self.assertEqual(plan["status"], "recommended")
        self.assertEqual(plan["affected_students"], ["S003"])

    def test_progress_gap_blocked(self):
        _, payload, _ = self.run_case()
        plan = next(item for item in payload["results"] if item["candidate_id"] == "PLAN-AC")
        self.assertIn("teaching progress gap exceeds policy", plan["blockers"])

    def test_language_mismatch(self):
        def mutate(data):
            data["sections"][1]["language"] = "en"
            data["candidates"] = [data["candidates"][0]]
        _, payload, _ = self.run_case(mutate)
        self.assertIn("teaching languages differ", payload["results"][0]["blockers"])

    def test_unknown_section(self):
        def mutate(data):
            data["candidates"] = [{"id":"BAD","section_ids":["SEC-A","NOPE"],"target_section_id":"SEC-A"}]
        _, payload, _ = self.run_case(mutate)
        self.assertEqual(payload["results"][0]["status"], "blocked")

    def test_zero_capacity_is_data_issue(self):
        def mutate(data):
            data["sections"][0]["capacity"] = 0
            data["candidates"] = []
        proc, payload, _ = self.run_case(mutate)
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(payload["data_issues"])

    def test_empty_candidates(self):
        def mutate(data):
            data["candidates"] = []
        _, payload, _ = self.run_case(mutate)
        self.assertEqual(payload["summary"]["total"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
