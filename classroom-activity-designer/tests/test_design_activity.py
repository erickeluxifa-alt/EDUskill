import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "design_activity.py"
SAMPLE = ROOT / "examples" / "sample_input.json"


def run(payload):
    proc = subprocess.run([sys.executable, str(SCRIPT), "-"], input=json.dumps(payload), text=True, capture_output=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


class ActivityDesignerTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads(SAMPLE.read_text(encoding="utf-8"))

    def test_sample_generates_complete_package(self):
        code, result = run(self.base)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "ok")
        for key in ("timeline", "groups", "teacher_prompts", "student_outputs", "rubric", "contingencies", "confirmation"):
            self.assertIn(key, result["activity"])
        self.assertIn("评价量规", result["markdown"])

    def test_objective_modes(self):
        for word, expected in (("解释概念", "概念排序"), ("应用方法", "情境案例"), ("分析证据", "证据辩论"), ("设计方案", "方案工作坊")):
            data = dict(self.base, objectives=[word])
            _, result = run(data)
            self.assertEqual(result["activity"]["mode"], expected)

    def test_preferred_mode_wins(self):
        data = dict(self.base, preferred_mode="方案工作坊")
        _, result = run(data)
        self.assertEqual(result["activity"]["mode"], "方案工作坊")

    def test_missing_fields_returns_errors(self):
        _, result = run({})
        self.assertEqual(result["status"], "error")
        self.assertGreaterEqual(len(result["errors"]), 3)

    def test_invalid_numbers_return_errors(self):
        data = dict(self.base, duration_minutes=0, student_count=-1)
        _, result = run(data)
        self.assertEqual(result["status"], "error")
        self.assertEqual(len(result["errors"]), 2)

    def test_short_lesson_uses_simple_flow(self):
        data = dict(self.base, duration_minutes=15)
        _, result = run(data)
        self.assertEqual(len(result["activity"]["timeline"]), 3)
        self.assertTrue(any("较短" in x for x in result["assumptions"]))

    def test_small_class_merges_roles(self):
        data = dict(self.base, student_count=3)
        _, result = run(data)
        self.assertEqual(result["activity"]["groups"]["size"], 3)
        self.assertEqual(len(result["activity"]["groups"]["roles"]), 2)

    def test_no_devices_adds_assumption(self):
        data = dict(self.base, constraints={"devices": "不可用"})
        _, result = run(data)
        self.assertTrue(any("设备不可用" in x for x in result["assumptions"]))

    def test_fixed_room_adds_contingency(self):
        _, result = run(self.base)
        self.assertTrue(any(x["case"] == "教室固定座位" for x in result["activity"]["contingencies"]))

    def test_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.json"
            proc = subprocess.run([sys.executable, str(SCRIPT), str(SAMPLE), "--output", str(target)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["status"], "ok")


if __name__ == "__main__":
    unittest.main()
