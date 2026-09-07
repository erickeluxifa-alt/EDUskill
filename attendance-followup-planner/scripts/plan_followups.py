#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import json
from pathlib import Path

VALID = {"present", "late", "absent", "excused"}

def parse_date(value):
    return dt.date.fromisoformat(value)

def main():
    parser = argparse.ArgumentParser(description="Plan attendance follow-ups from local JSON")
    parser.add_argument("input")
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    errors = []
    if not isinstance(records, list):
        result = {"status": "error", "errors": ["records 必须是数组"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    rules = payload.get("rules", {}) if isinstance(payload, dict) else {}
    absence_threshold = rules.get("absence_threshold", 2)
    consecutive_threshold = rules.get("consecutive_threshold", 2)
    late_weight = rules.get("late_weight", 0.5)
    try:
        absence_threshold = float(absence_threshold)
        consecutive_threshold = int(consecutive_threshold)
        late_weight = float(late_weight)
        if absence_threshold <= 0 or consecutive_threshold <= 0 or late_weight < 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("rules 中的阈值必须为正数，late_weight 不能为负数")
        absence_threshold, consecutive_threshold, late_weight = 2.0, 2, 0.5

    students = {}
    seen = set()
    duplicate_count = 0
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            errors.append(f"第 {index} 条记录不是对象")
            continue
        sid = str(record.get("student_id", "")).strip()
        name = str(record.get("student_name", "")).strip()
        date_value = str(record.get("date", "")).strip()
        status = str(record.get("status", "")).strip().lower()
        if not sid or not name:
            errors.append(f"第 {index} 条记录缺少 student_id 或 student_name")
            continue
        try:
            date_value_obj = parse_date(date_value)
        except ValueError:
            errors.append(f"第 {index} 条记录日期无效：{html.escape(date_value)[:40]}")
            continue
        if status not in VALID:
            errors.append(f"第 {index} 条记录状态不支持：{html.escape(status)[:40]}")
            continue
        key = (sid, date_value)
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        student = students.setdefault(sid, {"student_id": sid, "student_name": name, "events": []})
        if student["student_name"] != name:
            errors.append(f"学生 {html.escape(sid)[:40]} 出现多个姓名，采用首条姓名")
        student["events"].append({"date": date_value_obj, "status": status})

    output_students = []
    for student in students.values():
        events = sorted(student["events"], key=lambda item: item["date"])
        absent_count = sum(item["status"] == "absent" for item in events)
        late_count = sum(item["status"] == "late" for item in events)
        score = absent_count + late_count * late_weight
        absent_dates = [item["date"] for item in events if item["status"] == "absent"]
        longest = current = 0
        previous = None
        for item in events:
            if item["status"] == "absent" and previous is not None and (item["date"] - previous).days == 1:
                current += 1
            elif item["status"] == "absent":
                current = 1
            else:
                current = 0
            longest = max(longest, current)
            if item["status"] == "absent":
                previous = item["date"]
            else:
                previous = None
        if absent_count >= absence_threshold or longest >= consecutive_threshold:
            level = "priority"
            reason = "缺勤达到阈值或存在连续缺勤"
        elif score > 0 or late_count >= 2:
            level = "watch"
            reason = "存在缺勤或迟到累积，建议先核实"
        else:
            level = "normal"
            reason = "当前输入中未发现缺勤跟进信号"
        output_students.append({
            "student_id": student["student_id"],
            "student_name": student["student_name"],
            "absence_count": absent_count,
            "late_count": late_count,
            "absence_score": round(score, 2),
            "longest_consecutive_absence": longest,
            "level": level,
            "evidence": reason,
            "communication_preview": (f"想和你确认一下近期出勤情况（记录显示缺勤 {absent_count} 次、迟到 {late_count} 次），"
                                      "是否有需要学校协助的情况？这是一份人工核实预览，请确认事实和沟通方式后再联系。"),
        })
    output_students.sort(key=lambda item: ({"priority": 0, "watch": 1, "normal": 2}[item["level"]], -item["absence_score"], item["student_id"]))
    result = {
        "status": "ok" if not errors else "partial",
        "course": payload.get("course", "未填写"),
        "class_name": payload.get("class_name", "未填写"),
        "rules": {"absence_threshold": absence_threshold, "consecutive_threshold": consecutive_threshold, "late_weight": late_weight},
        "summary": {"student_count": len(output_students), "priority_count": sum(x["level"] == "priority" for x in output_students), "watch_count": sum(x["level"] == "watch" for x in output_students), "normal_count": sum(x["level"] == "normal" for x in output_students)},
        "students": output_students,
        "data_quality": {"valid_record_count": len(seen), "duplicate_record_count": duplicate_count, "errors": errors},
        "confirmation": ["确认请假/补签等制度口径", "确认学生隐私和联系渠道", "确认是否需要辅导员或教务人工升级"],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "followup_plan.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = [f"# 考勤跟进计划：{html.escape(str(result['class_name']))}", "", f"课程：{html.escape(str(result['course']))}", f"学生数：{len(output_students)}，优先跟进：{result['summary']['priority_count']}，观察：{result['summary']['watch_count']}", "", "## 跟进队列", ""]
    for item in output_students:
        lines.append(f"### {item['level']}｜{html.escape(item['student_id'])} {html.escape(item['student_name'])}")
        lines.append(f"- 证据：缺勤 {item['absence_count']} 次，迟到 {item['late_count']} 次，连续缺勤最长 {item['longest_consecutive_absence']} 次；{html.escape(item['evidence'])}")
        if item['level'] != 'normal':
            lines.append(f"- 沟通预览：{html.escape(item['communication_preview'])}")
    lines += ["", "## 数据质量", f"- 有效记录：{len(seen)}；重复记录：{duplicate_count}；错误：{len(errors)}"]
    if errors:
        lines += ["", "### 可修复问题"] + [f"- {error}" for error in errors]
    lines += ["", "## 人工确认", *[f"- {item}" for item in result["confirmation"]], "", "本报告仅用于跟进排序和人工预览，不自动发送、不修改考勤、不作纪律或心理风险结论。"]
    (out_dir / "followup_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result if args.json else {"status": result["status"], "summary": result["summary"], "files": [str(out_dir / "followup_plan.json"), str(out_dir / "followup_plan.md")]}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
