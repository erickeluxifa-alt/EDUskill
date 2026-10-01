#!/usr/bin/env python3
import argparse
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SLOT_RE = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)-[1-9][0-9]*$")
MAX_ABSENCES = 300
MAX_TEACHERS = 500
MAX_SLOTS = 1000
DEFAULT_RULES = {"allow_cross_subject": False, "max_candidates": 3}


def nonnegative_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def demo_data():
    return {
        "date_range": "2026-09-14~2026-09-18",
        "absences": [
            {"teacher_id": "T01", "course_id": "C01", "course_name": "高等数学", "class_id": "CL1", "subject": "数学", "slot": "Mon-1", "room_id": "R1", "students": 42},
            {"teacher_id": "T03", "course_id": "C02", "course_name": "大学物理实验", "class_id": "CL2", "subject": "物理", "slot": "Tue-2", "room_id": "LAB1", "students": 28},
        ],
        "teachers": [
            {"id": "T01", "name": "教师甲", "subjects": ["数学"], "available_slots": ["Wed-2"], "max_daily_load": 4, "existing_load": {"Wed": 1}},
            {"id": "T02", "name": "教师乙", "subjects": ["数学"], "available_slots": ["Mon-1", "Wed-2"], "max_daily_load": 4, "existing_load": {"Mon": 2, "Wed": 2}},
            {"id": "T03", "name": "教师丙", "subjects": ["物理"], "available_slots": [], "max_daily_load": 3, "existing_load": {"Tue": 2}},
            {"id": "T04", "name": "教师丁", "subjects": ["物理"], "available_slots": ["Thu-3"], "max_daily_load": 3, "existing_load": {"Thu": 1}},
        ],
        "rooms": [
            {"id": "R1", "capacity": 50, "available_slots": ["Mon-1", "Wed-2"]},
            {"id": "R2", "capacity": 60, "available_slots": ["Wed-2", "Thu-3"]},
            {"id": "LAB1", "capacity": 30, "available_slots": ["Tue-2", "Thu-3"]},
        ],
        "class_busy": {"CL1": ["Tue-1"], "CL2": ["Wed-2"]},
        "makeup_slots": ["Wed-2", "Thu-3"],
        "rules": DEFAULT_RULES,
    }


def issue(level, path, message):
    return {"level": level, "path": path, "message": message}


def valid_slot(value):
    return isinstance(value, str) and SLOT_RE.fullmatch(value) is not None

def normalize(data):
    if not isinstance(data, dict):
        raise ValueError("输入顶层必须是 JSON 对象")
    collections = {"absences": list, "teachers": list, "rooms": list, "makeup_slots": list, "class_busy": dict, "rules": dict}
    for key, expected in collections.items():
        if key not in data:
            if key in ("absences", "teachers"):
                raise ValueError(f"缺少数组字段 {key}")
            continue
        if not isinstance(data[key], expected):
            raise ValueError(f"字段 {key} 必须是{'数组' if expected is list else '对象'}")
    if len(data["absences"]) > MAX_ABSENCES or len(data["teachers"]) > MAX_TEACHERS:
        raise ValueError(f"输入规模超限：缺勤课程最多 {MAX_ABSENCES}，教师最多 {MAX_TEACHERS}")
    data = dict(data)
    data.setdefault("rooms", [])
    data.setdefault("class_busy", {})
    data.setdefault("makeup_slots", [])
    if len(data["makeup_slots"]) > MAX_SLOTS:
        raise ValueError(f"补课时段最多 {MAX_SLOTS} 个")
    for class_id, slots in data["class_busy"].items():
        if not isinstance(slots, list) or any(not valid_slot(slot) for slot in slots):
            raise ValueError(f"class_busy.{class_id} 必须是 Mon-1 格式数组")
    if any(not valid_slot(slot) for slot in data["makeup_slots"]):
        raise ValueError("makeup_slots 必须是 Mon-1 格式数组")
    rules = dict(DEFAULT_RULES)
    given_rules = data.get("rules", {})
    if "allow_cross_subject" in given_rules and not isinstance(given_rules["allow_cross_subject"], bool):
        raise ValueError("rules.allow_cross_subject 必须是布尔值")
    if "max_candidates" in given_rules and (isinstance(given_rules["max_candidates"], bool) or not isinstance(given_rules["max_candidates"], int) or not 1 <= given_rules["max_candidates"] <= 20):
        raise ValueError("rules.max_candidates 必须是 1~20 的整数")
    rules.update(given_rules)
    data["rules"] = rules
    if not data["absences"]:
        data["empty_warning"] = True
    return data


def validate(data):
    issues, teachers, rooms, valid_absences = [], {}, {}, []
    for i, teacher in enumerate(data["teachers"]):
        path = f"teachers[{i}]"
        if not isinstance(teacher, dict) or not str(teacher.get("id", "")).strip():
            issues.append(issue("error", path, "教师必须包含非空 id")); continue
        tid = str(teacher["id"])
        if tid in teachers:
            issues.append(issue("error", path, f"教师 ID 重复：{tid}")); continue
        subjects = teacher.get("subjects", [])
        slots = teacher.get("available_slots", [])
        load = teacher.get("existing_load", {})
        maximum = teacher.get("max_daily_load", 99)
        if not isinstance(subjects, list) or any(not isinstance(value, str) or not value.strip() for value in subjects):
            issues.append(issue("error", path + ".subjects", "subjects 必须是非空字符串数组")); continue
        if not isinstance(slots, list) or any(not valid_slot(slot) for slot in slots):
            issues.append(issue("error", path + ".available_slots", "可用时段必须是 Mon-1 格式数组")); continue
        if not isinstance(load, dict) or any(day not in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun") or not nonnegative_number(value) for day, value in load.items()):
            issues.append(issue("error", path + ".existing_load", "existing_load 必须是星期到非负负荷的映射")); continue
        if not nonnegative_number(maximum):
            issues.append(issue("error", path + ".max_daily_load", "max_daily_load 必须为非负数")); continue
        teachers[tid] = {**teacher, "subjects": set(subjects), "available_slots": set(slots), "existing_load": load, "max_daily_load": maximum}
    for i, room in enumerate(data["rooms"]):
        path = f"rooms[{i}]"
        if not isinstance(room, dict) or not str(room.get("id", "")).strip():
            issues.append(issue("error", path, "教室必须包含非空 id")); continue
        rid = str(room["id"])
        if rid in rooms:
            issues.append(issue("error", path, f"教室 ID 重复：{rid}")); continue
        capacity = room.get("capacity", 0)
        if not nonnegative_number(capacity):
            issues.append(issue("error", path, "capacity 必须为非负数")); continue
        slots = room.get("available_slots", [])
        if not isinstance(slots, list) or any(not valid_slot(slot) for slot in slots):
            issues.append(issue("error", path + ".available_slots", "可用时段必须是 Mon-1 格式数组")); continue
        rooms[rid] = {**room, "available_slots": set(slots)}
    seen = set()
    for i, absence in enumerate(data["absences"]):
        path = f"absences[{i}]"
        if not isinstance(absence, dict):
            issues.append(issue("error", path, "缺勤记录必须是对象")); continue
        required = ["teacher_id", "course_id", "class_id", "subject", "slot"]
        missing = [key for key in required if not str(absence.get(key, "")).strip()]
        if missing:
            issues.append(issue("error", path, "缺少字段：" + ", ".join(missing))); continue
        if not valid_slot(absence["slot"]):
            issues.append(issue("error", path + ".slot", "时段格式须为 Mon-1")); continue
        students = absence.get("students", 0)
        if isinstance(students, bool) or not isinstance(students, int) or students < 0:
            issues.append(issue("error", path + ".students", "students 必须为非负整数")); continue
        key = (str(absence["course_id"]), str(absence["slot"]))
        if key in seen:
            issues.append(issue("error", path, "课程与时段重复，已跳过")); continue
        seen.add(key); valid_absences.append(absence)
        if str(absence["teacher_id"]) not in teachers:
            issues.append(issue("warning", path + ".teacher_id", "缺勤教师未出现在教师清单中"))
    return teachers, rooms, valid_absences, issues

def teacher_candidates(absence, teachers, rules, slot=None, include_original=False):
    candidates = []
    slot = slot or absence["slot"]
    day = slot.split("-", 1)[0]
    for tid, teacher in teachers.items():
        if not include_original and tid == str(absence["teacher_id"]):
            continue
        if slot not in teacher["available_slots"]:
            continue
        matched = absence["subject"] in teacher["subjects"]
        if not matched and not rules["allow_cross_subject"]:
            continue
        current = teacher["existing_load"].get(day, 0)
        maximum = teacher["max_daily_load"]
        if current + 1 > maximum:
            continue
        candidates.append({
            "teacher_id": tid,
            "teacher_name": str(teacher.get("name", tid)),
            "cross_subject": not matched,
            "current_daily_load": current,
            "remaining_after_assignment": maximum - current - 1,
            "reason": "同学科且时段可用" if matched else "跨学科候选，必须人工核验资质",
        })
    candidates.sort(key=lambda x: (x["cross_subject"], -x["remaining_after_assignment"], x["current_daily_load"], x["teacher_id"]))
    return candidates[:rules["max_candidates"]]


def reschedule_candidates(absence, teachers, rooms, data):
    result = []
    busy = set(data["class_busy"].get(str(absence["class_id"]), []))
    for slot in data["makeup_slots"]:
        if slot in busy:
            continue
        instructor_candidates = teacher_candidates(absence, teachers, data["rules"], slot, include_original=True)
        if not instructor_candidates:
            continue
        suitable_rooms = ({"room_id": rid, "capacity": room["capacity"]} for rid, room in rooms.items()
                          if room["capacity"] >= absence.get("students", 0) and slot in room["available_slots"])
        room = min(suitable_rooms, key=lambda x: (x["capacity"], x["room_id"]), default=None)
        if room is None:
            continue
        instructor = instructor_candidates[0]
        result.append({"slot": slot, "room": room, "teacher": instructor,
                       "reason": "班级、教室与授课教师均可用"})
    return result[:data["rules"]["max_candidates"]]


def build_report(data):
    data = normalize(data)
    teachers, rooms, absences, issues = validate(data)
    if data.get("empty_warning"):
        issues.append(issue("warning", "absences", "缺勤列表为空，未生成覆盖方案"))
    plans = []
    for absence in absences:
        candidates = teacher_candidates(absence, teachers, data["rules"])
        base = {"course_id": str(absence["course_id"]), "course_name": str(absence.get("course_name", absence["course_id"])),
                "class_id": str(absence["class_id"]), "subject": str(absence["subject"]), "original_slot": str(absence["slot"])}
        if candidates:
            plans.append({**base, "status": "substitute", "recommended": candidates[0], "candidates": candidates,
                          "reason": "找到可在原时段授课的候选教师"})
            continue
        alternatives = reschedule_candidates(absence, teachers, rooms, data)
        if alternatives:
            plans.append({**base, "status": "reschedule", "recommended": alternatives[0], "candidates": alternatives,
                          "reason": "原时段无可用代课教师，建议调课"})
        else:
            plans.append({**base, "status": "uncovered", "recommended": None, "candidates": [],
                          "reason": "没有满足资质、忙闲、负荷、班级与教室约束的方案"})
    conflicts = combination_conflicts(plans)
    counts = Counter(p["status"] for p in plans)
    return {"status": "needs_review" if any(i["level"] == "error" for i in issues) or conflicts or counts["uncovered"] else "ok",
            "date_range": data.get("date_range", "未提供"),
            "summary": {"total": len(plans), "substitute": counts["substitute"], "reschedule": counts["reschedule"], "uncovered": counts["uncovered"], "issues": len(issues), "conflicts": len(conflicts)},
            "plans": plans, "conflicts": conflicts, "issues": issues,
            "assumptions": ["未声明可用时段的教师视为不可用", "候选方案不会自动占用资源", "跨学科代课默认关闭"]}

def combination_conflicts(plans):
    allocations = defaultdict(list)
    for plan in plans:
        rec = plan["recommended"]
        if plan["status"] == "substitute":
            slot = plan["original_slot"]
            allocations[("teacher", rec["teacher_id"], slot)].append(plan["course_id"])
        elif plan["status"] == "reschedule":
            slot = rec["slot"]
            allocations[("teacher", rec["teacher"]["teacher_id"], slot)].append(plan["course_id"])
            allocations[("room", rec["room"]["room_id"], slot)].append(plan["course_id"])
            allocations[("class", plan["class_id"], slot)].append(plan["course_id"])
    labels = {"teacher": "教师", "room": "教室", "class": "班级"}
    return [{"type": f"{kind}_double_booking", "resource_id": resource_id, "slot": slot,
             "course_ids": courses, "message": f"多个独立推荐占用同一{labels[kind]}同一时段，必须人工选择"}
            for (kind, resource_id, slot), courses in allocations.items() if len(courses) > 1]


def esc(value):
    return html.escape(str(value).replace("\r", " ").replace("\n", " "), quote=False).replace("|", "\\|")


def render_markdown(report):
    s = report["summary"]
    lines = ["# 教师缺勤代课与调课方案", "", f"- 覆盖范围：{esc(report['date_range'])}", f"- 状态：`{report['status']}`",
             f"- 受影响课程：{s['total']}；代课：{s['substitute']}；调课：{s['reschedule']}；未覆盖：{s['uncovered']}", "",
             "## 方案预览", "", "| 课程 | 班级 | 原时段 | 建议 | 理由 |", "|---|---|---|---|---|"]
    for plan in report["plans"]:
        rec = plan["recommended"]
        if plan["status"] == "substitute":
            action = f"代课：{rec['teacher_name']}（{rec['teacher_id']}）"
        elif plan["status"] == "reschedule":
            action = f"调至 {rec['slot']} / {rec['room']['room_id']} / {rec['teacher']['teacher_name']}（{rec['teacher']['teacher_id']}）"
        else:
            action = "未覆盖"
        lines.append(f"| {esc(plan['course_name'])} | {esc(plan['class_id'])} | {esc(plan['original_slot'])} | {esc(action)} | {esc(plan['reason'])} |")
    lines += ["", "## 组合冲突", ""]
    lines += [f"- {esc(c['message'])}：资源 {esc(c['resource_id'])} / {esc(c['slot'])} / 课程 {esc(', '.join(c['course_ids']))}" for c in report["conflicts"]] or ["- 无。"]
    lines += ["", "## 数据问题", ""]
    lines += [f"- **{i['level']}** `{esc(i['path'])}`：{esc(i['message'])}" for i in report["issues"]] or ["- 无。"]
    lines += ["", "## 人工确认", "", "- [ ] 核验代课教师资质、意愿与最新课表。", "- [ ] 核验教师工作量与本校代课规则。",
              "- [ ] 核验教室开放状态、容量与设备。", "- [ ] 处理组合冲突后再通知师生。", "- [ ] 本报告仅为预览，未写回任何系统。"]
    return "\n".join(lines) + "\n"


def load_input(args):
    if args.demo:
        return demo_data()
    if not args.input:
        raise ValueError("请使用 --input FILE、--input - 或 --demo")
    if args.input == "-":
        return json.load(sys.stdin)
    with open(args.input, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    parser = argparse.ArgumentParser(description="生成教师缺勤代课与调课候选方案")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input")
    source.add_argument("--demo", action="store_true")
    parser.add_argument("--out-dir", default="output")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        report = build_report(load_input(args))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "coverage_plan.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "coverage_plan.md").write_text(render_markdown(report), encoding="utf-8")
        print(f"已生成：{out / 'coverage_plan.json'}")
        print(f"已生成：{out / 'coverage_plan.md'}")
    return 2 if args.strict and report["status"] != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
