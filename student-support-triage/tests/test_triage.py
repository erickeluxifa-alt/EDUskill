import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "triage.py"
spec = importlib.util.spec_from_file_location("triage", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_sample_routes_and_orders_critical_first():
    payload = json.loads((SCRIPT.parents[1] / "examples" / "sample.json").read_text())
    result = module.triage(payload)
    assert result["status"] == "OK"
    assert result["summary"]["valid"] == 5
    assert result["queue"][0]["urgency"] == "critical"
    assert result["summary"]["critical_or_high"] == 2
    assert result["side_effects"]["external_write"] is False


def test_alias_and_explicit_urgency():
    result = module.triage({"requests": [{"id": "X", "text": "请问选课怎么改？", "urgency": "high"}]})
    assert result["queue"][0]["topic"] == "学籍教务"
    assert result["queue"][0]["urgency"] == "high"


def test_invalid_inputs():
    assert module.triage({})["status"] == "INVALID_INPUT"
    assert module.triage({"items": []})["status"] == "INVALID_INPUT"
    result = module.triage({"items": [{"id": "X"}]})
    assert result["status"] == "OK"
    assert result["summary"]["invalid"] == 1
    assert module.triage({"items": [{"id": "X", "text": ""}]})["summary"]["invalid"] == 1


def test_boundary_and_safety():
    long_text = "系统\x00登录 " + "x" * 1500
    result = module.triage({"items": [{"text": long_text}], "max_items": 1})
    assert result["status"] == "OK"
    assert len(result["queue"][0]["draft_reply"]) < 300
    assert result["queue"][0]["status"] == "待人工确认"


def test_max_items_validation():
    assert module.triage({"items": [{"text": "你好"}], "max_items": 0})["status"] == "INVALID_INPUT"
    assert module.triage({"items": [{"text": "你好"}], "max_items": 101})["status"] == "INVALID_INPUT"
