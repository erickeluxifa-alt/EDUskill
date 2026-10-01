#!/usr/bin/env python3
"""Build an offline, reviewable classroom runbook from structured lesson data."""
import argparse
import json
import sys
from typing import Any, Dict, List, Tuple

MAX_INPUT_BYTES = 1_000_000
MAX_OBJECTIVES = 50
MAX_ACTIVITIES = 100
MAX_TEXT_LENGTH = 500


def side_effects() -> str:
    return "仅生成课堂运行单预览；不写入 LMS/SIS、不发送通知、不修改成绩或课表。"


def issue(code: str, severity: str, message: str, action: str) -> Dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "recommended_action": action}


def empty_result(status: str, issues: List[Dict[str, str]], assumptions: List[str] = None) -> Dict[str, Any]:
    return {
        "status": status,
        "summary": {"course": "", "lesson": "", "duration_minutes": 0, "objective_count": 0, "activity_count": 0, "planned_minutes": 0, "unplanned_minutes": 0},
        "timeline": [], "checkpoints": [], "differentiation": {}, "contingencies": [],
        "issues": issues, "assumptions": assumptions or [], "side_effects": side_effects(),
    }


def text_value(value: Any, field: str, problems: List[Dict[str, str]], required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        problems.append(issue("INVALID_FIELD_TYPE", "high", f"{field} 必须是字符串。", f"将 {field} 改为字符串。"))
        return ""
    value = value.strip()
    if len(value) > MAX_TEXT_LENGTH:
        problems.append(issue("TEXT_TOO_LONG", "high", f"{field} 超过 {MAX_TEXT_LENGTH} 个字符。", f"缩短 {field}。"))
        return value[:MAX_TEXT_LENGTH]
    if required and not value:
        problems.append(issue(f"MISSING_{field.upper()}", "critical", f"缺少 {field}。", f"补充 {field}。"))
    return value


def integer_value(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def normalize_objectives(raw: Any, problems: List[Dict[str, str]]) -> List[str]:
    if not isinstance(raw, list):
        return []
    if len(raw) > MAX_OBJECTIVES:
        problems.append(issue("TOO_MANY_OBJECTIVES", "high", f"目标数量超过 {MAX_OBJECTIVES} 条。", "合并或拆分后仅保留本节课目标。"))
    result = []
    for index, item in enumerate(raw[:MAX_OBJECTIVES], 1):
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict) and isinstance(item.get("description") or item.get("name"), str):
            value = str(item.get("description") or item.get("name")).strip()
        else:
            problems.append(issue("INVALID_OBJECTIVE", "high", f"第 {index} 个目标必须是字符串或带 name/description 的对象。", "修正 objectives 中的目标项。"))
            continue
        if value and len(value) <= MAX_TEXT_LENGTH:
            result.append(value)
        elif value:
            problems.append(issue("TEXT_TOO_LONG", "high", f"第 {index} 个目标过长。", f"将单个目标缩短到 {MAX_TEXT_LENGTH} 个字符以内。"))
    return result


def allocate_minutes(duration: int, weights: List[int]) -> List[int]:
    """Allocate every minute exactly once, while keeping each phase non-empty."""
    base = [1] * len(weights)
    remaining = duration - len(weights)
    if remaining < 0:
        return base[:duration] + [0] * max(0, len(weights) - duration)
    raw = [remaining * weight / sum(weights) for weight in weights]
    floors = [int(value) for value in raw]
    left = remaining - sum(floors)
    order = sorted(range(len(weights)), key=lambda index: raw[index] - floors[index], reverse=True)
    for index in order[:left]:
        floors[index] += 1
    return [base[index] + floors[index] for index in range(len(weights))]


def build_default_activities(duration: int, objectives: List[str]) -> List[Dict[str, Any]]:
    minutes = allocate_minutes(duration, [10, 25, 30, 15, 20])
    return [
        {"name": "导入与目标对齐", "minutes": minutes[0], "mode": "whole_class", "student_output": "说出已有经验或一个初步判断", "objective_refs": objectives[:1]},
        {"name": "教师建模与关键概念", "minutes": minutes[1], "mode": "mini_lesson", "student_output": "完成关键概念/步骤标注", "objective_refs": objectives[:2]},
        {"name": "引导练习", "minutes": minutes[2], "mode": "pair_or_group", "student_output": "完成一项练习并保留过程证据", "objective_refs": objectives},
        {"name": "形成性检查", "minutes": minutes[3], "mode": "individual", "student_output": "提交一道短题、口头解释或快速演示", "objective_refs": objectives[:1]},
        {"name": "反馈与收束", "minutes": minutes[4], "mode": "whole_class", "student_output": "写下一个带证据的课后行动", "objective_refs": objectives},
    ]


def normalize_activities(raw: Any, duration: int, objectives: List[str], problems: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    assumptions = []
    if raw is None or raw == []:
        assumptions.append("未提供课堂活动，使用五段式默认流程；教师需按学科与班级调整。")
        return build_default_activities(duration, objectives), assumptions
    if not isinstance(raw, list):
        problems.append(issue("INVALID_ACTIVITIES", "critical", "activities 必须是数组。", "提供活动对象数组，或删除 activities 让脚本生成默认流程。"))
        return [], assumptions
    if len(raw) > MAX_ACTIVITIES:
        problems.append(issue("TOO_MANY_ACTIVITIES", "high", f"活动数量超过 {MAX_ACTIVITIES} 项。", "只保留本节课需要运行的活动。"))
    activities = []
    for index, item in enumerate(raw[:MAX_ACTIVITIES], 1):
        if not isinstance(item, dict):
            problems.append(issue("INVALID_ACTIVITY", "high", f"第 {index} 个活动必须是对象。", "补充 name、minutes 等活动字段。"))
            continue
        name = text_value(item.get("name") or f"活动{index}", f"活动{index}.name", problems, required=True)
        mode = text_value(item.get("mode") or "whole_class", f"活动{index}.mode", problems) or "whole_class"
        output = text_value(item.get("student_output") or "待教师补充可观察产出", f"活动{index}.student_output", problems) or "待教师补充可观察产出"
        minutes = integer_value(item.get("minutes", 0))
        if minutes <= 0:
            problems.append(issue("MISSING_ACTIVITY_TIME", "medium", f"活动“{name or index}”缺少正整数 minutes。", "为每个活动补充正整数 minutes。"))
        refs = item.get("objective_refs", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            problems.append(issue("INVALID_OBJECTIVE_REFS", "medium", f"活动“{name or index}”的 objective_refs 必须是字符串数组。", "使用目标原文组成的字符串数组。"))
            refs = []
        refs = [ref.strip() for ref in refs if ref.strip()]
        activities.append({"name": name or f"活动{index}", "minutes": minutes, "mode": mode, "student_output": output, "objective_refs": refs})
    return activities, assumptions


def build(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return empty_result("INVALID_INPUT", [issue("INVALID_JSON_OBJECT", "critical", "输入必须是 JSON 对象。", "提供对象格式的课程信息。")])
    problems: List[Dict[str, str]] = []
    course = text_value(payload.get("course"), "course", problems, required=True)
    lesson = text_value(payload.get("lesson"), "lesson", problems, required=True)
    duration_raw = payload.get("duration_minutes", 0)
    duration = integer_value(duration_raw)
    if duration < 15 or duration > 240:
        problems.append(issue("INVALID_DURATION", "critical", "单次课堂时长应在 15 到 240 分钟之间，且必须是整数。", "调整 duration_minutes。"))
    objectives = normalize_objectives(payload.get("objectives"), problems)
    if not objectives:
        problems.append(issue("MISSING_OBJECTIVES", "critical", "缺少至少一个可观察的课程目标。", "补充 objectives 数组。"))
    if any(problem["severity"] == "critical" for problem in problems):
        result = empty_result("INVALID_INPUT", problems)
        result["summary"].update({"course": course, "lesson": lesson, "duration_minutes": duration})
        return result

    activities, assumptions = normalize_activities(payload.get("activities"), duration, objectives, problems)
    if any(problem["severity"] == "critical" for problem in problems):
        result = empty_result("INVALID_INPUT", problems, assumptions)
        result["summary"].update({"course": course, "lesson": lesson, "duration_minutes": duration})
        return result
    total = sum(max(0, activity["minutes"]) for activity in activities)
    unplanned = max(0, duration - total)
    if total > duration:
        problems.append(issue("TIME_OVERFLOW", "high", f"活动时长合计 {total} 分钟，超过课堂时长 {duration} 分钟。", "删减或调整活动时长后再使用。"))
    elif total < duration:
        problems.append(issue("TIME_UNPLANNED", "medium", f"活动时长合计 {total} 分钟，尚有 {unplanned} 分钟未安排。", "补充活动，或明确将剩余时间用于答疑/机动。"))
    valid_objectives = set(objectives)
    for activity in activities:
        unknown = [ref for ref in activity["objective_refs"] if ref not in valid_objectives]
        if unknown:
            problems.append(issue("UNKNOWN_OBJECTIVE_REF", "medium", f"活动“{activity['name']}”引用了未出现在 objectives 中的目标。", "统一目标文本或删除无效引用。"))

    timeline = []
    cursor = 0
    for index, activity in enumerate(activities, 1):
        start, end = cursor, cursor + max(0, activity["minutes"])
        check = "教师用全班举手、口头解释或一题快答确认理解。"
        if any(word in activity["name"] for word in ("练习", "检查", "出口", "测验", "实验")):
            check = "抽取至少两份过程证据，按正确性与解释完整度决定继续讲解或进入巩固。"
        if index == len(activities):
            check = "收集出口条/一句话回顾，记录仍需支持的目标，不作为正式成绩。"
        refs = activity["objective_refs"] or objectives[:1]
        timeline.append({
            "step": index, "name": activity["name"], "start_minute": start, "end_minute": end,
            "mode": activity["mode"], "objective_refs": refs,
            "teacher_actions": [f"明确本环节目标：{', '.join(refs)}。", "给出任务、时间边界和完成标准。", "巡视并记录代表性证据，按需调整节奏。"],
            "student_actions": [f"按 {activity['mode']} 参与活动。", "完成并保留可观察产出。"],
            "student_output": activity["student_output"], "check_for_understanding": check,
            "transition": "用一句话回收本环节证据，并说明下一环节任务。",
        })
        cursor = end

    checkpoints = [{
        "step": item["step"], "when": f"{item['end_minute']} 分钟：{item['name']}结束",
        "evidence": item["student_output"], "decision": item["check_for_understanding"],
    } for item in timeline]
    class_size = payload.get("class_size")
    if isinstance(class_size, int) and not isinstance(class_size, bool) and class_size > 0:
        sample_hint = f"班级规模 {class_size} 人；检查时至少抽取 2 份不同过程证据。"
    else:
        sample_hint = "未提供班级规模；检查时至少抽取 2 份不同过程证据。"
    differentiation = {
        "需要更多支架": "提供术语表、步骤框架、示例首步或口头回答替代书面长答。",
        "按时完成": "增加一个变式情境，要求说明选择方法的理由。",
        "提前完成": "让学生比较两种方法或为同伴设计一个检查问题。",
    }
    contingencies = [
        {"condition": "进度落后 5 分钟以上", "action": "保留形成性检查，合并分享环节，课后材料只作为延伸，不牺牲目标证据。"},
        {"condition": "全班无响应", "action": "改为匿名书写或同伴先说，再抽取自愿分享；避免点名施压。"},
        {"condition": "投影/网络/材料不可用", "action": "切换到板书、口述案例和纸笔快答，保留目标与检查点。"},
    ]
    resources = payload.get("resources")
    constraints = payload.get("constraints")
    if isinstance(resources, list) and resources:
        contingencies.append({"condition": "已列资源不可用", "action": f"优先用板书和口述替代：{', '.join(str(item) for item in resources[:5])}。"})
    if isinstance(constraints, list) and constraints:
        assumptions.append("已保留用户提供的课堂约束，教师需在开始前逐项核对：" + "；".join(str(item) for item in constraints[:5]))
    status = "needs_revision" if problems else "ready_for_review"
    return {
        "status": status,
        "summary": {"course": course, "lesson": lesson, "duration_minutes": duration, "objective_count": len(objectives), "activity_count": len(activities), "planned_minutes": total, "unplanned_minutes": unplanned, "audience": payload.get("audience") if isinstance(payload.get("audience"), str) else "", "class_size": class_size if isinstance(class_size, int) and not isinstance(class_size, bool) else None, "evidence_hint": sample_hint},
        "timeline": timeline, "checkpoints": checkpoints, "differentiation": differentiation, "contingencies": contingencies,
        "issues": problems, "assumptions": assumptions, "side_effects": side_effects(),
    }


def markdown(result: Dict[str, Any]) -> str:
    summary = result.get("summary", {})
    lines = [f"# 课堂授课运行单：{summary.get('course', '未命名')} / {summary.get('lesson', '未命名')}", "", f"状态：`{result.get('status', 'UNKNOWN')}`", f"课时：{summary.get('duration_minutes', '-')} 分钟；计划活动：{summary.get('activity_count', 0)} 项；排布：{summary.get('planned_minutes', 0)} 分钟；未安排：{summary.get('unplanned_minutes', 0)} 分钟", "", "## 时间轴"]
    for item in result.get("timeline", []):
        lines += [f"### {item['start_minute']:02d}-{item['end_minute']:02d} 分钟｜{item['name']}", f"- 目标：{'；'.join(item['objective_refs'])}", f"- 模式：{item['mode']}", f"- 教师动作：{'；'.join(item['teacher_actions'])}", f"- 学生活动：{'；'.join(item['student_actions'])}", f"- 学生产出：{item['student_output']}", f"- 理解检查：{item['check_for_understanding']}", ""]
    lines.append("## 形成性检查")
    checkpoints = result.get("checkpoints", [])
    if checkpoints:
        lines.extend("- " + "；".join(f"{key}：{value}" for key, value in item.items()) for item in checkpoints)
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 差异化支持")
    differentiation = result.get("differentiation", {})
    if differentiation:
        lines.extend(f"- **{key}**：{value}" for key, value in differentiation.items())
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 异常预案")
    contingencies = result.get("contingencies", [])
    if contingencies:
        lines.extend("- " + "；".join(f"{key}：{value}" for key, value in item.items()) for item in contingencies)
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 问题")
    issues = result.get("issues", [])
    if issues:
        lines.extend(f"- `{item['code']}`（{item['severity']}）：{item['message']} 建议：{item['recommended_action']}" for item in issues)
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 假设")
    assumptions = result.get("assumptions", [])
    lines.extend(f"- {item}" for item in assumptions) if assumptions else lines.append("- 无")
    lines += ["", "## 交互边界", f"- {result.get('side_effects', '')}"]
    return "\n".join(lines)


def read_input(path: str) -> str:
    if path == "-":
        raw = sys.stdin.read(MAX_INPUT_BYTES + 1)
    else:
        with open(path, encoding="utf-8") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError(f"输入超过 {MAX_INPUT_BYTES} 字节限制")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="JSON 文件路径，或 - 表示标准输入")
    parser.add_argument("--format", choices=["json", "md"], default="json")
    args = parser.parse_args()
    try:
        payload = json.loads(read_input(args.input))
        result = build(payload)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result = empty_result("INVALID_INPUT", [issue("INVALID_INPUT", "critical", f"无法读取或解析输入：{exc}", "检查输入文件、编码和 JSON 格式。")])
    print(markdown(result) if args.format == "md" else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
