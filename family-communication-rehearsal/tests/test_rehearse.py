import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rehearse import MAX_FILE_BYTES, load_payload, markdown, rehearse


class RehearseTests(unittest.TestCase):
    def base(self):
        return {
            "class_name": "八年级2班",
            "student": {"id": "S001", "name": "示例甲"},
            "context": {"channel": "phone", "purpose": "阶段反馈"},
            "observations": [
                {"date": "2026-09-08", "domain": "作业", "fact": "4次作业中2次按时提交", "source": "作业记录"}
            ],
            "strengths": ["小组资料整理细致"],
            "support_options": ["提供任务清单"],
            "requested_actions": ["下周复核"]
        }

    def test_happy_path_is_review_only(self):
        result = rehearse(self.base())
        self.assertEqual("REVIEW_REQUIRED", result["status"])
        self.assertFalse(result["side_effects"]["message_sent"])
        self.assertIn("根据作业记录", result["fact_cards"][0]["statement"])

    def test_missing_observations(self):
        payload = self.base()
        payload.pop("observations")
        result = rehearse(payload)
        self.assertEqual("INVALID_INPUT", result["status"])

    def test_invalid_date(self):
        payload = self.base()
        payload["observations"][0]["date"] = "2026-02-30"
        result = rehearse(payload)
        self.assertEqual("INVALID_INPUT", result["status"])

    def test_risky_language_flagged(self):
        payload = self.base()
        payload["observations"][0]["fact"] = "学生总是懒，家长没管"
        categories = {item["category"] for item in rehearse(payload)["risk_review"]}
        self.assertTrue({"labeling", "absolute", "blaming"}.issubset(categories))

    def test_crisis_signal_escalates(self):
        payload = self.base()
        payload["observations"][0]["fact"] = "学生提到不想活"
        result = rehearse(payload)
        self.assertEqual("SAFETY_ESCALATION_REQUIRED", result["status"])
        self.assertTrue(result["must_stop"])
        self.assertEqual([], result["agenda"])
        self.assertIn("停止常规预演", markdown(result))

    def test_observation_limit_is_rejected_without_truncation(self):
        payload = self.base()
        payload["observations"] *= 21
        result = rehearse(payload)
        self.assertEqual("INVALID_INPUT", result["status"])
        self.assertTrue(any("最多包含 20 项" in item for item in result["errors"]))

    def test_non_string_nested_value_is_rejected(self):
        payload = self.base()
        payload["observations"][0]["source"] = {"name": "记录"}
        self.assertEqual("INVALID_INPUT", rehearse(payload)["status"])

    def test_invalid_context_type_is_rejected(self):
        payload = self.base()
        payload["context"] = "phone"
        self.assertEqual("INVALID_INPUT", rehearse(payload)["status"])

    def test_risk_term_in_context_is_scanned(self):
        payload = self.base()
        payload["context"]["purpose"] = "确认是否心理有问题"
        categories = {item["category"] for item in rehearse(payload)["risk_review"]}
        self.assertIn("diagnostic", categories)

    def test_markdown_link_syntax_is_escaped(self):
        payload = self.base()
        payload["observations"][0]["fact"] = "[点击](https://example.invalid)"
        rendered = markdown(rehearse(payload))
        self.assertNotIn("[点击](https://example.invalid)", rendered)

    def test_oversized_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * (MAX_FILE_BYTES + 1))
            payload, result = load_payload(path)
        self.assertIsNone(payload)
        self.assertEqual("INVALID_INPUT", result["status"])

    def test_defaults_remain_explicit(self):
        payload = self.base()
        payload.pop("strengths")
        payload.pop("support_options")
        payload.pop("requested_actions")
        result = rehearse(payload)
        self.assertIn("未提供", result["strengths"][0])
        self.assertIn("补充", result["support_options"][0])

    def test_html_is_escaped(self):
        payload = self.base()
        payload["observations"][0]["fact"] = "<script>alert(1)</script>"
        rendered = markdown(rehearse(payload))
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_control_chars_and_length_are_sanitized(self):
        payload = self.base()
        payload["observations"][0]["fact"] = "a\x00b" + "x" * 1000
        result = rehearse(payload)
        self.assertNotIn("\x00", result["fact_cards"][0]["fact"])
        self.assertLessEqual(len(result["fact_cards"][0]["fact"]), 600)

    def test_observations_are_sorted(self):
        payload = self.base()
        payload["observations"].append({"date": "2026-09-01", "domain": "课堂", "fact": "完成展示", "source": "观察"})
        result = rehearse(payload)
        self.assertEqual("2026-09-01", result["fact_cards"][0]["date"])

    def test_non_list_optional_field_rejected(self):
        payload = self.base()
        payload["strengths"] = "认真"
        self.assertEqual("INVALID_INPUT", rehearse(payload)["status"])

    def run_cli(self, payload, *args):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "rehearse.py"), str(path), *args],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_cli_json_success_exit_code(self):
        completed = self.run_cli(self.base(), "--json")
        self.assertEqual(0, completed.returncode)
        self.assertEqual("REVIEW_REQUIRED", json.loads(completed.stdout)["status"])

    def test_cli_invalid_input_exit_code(self):
        payload = self.base()
        payload.pop("observations")
        completed = self.run_cli(payload, "--json")
        self.assertEqual(2, completed.returncode)
        self.assertEqual("INVALID_INPUT", json.loads(completed.stdout)["status"])

    def test_cli_safety_exit_code(self):
        payload = self.base()
        payload["observations"][0]["fact"] = "学生提到不想活"
        completed = self.run_cli(payload, "--json")
        self.assertEqual(2, completed.returncode)
        self.assertTrue(json.loads(completed.stdout)["must_stop"])

    def test_exact_observation_limit_is_accepted(self):
        payload = self.base()
        payload["observations"] *= 20
        self.assertEqual("REVIEW_REQUIRED", rehearse(payload)["status"])


if __name__ == "__main__":
    unittest.main()
