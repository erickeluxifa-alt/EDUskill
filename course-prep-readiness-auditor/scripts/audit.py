#!/usr/bin/env python3
"""Offline course-prep readiness audit."""
import argparse
import json
import math
import re
import sys
from typing import Any, Dict, List

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

DIMENSIONS = {
    "objectives": ("学习目标", "写出 1-3 条可观察、可测量的学习目标", "critical"),
    "activities": ("学习活动", "为每个关键目标补一项学生可见的学习活动", "critical"),
    "assessments": ("评价证据", "补充学生产出、判定标准和反馈时机", "critical"),
    "resources": ("教学资源", "列出授课所需材料、设备或数据，并确认可获得", "high"),
    "differentiation": ("差异化支持", "为先备知识不足或进阶学生各补一个支持方案", "medium"),
}


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def evidence_present(item: Any) -> bool:
    if isinstance(item, dict):
        return any(str(value).strip() for value in item.values() if value is not None)
    return bool(str(item).strip()) if isinstance(item, (str, int, float)) and not isinstance(item, bool) else False


def refs(item: Any) -> List[str]:
    if not isinstance(item, dict):
        return []
    value = item.get("objective_refs", item.get("objectives", []))
    return [str(x).strip() for x in as_list(value) if str(x).strip().isdigit()]


def parse_minutes(value: Any, field: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} 必须是非负有限数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是非负有限数字") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} 必须是非负有限数字")
    return number


def infer_text(raw: str) -> Dict[str, Any]:
    sections = {key: [] for key in DIMENSIONS}
    sections["notes"] = []
    patterns = {
        "objectives": r"目标|目的|学会|理解|掌握|能够",
        "activities": r"活动|练习|讨论|实验|案例|小组|任务",
        "assessments": r"评价|测验|作业|考核|出口条|反馈|评分",
        "resources": r"资源|教材|讲义|课件|设备|数据|材料",
        "differentiation": r"差异化|分层|学困|进阶|支持|拓展",
    }
    for line in raw.splitlines():
        line = line.strip(" -*#\t")
        if not line:
            continue
        matched = False
        for key, pattern in patterns.items():
            if re.search(pattern, line):
                sections[key].append(line)
                matched = True
        if not matched:
            sections["notes"].append(line)
    sections["notes"] = " ".join(sections["notes"])
    return sections


def audit(data: Dict[str, Any]) -> Dict[str, Any]:
    if "text" in data and not any(data.get(k) for k in DIMENSIONS):
        data = {**infer_text(str(data["text"])), **{k: v for k, v in data.items() if k != "text"}}
    checks = []
    issues = []
    for key, (label, action, severity) in DIMENSIONS.items():
        items = [item for item in as_list(data.get(key)) if evidence_present(item)]
        checks.append({"dimension": key, "label": label, "present": bool(items), "evidence_count": len(items)})
        if not items:
            issues.append({"severity": severity, "code": f"missing_{key}", "message": f"缺少{label}证据", "action": action})
        if key == "assessments":
            for item in items:
                if isinstance(item, dict) and not any(str(item.get(field, "")).strip() for field in ("description", "output", "criteria", "rubric", "standard")):
                    issues.append({"severity": "high", "code": "assessment_without_criteria", "message": "评价缺少学生产出或判定标准", "action": "为评价补充 output/description 与 criteria/rubric"})

    objectives = [item for item in as_list(data.get("objectives")) if evidence_present(item)]
    objective_ids = {str(i + 1) for i in range(len(objectives))}
    activities = as_list(data.get("activities"))
    assessments = as_list(data.get("assessments"))
    activity_refs = {ref for item in activities for ref in refs(item)}
    assessment_refs = {ref for item in assessments for ref in refs(item)}
    has_explicit_refs = any(refs(item) for item in activities + assessments)
    alignment = []
    assumptions = ["未提供的维度视为缺少可审计证据", "脚本不判断学科内容正确性，目标引用按 1..N 编号解释"]
    if objectives and has_explicit_refs:
        unserved_activities = sorted(objective_ids - activity_refs, key=int)
        unserved_assessments = sorted(objective_ids - assessment_refs, key=int)
        alignment = [{"check": "objective_to_activity", "unserved_objectives": unserved_activities},
                     {"check": "objective_to_assessment", "unserved_objectives": unserved_assessments}]
        if unserved_activities:
            issues.append({"severity": "high", "code": "objective_activity_gap", "message": "部分目标没有明确活动证据", "action": "为目标 " + ", ".join(unserved_activities) + " 增加学生任务，并标注 objective_refs"})
        if unserved_assessments:
            issues.append({"severity": "high", "code": "objective_assessment_gap", "message": "部分目标没有明确评价证据", "action": "为目标 " + ", ".join(unserved_assessments) + " 增加产出和判定标准"})
    elif objectives:
        assumptions.append("活动和评价未显式标注 objective_refs，文本/字符串输入不执行目标对齐推断")

    duration = parse_minutes(data["duration_minutes"], "duration_minutes") if "duration_minutes" in data else None
    total_minutes = sum(parse_minutes(item.get("minutes", 0), "activities.minutes") for item in activities if isinstance(item, dict) and "minutes" in item)
    timing = {"duration_minutes": duration, "activity_minutes": total_minutes, "within_duration": True}
    if duration is not None and total_minutes > duration:
        timing["within_duration"] = False
        issues.append({"severity": "high", "code": "activity_overrun", "message": f"活动时长 {total_minutes:g} 分钟超过课时 {duration:g} 分钟", "action": "压缩或合并活动，并保留至少 5 分钟收束与反馈时间"})

    penalty = sum({"critical": 18, "high": 12, "medium": 7, "low": 3}.get(i["severity"], 0) for i in issues)
    score = max(0, min(100, 100 - penalty))
    status = "needs_revision" if any(i["severity"] in ("critical", "high") for i in issues) else "ready_for_review"
    actions = [i["action"] for i in sorted(issues, key=lambda x: SEVERITY_RANK[x["severity"]])]
    return {"course": data.get("course", "未命名课程"), "lesson": data.get("lesson", "未命名单元"),
            "readiness_score": score, "status": status, "dimension_checks": checks,
            "alignment_checks": alignment, "timing_check": timing, "issues": issues,
            "next_actions": actions[:6], "assumptions": assumptions}


def markdown(result: Dict[str, Any]) -> str:
    lines = [f"# 课前备课就绪度审计：{result['course']} / {result['lesson']}", "", f"- 就绪度：**{result['readiness_score']}/100**", f"- 状态：`{result['status']}`", "", "## 维度检查", "| 维度 | 证据 | 数量 |", "|---|---|---:|"]
    for item in result["dimension_checks"]:
        lines.append(f"| {item['label']} | {'有' if item['present'] else '缺失'} | {item['evidence_count']} |")
    duration = result["timing_check"]["duration_minutes"]
    duration_label = "未提供" if duration is None else f"{duration:g}"
    lines += ["", "## 对齐与边界", f"- 活动时长：{result['timing_check']['activity_minutes']:g} / {duration_label} 分钟（{'通过' if result['timing_check']['within_duration'] else '超时'}）"]
    for check in result["alignment_checks"]:
        lines.append(f"- {check['check']}：未覆盖目标 {', '.join(check['unserved_objectives']) if check['unserved_objectives'] else '无'}")
    lines += ["", "## 问题与动作"]
    if not result["issues"]:
        lines.append("- 未发现结构性缺口，建议人工复核学科内容与学生实际情况。")
    else:
        for issue in result["issues"]:
            lines.append(f"- **{issue['severity']}** {issue['message']}：{issue['action']}")
    lines += ["", "## 假设", *[f"- {x}" for x in result["assumptions"]]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit course-prep readiness offline")
    parser.add_argument("input", nargs="?", help="JSON file, or - for stdin")
    parser.add_argument("--text", help="Raw lesson text")
    parser.add_argument("--format", choices=["json", "md"], default="json")
    args = parser.parse_args()
    try:
        if args.text is not None:
            data = {"text": args.text}
        elif args.input:
            if args.input == "-":
                raw = sys.stdin.read()
            else:
                with open(args.input, encoding="utf-8") as handle:
                    raw = handle.read()
            data = json.loads(raw)
        else:
            parser.error("需要 JSON 输入文件、- 或 --text")
        if not isinstance(data, dict):
            raise ValueError("输入必须是 JSON 对象")
        result = audit(data)
        print(markdown(result) if args.format == "md" else json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
