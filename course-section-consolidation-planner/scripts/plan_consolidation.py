#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

REQUIRED = ("id", "course_code", "enrollment", "capacity", "timeslots", "progress_week", "language", "campus", "teacher_id", "teacher_load")


def load_data(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("input root must be an object")
    for key in ("sections", "students", "candidates"):
        if key not in data or not isinstance(data[key], list):
            raise ValueError(f"{key} must be an array")
    return data


def validate(data):
    issues, sections, student_ids = [], {}, set()
    for index, item in enumerate(data["sections"]):
        missing = [key for key in REQUIRED if key not in item]
        if missing:
            issues.append(f"section[{index}] missing: {', '.join(missing)}")
            continue
        sid = str(item["id"])
        if sid in sections:
            issues.append(f"duplicate section: {sid}")
        if not isinstance(item["capacity"], int) or item["capacity"] <= 0:
            issues.append(f"section {sid} capacity must be positive integer")
        if not isinstance(item["enrollment"], int) or item["enrollment"] < 0:
            issues.append(f"section {sid} enrollment must be non-negative integer")
        sections[sid] = item
    for index, student in enumerate(data["students"]):
        if not all(key in student for key in ("id", "section_id", "external_timeslots")):
            issues.append(f"student[{index}] missing required field")
            continue
        student_id = str(student["id"])
        if student_id in student_ids:
            issues.append(f"duplicate student: {student_id}")
        student_ids.add(student_id)
        if str(student["section_id"]) not in sections:
            issues.append(f"student {student_id} references unknown section")
    return sections, issues


def evaluate(candidate, sections, students, policy):
    cid = str(candidate.get("id", "unnamed"))
    ids = [str(value) for value in candidate.get("section_ids", [])]
    target_id = str(candidate.get("target_section_id", ""))
    blockers, risks = [], []
    unknown = [sid for sid in ids if sid not in sections]
    if len(ids) < 2:
        blockers.append("candidate must include at least two sections")
    if unknown:
        blockers.append("unknown sections: " + ", ".join(unknown))
    if target_id not in ids:
        blockers.append("target section is not in candidate group")
    valid = [sections[sid] for sid in ids if sid in sections]
    if not valid or target_id not in sections:
        return result(cid, "blocked", 0, blockers, risks, 0, 0, 0, [])
    target = sections[target_id]
    courses = {str(item["course_code"]) for item in valid}
    languages = {str(item["language"]) for item in valid}
    campuses = {str(item["campus"]) for item in valid}
    progress = [int(item["progress_week"]) for item in valid]
    merged = sum(int(item["enrollment"]) for item in valid)
    capacity = int(candidate.get("room_capacity", target["capacity"]))
    if len(courses) > 1:
        blockers.append("course codes differ")
    if len(languages) > 1:
        blockers.append("teaching languages differ")
    if len(campuses) > 1 and not policy.get("allow_cross_campus", False):
        blockers.append("campuses differ")
    elif len(campuses) > 1:
        risks.append("cross-campus consolidation requires travel review")
    if max(progress) - min(progress) > int(policy.get("max_progress_gap", 1)):
        blockers.append("teaching progress gap exceeds policy")
    if capacity <= 0:
        blockers.append("effective capacity must be positive")
    elif merged > capacity:
        blockers.append(f"capacity exceeded by {merged - capacity}")
    target_slots = set(target.get("timeslots", []))
    affected, conflicts = [], []
    for student in students:
        if str(student.get("section_id")) in ids and str(student.get("section_id")) != target_id:
            sid = str(student.get("id"))
            affected.append(sid)
            if target_slots.intersection(set(student.get("external_timeslots", []))):
                conflicts.append(sid)
    if conflicts:
        blockers.append(f"{len(conflicts)} students have target-timeslot conflicts")
    teacher_count = len({str(item["teacher_id"]) for item in valid})
    utilization = round(merged / capacity, 4) if capacity > 0 else 0
    score = 100
    score -= min(20, len(conflicts) * 5)
    score -= min(15, (max(progress) - min(progress)) * 8)
    score -= 8 if teacher_count > 1 else 0
    score -= 8 if target.get("room_id") and candidate.get("room_capacity") else 0
    score -= 12 if utilization > 0.9 else (5 if utilization > 0.8 else 0)
    score = max(0, score)
    status = "blocked" if blockers else ("review" if score < int(policy.get("review_score_below", 75)) else "recommended")
    confirms = ["verify roster snapshot freshness", "confirm room and timetable", "confirm teacher workload", "review student impact before SIS action"]
    return result(cid, status, score, blockers, risks, merged, capacity, utilization, affected, confirms)


def result(cid, status, score, blockers, risks, merged, capacity, utilization, affected, confirms=None):
    return {"candidate_id": cid, "status": status, "score": score, "merged_enrollment": merged,
            "effective_capacity": capacity, "utilization": utilization, "blockers": blockers,
            "risks": risks, "affected_students": affected, "confirmation_items": confirms or []}


def render(payload):
    lines = ["# 教学班合并方案评估报告", "", f"候选方案：{payload['summary']['total']}；推荐：{payload['summary']['recommended']}；复核：{payload['summary']['review']}；阻断：{payload['summary']['blocked']}。", ""]
    if payload["data_issues"]:
        lines += ["## 数据问题", *[f"- {item}" for item in payload["data_issues"]], ""]
    for item in payload["results"]:
        lines += [f"## {item['candidate_id']} — {item['status']}", f"评分：{item['score']}/100；合并人数：{item['merged_enrollment']}；有效容量：{item['effective_capacity']}；影响学生：{len(item['affected_students'])}。"]
        lines += ["阻断项：" + ("；".join(item["blockers"]) or "无"), "风险：" + ("；".join(item["risks"]) or "无"), "确认清单：" + "；".join(item["confirmation_items"]), ""]
    lines += ["本报告仅供人工审核，不自动修改教务系统或发送通知。"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    data = load_data(args.input)
    sections, issues = validate(data)
    results = [evaluate(item, sections, data["students"], data.get("policy", {})) for item in data["candidates"]]
    results.sort(key=lambda item: (item["status"] == "blocked", -item["score"], item["candidate_id"]))
    summary = {"total": len(results), "recommended": sum(x["status"] == "recommended" for x in results), "review": sum(x["status"] == "review" for x in results), "blocked": sum(x["status"] == "blocked" for x in results)}
    payload = {"summary": summary, "results": results, "data_issues": issues}
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "consolidation_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "consolidation_report.md").write_text(render(payload) + "\n", encoding="utf-8")
    return 2 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
