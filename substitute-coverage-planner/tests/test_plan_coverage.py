import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan_coverage.py"
SAMPLE = ROOT / "examples" / "sample_input.json"


def run(data=None, *args):
    cmd = ["python3", str(SCRIPT), *args]
    if data is not None:
        cmd += ["--input", "-"]
        return subprocess.run(cmd, input=json.dumps(data), text=True, capture_output=True)
    return subprocess.run(cmd, text=True, capture_output=True)


class CoverageTests(unittest.TestCase):
    def test_demo_json(self):
        p = run(None, "--demo", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads(p.stdout)
        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["summary"]["substitute"], 1)
        self.assertEqual(report["summary"]["reschedule"], 1)

    def test_sample_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run(["python3", str(SCRIPT), "--input", str(SAMPLE), "--out-dir", tmp], text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue((Path(tmp) / "coverage_plan.json").is_file())
            self.assertTrue((Path(tmp) / "coverage_plan.md").is_file())

    def test_missing_required_input(self):
        p = run({"teachers": []}, "--json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("absences", p.stderr)

    def test_invalid_and_duplicate_records(self):
        absence = {"teacher_id":"A","course_id":"C","class_id":"X","subject":"S","slot":"Mon-1","students":2}
        data = {"absences":[absence, dict(absence)],
                "teachers":[{"id":"B","name":"B","subjects":["S"],"available_slots":["Mon-1"]}]}
        p = run(data, "--json")
        self.assertEqual(p.returncode, 0)
        report = json.loads(p.stdout)
        self.assertEqual(report["summary"]["total"], 1)
        self.assertTrue(any("重复" in i["message"] for i in report["issues"]))

    def test_empty_absences_warns(self):
        report = json.loads(run({"absences":[], "teachers":[]}, "--json").stdout)
        self.assertEqual(report["summary"]["total"], 0)
        self.assertTrue(any(i["level"] == "warning" for i in report["issues"]))

    def test_invalid_optional_collections_fail_cleanly(self):
        for field, value in (("rooms", None), ("class_busy", []), ("makeup_slots", {}), ("rules", [])):
            with self.subTest(field=field):
                data = {"absences":[], "teachers":[], field:value}
                p = run(data, "--json")
                self.assertEqual(p.returncode, 2)
                self.assertIn(field, p.stderr)

    def test_boolean_numeric_values_rejected(self):
        absence = {"teacher_id":"A","course_id":"C","class_id":"X","subject":"S","slot":"Mon-1","students":True}
        report = json.loads(run({"absences":[absence], "teachers":[]}, "--json").stdout)
        self.assertEqual(report["summary"]["total"], 0)
        self.assertTrue(any(i["path"].endswith(".students") for i in report["issues"]))

    def test_strict_uncovered(self):
        data = {"absences":[{"teacher_id":"A","course_id":"C","class_id":"X","subject":"S","slot":"Mon-1","students":2}],"teachers":[]}
        p = run(data, "--json", "--strict")
        self.assertEqual(p.returncode, 2)

    def test_cross_subject_rule(self):
        data = {"absences":[{"teacher_id":"A","course_id":"C","class_id":"X","subject":"S","slot":"Mon-1","students":2}],
                "teachers":[{"id":"B","name":"B","subjects":["Other"],"available_slots":["Mon-1"],"max_daily_load":3}],
                "rules":{"allow_cross_subject":True}}
        p = run(data, "--json")
        report = json.loads(p.stdout)
        self.assertEqual(report["plans"][0]["status"], "substitute")
        self.assertTrue(report["plans"][0]["candidates"][0]["cross_subject"])

    def test_reschedule_requires_instructor(self):
        absence = {"teacher_id":"A","course_id":"C","class_id":"X","subject":"S","slot":"Mon-1","students":2}
        data = {"absences":[absence], "teachers":[],
                "rooms":[{"id":"R","capacity":10,"available_slots":["Tue-1"]}], "makeup_slots":["Tue-1"]}
        report = json.loads(run(data, "--json").stdout)
        self.assertEqual(report["plans"][0]["status"], "uncovered")

    def test_reschedule_contains_all_resources(self):
        absence = {"teacher_id":"A","course_id":"C","class_id":"X","subject":"S","slot":"Mon-1","students":2}
        data = {"absences":[absence],
                "teachers":[{"id":"B","subjects":["S"],"available_slots":["Tue-1"]}],
                "rooms":[{"id":"R","capacity":10,"available_slots":["Tue-1"]}], "makeup_slots":["Tue-1"]}
        plan = json.loads(run(data, "--json").stdout)["plans"][0]
        self.assertEqual(plan["status"], "reschedule")
        self.assertEqual(plan["recommended"]["teacher"]["teacher_id"], "B")
        self.assertEqual(plan["recommended"]["room"]["room_id"], "R")

    def test_conflict_markdown_renders(self):
        data = {"absences":[
            {"teacher_id":"A","course_id":"C1","class_id":"X","subject":"S","slot":"Mon-1"},
            {"teacher_id":"D","course_id":"C2","class_id":"Y","subject":"S","slot":"Mon-1"}],
            "teachers":[{"id":"B","subjects":["S"],"available_slots":["Mon-1"]}]}
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")
            p = subprocess.run(["python3", str(SCRIPT), "--input", str(input_path), "--out-dir", tmp], text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("资源 B", (Path(tmp) / "coverage_plan.md").read_text(encoding="utf-8"))

    def test_input_source_is_mutually_exclusive(self):
        p = run(None, "--demo", "--input", str(SAMPLE), "--json")
        self.assertEqual(p.returncode, 2)

    def test_combination_conflict(self):
        data = {"absences":[
            {"teacher_id":"A","course_id":"C1","class_id":"X","subject":"S","slot":"Mon-1","students":2},
            {"teacher_id":"D","course_id":"C2","class_id":"Y","subject":"S","slot":"Mon-1","students":2}],
            "teachers":[{"id":"B","name":"B","subjects":["S"],"available_slots":["Mon-1"],"max_daily_load":3}]}
        report = json.loads(run(data, "--json").stdout)
        self.assertEqual(len(report["conflicts"]), 1)


if __name__ == "__main__":
    unittest.main()
