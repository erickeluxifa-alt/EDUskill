import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_material.py"

class AuditTests(unittest.TestCase):
    def run_case(self, payload):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "input.json"
            out = Path(td) / "out"
            inp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(["python3", str(SCRIPT), str(inp), "--out", str(out)], capture_output=True, text=True)
            result = json.loads((out / "audit.json").read_text(encoding="utf-8")) if (out / "audit.json").exists() else None
            return proc, result

    def test_clean_material(self):
        data = {"title":"课程任务","sections":[{"heading":"目标","level":1,"paragraphs":["识别核心概念。"]}],"images":[],"links":[],"tables":[]}
        proc, result = self.run_case(data)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(result["summary"]["blocker"], 0)

    def test_blockers(self):
        data = {"title":"材料","sections":[{"heading":"任务","level":3,"paragraphs":["完成任务。"]}],"images":[{"id":"x","alt":""}],"links":[{"text":"点击这里","url":"https://example.edu"}],"tables":[]}
        proc, result = self.run_case(data)
        self.assertEqual(proc.returncode, 2)
        codes = {i["code"] for i in result["issues"]}
        self.assertIn("IMG_ALT_MISSING", codes)
        self.assertIn("HEADING_LEVEL_SKIP", codes)

    def test_invalid_shape(self):
        proc, result = self.run_case({"title":"x","sections":"bad"})
        self.assertEqual(proc.returncode, 1)
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
