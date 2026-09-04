#!/usr/bin/env python3
import argparse, json, re, sys

WEIGHTS = {"speak": .30, "question": .20, "submission": .25, "collaboration": .25}
ALIASES = {"speak": ("speak", "speaking", "participation"), "question": ("question", "questions", "ask"), "submission": ("submission", "submit", "exit_ticket"), "collaboration": ("collaboration", "collaborate", "peer_work")}

def clean(value, limit=120):
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]

def evidence(row, key):
    for alias in ALIASES[key]:
        if alias in row:
            value = row[alias]
            if isinstance(value, bool): return value
            if isinstance(value, (int, float)): return value > 0
            return clean(value).lower() not in ("", "0", "false", "no", "none", "无")
    return None

def diagnose(payload):
    if not isinstance(payload, dict): return {"error": "INVALID_INPUT", "message": "输入必须是 JSON 对象"}
    rows = payload.get("sessions", payload.get("students"))
    if not isinstance(rows, list) or not rows: return {"error": "INVALID_INPUT", "message": "需要非空 sessions/students 数组"}
    result, counts = [], {"present": 0, "absent": 0, "late": 0, "unknown": 0, "sufficient": 0, "limited": 0, "needs_opportunity": 0, "insufficient_data": 0}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict): continue
        name = clean(row.get("name") or row.get("student_name"))
        sid = clean(row.get("student_id") or row.get("sid") or row.get("id"))
        if not name or not sid: continue
        attendance = clean(row.get("attendance", "unknown")).lower()
        if attendance not in counts: attendance = "unknown"
        counts[attendance] += 1
        signals = {key: evidence(row, key) for key in WEIGHTS}
        known = [v for v in signals.values() if v is not None]
        if attendance == "absent": tier, score, gaps = "absent_not_rated", None, []
        elif not known: tier, score, gaps = "insufficient_data", None, list(WEIGHTS)
        else:
            denominator = sum(WEIGHTS[k] for k in WEIGHTS if signals[k] is not None)
            score = round(sum(WEIGHTS[k] * int(signals[k] is True) for k in WEIGHTS) / denominator, 3)
            gaps = [k for k, value in signals.items() if value is not True]
            tier = "sufficient" if score >= .75 else "limited" if score >= .40 else "needs_opportunity"
        if tier in counts: counts[tier] += 1
        advice = []
        if tier == "needs_opportunity": advice = ["安排一次低风险冷启动提问", "提供匿名随堂提交入口"]
        elif tier == "limited": advice = ["轮换一次同伴核对或小组汇报机会"]
        elif tier == "insufficient_data": advice = ["下一节课补采至少一种互动证据"]
        if attendance == "late": advice.append("核对迟到时间与实际参与时段")
        result.append({"id": index, "student_id": sid, "name": name, "attendance": attendance, "score": score, "tier": tier, "evidence_gaps": gaps, "suggestions": advice, "note": clean(row.get("note"))})
    if not result: return {"error": "INVALID_INPUT", "message": "没有包含 name 与 student_id 的有效记录"}
    actionable = [r for r in result if r["tier"] in ("needs_opportunity", "limited", "insufficient_data")]
    return {"summary": {"course": clean(payload.get("course")), "class_name": clean(payload.get("class_name")), "student_count": len(result), "attendance": {k: counts[k] for k in ("present", "absent", "late", "unknown")}, "tiers": {k: counts[k] for k in ("sufficient", "limited", "needs_opportunity", "insufficient_data")}, "actionable_count": len(actionable)}, "students": result, "intervention_plan": ["先用匿名/低风险方式扩大证据覆盖", "按小组轮换发言与同伴核对，避免固定点名", "连续 3 次课观察后再判断趋势"], "review_queue": [{"student_id": r["student_id"], "name": r["name"], "proposed_action": r["suggestions"][0] if r["suggestions"] else "补采证据", "status": "待教师确认"} for r in actionable], "side_effects": {"writes": False, "notifications": False, "message": "结果仅为形成性教学预览，不修改成绩或学生档案"}}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--pretty", action="store_true"); args = parser.parse_args()
    try: payload = json.load(sys.stdin); output = diagnose(payload)
    except (json.JSONDecodeError, OSError) as exc: output = {"error": "INVALID_INPUT", "message": clean(exc)}
    print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
    return 2 if "error" in output else 0

if __name__ == "__main__": sys.exit(main())
