import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "build_runbook.py"


def run(payload):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "-", "--format", "json"],
        input=json.dumps(payload), text=True, capture_output=True, check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


def test_default_plan_has_timeline_and_checkpoints():
    code, result = run({
        "course": "数学", "lesson": "函数", "duration_minutes": 40,
        "objectives": ["能识别一次函数的变化规律"],
    })
    assert code == 0
    assert result["status"] == "ready_for_review"
    assert len(result["timeline"]) == 5
    assert len(result["checkpoints"]) >= 3


def test_overlong_activities_need_revision():
    code, result = run({
        "course": "物理", "lesson": "力", "duration_minutes": 30,
        "objectives": ["能区分合力与分力"],
        "activities": [{"name": "讲解", "minutes": 35}],
    })
    assert code == 0
    assert result["status"] == "needs_revision"
    assert any(issue["code"] == "TIME_OVERFLOW" for issue in result["issues"])


def test_missing_objectives_is_invalid():
    code, result = run({"course": "语文", "lesson": "阅读", "duration_minutes": 40})
    assert code == 0
    assert result["status"] == "INVALID_INPUT"
    assert result["issues"][0]["code"] == "MISSING_OBJECTIVES"
    assert result["timeline"] == []


def test_short_default_plan_preserves_total_duration():
    for duration in (15, 16, 19, 20):
        code, result = run({
            "course": "数学", "lesson": "函数", "duration_minutes": duration,
            "objectives": ["能识别一次函数的变化规律"],
        })
        assert code == 0
        assert result["status"] == "ready_for_review"
        assert result["summary"]["planned_minutes"] == duration


def test_invalid_activity_refs_are_structured():
    code, result = run({
        "course": "物理", "lesson": "力", "duration_minutes": 30,
        "objectives": ["能区分合力与分力"],
        "activities": [{"name": "讨论", "minutes": 20, "objective_refs": [{"bad": True}]}],
    })
    assert code == 0
    assert result["status"] == "needs_revision"
    assert any(item["code"] == "INVALID_OBJECTIVE_REFS" for item in result["issues"])


def test_markdown_keeps_assumptions_and_does_not_claim_no_issues():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "-", "--format", "md"],
        input=json.dumps({
            "course": "语文", "lesson": "阅读", "duration_minutes": 40,
            "objectives": ["能概括文章主旨"], "activities": [{"name": "阅读", "minutes": 45}],
        }), text=True, capture_output=True, check=False,
    )
    assert "TIME_OVERFLOW" in proc.stdout
    assert "- 无" not in proc.stdout.split("## 问题", 1)[1].split("## 假设", 1)[0]


def test_missing_file_is_structured_error():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "/path/that/does/not/exist.json"],
        text=True, capture_output=True, check=False,
    )
    result = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert result["status"] == "INVALID_INPUT"
    assert result["issues"][0]["code"] == "INVALID_INPUT"


def test_query_matrix_covers_normal_and_boundary_inputs():
    cases = [
        ({"course": "数学", "lesson": "函数", "duration_minutes": 240, "objectives": ["目标"]}, "ready_for_review"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 14, "objectives": ["目标"]}, "INVALID_INPUT"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 241, "objectives": ["目标"]}, "INVALID_INPUT"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": True, "objectives": ["目标"]}, "INVALID_INPUT"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": []}, "INVALID_INPUT"),
        ({"course": "", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"]}, "INVALID_INPUT"),
        ({"course": "数学", "lesson": "", "duration_minutes": 40, "objectives": ["目标"]}, "INVALID_INPUT"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": [1]}, "INVALID_INPUT"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "activities": "bad"}, "INVALID_INPUT"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "activities": [{}]}, "needs_revision"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "activities": ["bad"]}, "needs_revision"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "activities": [{"name": "讨论", "minutes": 10}]}, "needs_revision"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "activities": [{"name": "讨论", "minutes": 50}]}, "needs_revision"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "activities": [{"name": "讨论", "minutes": 20, "objective_refs": ["未知"]}]}, "needs_revision"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "activities": [{"name": "讨论", "minutes": 20, "objective_refs": [1]}]}, "needs_revision"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "resources": ["课件"], "constraints": ["设备不可用"]}, "ready_for_review"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "class_size": 30}, "ready_for_review"),
        ({"course": "数学", "lesson": "函数", "duration_minutes": 40, "objectives": ["目标"], "class_size": "30"}, "ready_for_review"),
    ]
    for payload, expected in cases:
        code, result = run(payload)
        assert code == 0
        assert result["status"] == expected
        assert set(("status", "summary", "timeline", "checkpoints", "differentiation", "contingencies", "issues", "assumptions", "side_effects")) <= set(result)
