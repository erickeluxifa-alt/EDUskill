#!/usr/bin/env python3
"""Convert teaching-quality findings into an actionable closure register."""
import json
import sys
from datetime import date, timedelta

SEVERITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}
SEVERITY_ALIASES = {
    "严重": "critical", "重大": "critical", "高": "high", "高风险": "high",
    "中": "medium", "一般": "medium", "低": "low", "轻微": "low"
}
TYPE_HINTS = {
    "课程目标": "curriculum", "教学目标": "curriculum", "考核": "assessment",
    "作业": "assessment", "课堂": "instruction", "互动": "instruction",
    "实验": "practice", "资源": "resource", "教材": "resource",
    "数据": "data", "公平": "student_support", "学生": "student_support",
    "反馈": "student_support", "教室": "resource"
}
OWNER = {
    "curriculum": "课程负责人",
    "assessment": "任课教师与教研组",
    "instruction": "任课教师",
    "practice": "实验/实践负责人",
    "resource": "院系教学秘书",
    "data": "教学管理者与数据管理员",
    "student_support": "班主任/辅导员"
}

def text_of(item):
    if isinstance(item, str):
        return item.strip()
    return str(item.get("description") or item.get("issue") or item.get("finding") or "").strip()

def classify(text):
    for key, kind in TYPE_HINTS.items():
        if key in text:
            return kind
    return "instruction"

def severity_of(item, text):
    value = item.get("severity") if isinstance(item, dict) else None
    value = str(value or "").lower()
    value = SEVERITY_ALIASES.get(value, value)
    if value in SEVERITY:
        return value
    if any(word in text for word in ("安全", "合规", "大面积", "无法参加")):
        return "critical"
    if any(word in text for word in ("普遍", "明显", "多名", "逾期")):
        return "high"
    if any(word in text for word in ("偶发", "个别", "建议")):
        return "low"
    return "medium"

def action_for(kind, text):
    actions = {
        "curriculum": "补齐目标与内容映射，提交教研组复核后更新课程材料",
        "assessment": "复核考核规则与评分标准，抽样验证公平性并留存修订记录",
        "instruction": "调整课堂流程或互动设计，下一次授课后收集快速反馈",
        "practice": "核对实践资源与安全要求，安排补做或替代任务并记录结果",
        "resource": "补充或替换教学资源，确认所有学生可访问并记录链接/版本",
        "data": "核对数据口径与权限，修正报表后由教学管理者复核",
        "student_support": "识别受影响学生并提供等价支持，跟踪完成情况后复核"
    }
    return actions[kind]

def build_register(payload):
    if not isinstance(payload, dict):
        raise ValueError("输入必须是 JSON 对象")
    raw = payload.get("findings") or payload.get("issues") or payload.get("问题")
    if not isinstance(raw, list) or not raw:
        raise ValueError("findings/issues 必须是非空数组")
    max_items = payload.get("max_items", 100)
    if not isinstance(max_items, int) or max_items < 1 or max_items > 100:
        raise ValueError("max_items 必须在 1—100 之间")
    today = date.today()
    items = []
    for index, raw_item in enumerate(raw[:max_items], 1):
        text = text_of(raw_item)
        if not text:
            continue
        severity = severity_of(raw_item, text)
        kind = classify(text)
        days = {"critical": 3, "high": 7, "medium": 14, "low": 21}[severity]
        owner = raw_item.get("owner") if isinstance(raw_item, dict) else None
        due = raw_item.get("due_date") if isinstance(raw_item, dict) else None
        items.append({
            "id": f"TQ-{index:03d}", "finding": text, "category": kind,
            "severity": severity, "priority_score": SEVERITY[severity],
            "owner": owner or OWNER[kind], "recommended_action": action_for(kind, text),
            "target_date": due or (today + timedelta(days=days)).isoformat(),
            "evidence_to_close": "整改材料/修订版本 + 复核记录 + 影响范围结果",
            "status": "待确认", "needs_human_confirmation": True
        })
    if not items:
        raise ValueError("没有可处理的问题描述")
    items.sort(key=lambda x: (-x["priority_score"], x["target_date"], x["id"]))
    for i, item in enumerate(items, 1):
        item["rank"] = i
    return {
        "schema_version": "1.0", "generated_on": today.isoformat(),
        "summary": {"total": len(items), "critical": sum(x["severity"] == "critical" for x in items),
                    "high": sum(x["severity"] == "high" for x in items),
                    "medium": sum(x["severity"] == "medium" for x in items),
                    "low": sum(x["severity"] == "low" for x in items)},
        "register": items,
        "review_queue": ["确认问题事实与影响范围", "确认责任角色和目标日期", "确认整改动作后再写入教务/质量系统"],
        "side_effects": {"executed": False, "message": "仅生成预览，未发送通知、未写入外部系统"}
    }

def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(build_register(payload), ensure_ascii=False, indent=2))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": {"code": "INVALID_INPUT", "message": str(exc)}, "side_effects": {"executed": False}}, ensure_ascii=False, indent=2))
        sys.exit(2)

if __name__ == "__main__":
    main()
