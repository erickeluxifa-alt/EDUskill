#!/usr/bin/env python3
"""教师教学工作量核算与超限校验（纯离线、无第三方依赖）。"""
import argparse
import html
import json
import sys
from pathlib import Path

MAX_TEACHERS = 500
MAX_COURSES = 3000
MAX_COURSE_HOURS = 2000
MAX_SUPERVISION_COUNT = 500

DEFAULT_RULES = {
    "standard_workload": 320,
    "max_workload": 480,
    "min_workload": 160,
    "high_ratio": 1.2,
    "course_type_coefficient": {
        "理论": 1.0,
        "实验": 0.8,
        "实践": 0.6,
        "体育": 0.9,
        "在线": 0.7,
    },
    "class_size_tiers": [
        {"max_students": 60, "coefficient": 1.0},
        {"max_students": 90, "coefficient": 1.1},
        {"max_students": 150, "coefficient": 1.2},
    ],
    "oversize_coefficient": 1.3,
    "merged_class_extra": 0.05,
    "new_course_coefficient": 1.15,
    "supervision_hours": {
        "thesis": 18,
        "internship": 6,
        "competition": 10,
        "graduate": 30,
    },
}

SUPERVISION_LABEL = {
    "thesis": "毕业论文/设计指导",
    "internship": "实习实践指导",
    "competition": "学科竞赛指导",
    "graduate": "研究生指导",
}

STATUS_LABEL = {
    "over_limit": "超出上限",
    "high": "偏高关注",
    "normal": "正常",
    "low": "低于下限",
}


def text(value, limit=120):
    return str(value).replace("|", "/").replace("\n", " ")[:limit]


def num(value):
    """仅接受非 bool 的 int/float，返回 float 或 None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return float(value)


def r2(value):
    return round(value + 0.0, 2)


def merge_rules(custom, issues):
    rules = json.loads(json.dumps(DEFAULT_RULES))
    if custom is None:
        return rules
    if not isinstance(custom, dict):
        issues.append({"level": "warning", "target": "rules", "message": "rules 不是对象，已全部改用默认规则"})
        return rules
    for key, value in custom.items():
        if key not in rules:
            issues.append({"level": "warning", "target": f"rules.{text(key)}", "message": "未知规则项，已忽略"})
            continue
        if isinstance(rules[key], dict) and isinstance(value, dict):
            rules[key].update(value)
        elif isinstance(rules[key], list) and isinstance(value, list):
            rules[key] = value
        elif num(value) is not None and not isinstance(rules[key], (dict, list)):
            rules[key] = num(value)
        else:
            issues.append({"level": "warning", "target": f"rules.{text(key)}", "message": "类型不匹配，已改用默认值"})
    return rules


def check_rules(rules, issues):
    low = num(rules.get("min_workload")) or 0.0
    std = num(rules.get("standard_workload")) or 0.0
    high = num(rules.get("max_workload")) or 0.0
    if not (0 <= low <= std <= high):
        issues.append({
            "level": "warning",
            "target": "rules",
            "message": f"阈值未满足 min<=standard<=max（{low}/{std}/{high}），已改用默认阈值",
        })
        rules["min_workload"] = DEFAULT_RULES["min_workload"]
        rules["standard_workload"] = DEFAULT_RULES["standard_workload"]
        rules["max_workload"] = DEFAULT_RULES["max_workload"]
    tiers = []
    for tier in rules.get("class_size_tiers") or []:
        if not isinstance(tier, dict):
            continue
        cap, coef = num(tier.get("max_students")), num(tier.get("coefficient"))
        if cap is None or coef is None or cap <= 0 or coef <= 0:
            issues.append({"level": "warning", "target": "rules.class_size_tiers", "message": f"档位非法已忽略：{text(tier)}"})
            continue
        tiers.append({"max_students": cap, "coefficient": coef})
    tiers.sort(key=lambda item: item["max_students"])
    rules["class_size_tiers"] = tiers or DEFAULT_RULES["class_size_tiers"]
    return rules


def size_coefficient(students, rules):
    """按人数分档返回（系数, 说明）。人数缺失时按 1.0 处理。"""
    if students is None:
        return 1.0, "人数缺失，按 1.0 计"
    for tier in rules["class_size_tiers"]:
        if students <= tier["max_students"]:
            return tier["coefficient"], f"人数<= {int(tier['max_students'])} 档"
    coef = num(rules.get("oversize_coefficient")) or 1.0
    return coef, "超出最大档，按超大班系数计"


def load_teachers(data, issues):
    raw = data.get("teachers")
    if not isinstance(raw, list) or not raw:
        return None
    if len(raw) > MAX_TEACHERS:
        issues.append({"level": "error", "target": "teachers", "message": f"教师数不能超过 {MAX_TEACHERS}"})
        return None
    teachers = {}
    for item in raw:
        tid = item.get("id") if isinstance(item, dict) else None
        tid = tid.strip() if isinstance(tid, str) else ""
        if not tid:
            issues.append({"level": "error", "target": "teachers", "message": f"教师 id 缺失：{text(item)}"})
            continue
        if tid in teachers:
            issues.append({"level": "error", "target": tid, "message": "教师 id 重复，仅保留首条"})
            continue
        teachers[tid] = {
            "teacher_id": tid,
            "name": text(item.get("name", "未命名")),
            "title": text(item.get("title", "未填")),
            "department": text(item.get("department", "未分配院系")),
            "courses": [],
            "supervisions": [],
        }
    return teachers or None


def collect_courses(data, teachers, rules, issues):
    raw = data.get("courses")
    if raw is None:
        return
    if not isinstance(raw, list):
        issues.append({"level": "error", "target": "courses", "message": "courses 必须是列表"})
        return
    if len(raw) > MAX_COURSES:
        issues.append({"level": "error", "target": "courses", "message": f"课程条目不能超过 {MAX_COURSES}，已截断"})
        raw = raw[:MAX_COURSES]
    seen = set()
    for index, item in enumerate(raw):
        tag = f"courses[{index}]"
        if not isinstance(item, dict):
            issues.append({"level": "error", "target": tag, "message": "课程条目必须是对象"})
            continue
        tid = item.get("teacher_id")
        tid = tid.strip() if isinstance(tid, str) else ""
        if tid not in teachers:
            issues.append({"level": "error", "target": tag, "message": f"teacher_id 未在 teachers 中定义：{text(tid) or '空值'}"})
            continue
        hours = num(item.get("hours"))
        if hours is None or hours <= 0 or hours > MAX_COURSE_HOURS:
            issues.append({"level": "error", "target": tag, "message": f"hours 必须是 0~{MAX_COURSE_HOURS} 的正数，该课程未计入"})
            continue
        cid = text(item.get("course_id", f"C{index + 1}"), 60)
        key = (tid, cid)
        if key in seen:
            issues.append({"level": "warning", "target": tag, "message": f"同一教师出现重复课程号 {cid}，已按两次授课累加"})
        seen.add(key)
        ctype = text(item.get("type", "理论"), 20)
        type_coef = num(rules["course_type_coefficient"].get(ctype))
        if type_coef is None or type_coef <= 0:
            issues.append({"level": "warning", "target": tag, "message": f"课程类型 {ctype} 无系数配置，按 1.0 计"})
            type_coef = 1.0
        students = num(item.get("students"))
        if students is not None and students <= 0:
            issues.append({"level": "warning", "target": tag, "message": "students 非正数，按人数缺失处理"})
            students = None
        size_coef, size_note = size_coefficient(students, rules)
        merged = num(item.get("merged_classes")) or 1.0
        if merged < 1:
            issues.append({"level": "warning", "target": tag, "message": "merged_classes 小于 1，按 1 计"})
            merged = 1.0
        merged_coef = 1.0 + (num(rules.get("merged_class_extra")) or 0.0) * (merged - 1)
        new_coef = (num(rules.get("new_course_coefficient")) or 1.0) if item.get("is_new") is True else 1.0
        converted = hours * type_coef * size_coef * merged_coef * new_coef
        teachers[tid]["courses"].append({
            "course_id": cid,
            "name": text(item.get("name", "未命名课程"), 60),
            "type": ctype,
            "hours": r2(hours),
            "students": int(students) if students is not None else None,
            "merged_classes": int(merged),
            "is_new": item.get("is_new") is True,
            "coefficients": {
                "type": r2(type_coef),
                "class_size": r2(size_coef),
                "merged": r2(merged_coef),
                "new_course": r2(new_coef),
            },
            "size_note": size_note,
            "converted_hours": r2(converted),
        })


def collect_supervisions(data, teachers, rules, issues):
    raw = data.get("supervisions")
    if raw is None:
        return
    if not isinstance(raw, list):
        issues.append({"level": "error", "target": "supervisions", "message": "supervisions 必须是列表"})
        return
    for index, item in enumerate(raw):
        tag = f"supervisions[{index}]"
        if not isinstance(item, dict):
            issues.append({"level": "error", "target": tag, "message": "指导条目必须是对象"})
            continue
        tid = item.get("teacher_id")
        tid = tid.strip() if isinstance(tid, str) else ""
        if tid not in teachers:
            issues.append({"level": "error", "target": tag, "message": f"teacher_id 未在 teachers 中定义：{text(tid) or '空值'}"})
            continue
        kind = text(item.get("kind", ""), 40)
        hours_each = num(rules["supervision_hours"].get(kind))
        if hours_each is None or hours_each < 0:
            issues.append({"level": "error", "target": tag, "message": f"指导类型 {kind or '空值'} 无折算标准，该条未计入"})
            continue
        count = num(item.get("count"))
        if count is None or count < 0 or count > MAX_SUPERVISION_COUNT or count != int(count):
            issues.append({"level": "error", "target": tag, "message": f"count 必须是 0~{MAX_SUPERVISION_COUNT} 的整数，该条未计入"})
            continue
        teachers[tid]["supervisions"].append({
            "kind": kind,
            "label": SUPERVISION_LABEL.get(kind, kind),
            "count": int(count),
            "hours_each": r2(hours_each),
            "converted_hours": r2(hours_each * count),
        })


def classify(total, rules):
    if total > rules["max_workload"]:
        return "over_limit"
    if total >= rules["standard_workload"] * (num(rules.get("high_ratio")) or 1.2):
        return "high"
    if total < rules["min_workload"]:
        return "low"
    return "normal"


def calculate(data):
    issues = []
    if not isinstance(data, dict):
        return {"status": "data_error", "issues": [{"level": "error", "target": "root", "message": "输入顶层必须是 JSON 对象"}], "teachers": []}
    rules = check_rules(merge_rules(data.get("rules"), issues), issues)
    teachers = load_teachers(data, issues)
    if teachers is None:
        issues.append({"level": "error", "target": "teachers", "message": "teachers 必须是非空列表且至少含一条合法记录"})
        return {"status": "data_error", "issues": issues, "teachers": []}
    collect_courses(data, teachers, rules, issues)
    collect_supervisions(data, teachers, rules, issues)

    rows, counters = [], {"over_limit": 0, "high": 0, "normal": 0, "low": 0}
    for info in teachers.values():
        course_total = sum(item["converted_hours"] for item in info["courses"])
        sup_total = sum(item["converted_hours"] for item in info["supervisions"])
        total = course_total + sup_total
        state = classify(total, rules)
        counters[state] += 1
        if not info["courses"] and not info["supervisions"]:
            issues.append({"level": "warning", "target": info["teacher_id"], "message": "该教师没有任何课程或指导记录，工作量为 0，请确认是否漏报"})
        rows.append({
            **{k: info[k] for k in ("teacher_id", "name", "title", "department")},
            "course_workload": r2(course_total),
            "supervision_workload": r2(sup_total),
            "total_workload": r2(total),
            "ratio_to_standard": r2(total / rules["standard_workload"]) if rules["standard_workload"] else None,
            "status": state,
            "status_label": STATUS_LABEL[state],
            "courses": info["courses"],
            "supervisions": info["supervisions"],
        })
    rows.sort(key=lambda item: (-item["total_workload"], item["teacher_id"]))

    departments = {}
    for row in rows:
        bucket = departments.setdefault(row["department"], {"department": row["department"], "teachers": 0, "total_workload": 0.0, "over_limit": 0, "low": 0})
        bucket["teachers"] += 1
        bucket["total_workload"] += row["total_workload"]
        if row["status"] == "over_limit":
            bucket["over_limit"] += 1
        if row["status"] == "low":
            bucket["low"] += 1
    dept_rows = []
    for bucket in departments.values():
        bucket["total_workload"] = r2(bucket["total_workload"])
        bucket["average_workload"] = r2(bucket["total_workload"] / bucket["teachers"])
        dept_rows.append(bucket)
    dept_rows.sort(key=lambda item: (-item["total_workload"], item["department"]))

    grand = r2(sum(row["total_workload"] for row in rows))
    has_error = any(item["level"] == "error" for item in issues)
    needs_review = has_error or counters["over_limit"] or counters["low"]
    return {
        "status": "needs_review" if needs_review else "ok",
        "term": text(data.get("term", "未标注学期"), 40),
        "rules_applied": {
            "standard_workload": rules["standard_workload"],
            "min_workload": rules["min_workload"],
            "max_workload": rules["max_workload"],
            "high_ratio": rules.get("high_ratio"),
            "class_size_tiers": rules["class_size_tiers"],
            "merged_class_extra": rules.get("merged_class_extra"),
            "new_course_coefficient": rules.get("new_course_coefficient"),
            "course_type_coefficient": rules["course_type_coefficient"],
            "supervision_hours": rules["supervision_hours"],
        },
        "summary": {
            "teachers": len(rows),
            "courses_counted": sum(len(row["courses"]) for row in rows),
            "total_workload": grand,
            "average_workload": r2(grand / len(rows)) if rows else 0.0,
            **counters,
            "errors": sum(1 for item in issues if item["level"] == "error"),
            "warnings": sum(1 for item in issues if item["level"] == "warning"),
        },
        "teachers": rows,
        "department_summary": dept_rows,
        "issues": issues,
    }


def esc(value, limit=120):
    return html.escape(text(value, limit))


def markdown(result):
    summary = result.get("summary", {})
    rules = result.get("rules_applied", {})
    lines = [
        f"# 教学工作量核算预览：{esc(result.get('term', '未标注学期'))}",
        "",
        f"状态：**{result.get('status')}**；教师 {summary.get('teachers', 0)} 人，计入课程 {summary.get('courses_counted', 0)} 门，"
        f"总折算 {summary.get('total_workload', 0)} 学时，人均 {summary.get('average_workload', 0)} 学时。",
        "",
        f"阈值：下限 {rules.get('min_workload')} / 标准 {rules.get('standard_workload')} / 上限 {rules.get('max_workload')} 学时。"
        f"超限 {summary.get('over_limit', 0)} 人，偏高 {summary.get('high', 0)} 人，正常 {summary.get('normal', 0)} 人，不足 {summary.get('low', 0)} 人。",
        "",
        "## 教师工作量总表",
        "| 教师 | 职称 | 院系 | 课程折算 | 指导折算 | 合计 | 达标率 | 判定 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in result.get("teachers", []):
        ratio = f"{row['ratio_to_standard'] * 100:.0f}%" if row.get("ratio_to_standard") is not None else "-"
        lines.append(
            f"| {esc(row['name'])}（{esc(row['teacher_id'], 40)}） | {esc(row['title'], 20)} | {esc(row['department'], 40)} | "
            f"{row['course_workload']} | {row['supervision_workload']} | **{row['total_workload']}** | {ratio} | {row['status_label']} |"
        )
    focus = [row for row in result.get("teachers", []) if row["status"] in ("over_limit", "low")]
    if focus:
        lines += ["", "## 需重点处置名单", "| 教师 | 判定 | 合计 | 建议 |", "|---|---|---:|---|"]
        for row in focus:
            advice = "超出上限，需按规定审批超课时或调减下学期任务" if row["status"] == "over_limit" else "低于下限，需核实是否漏报课程/指导，或补充教学任务"
            lines.append(f"| {esc(row['name'])} | {row['status_label']} | {row['total_workload']} | {advice} |")
    lines += ["", "## 折算明细"]
    for row in result.get("teachers", []):
        lines.append(f"### {esc(row['name'])}（{esc(row['teacher_id'], 40)}）合计 {row['total_workload']} 学时")
        if row["courses"]:
            lines += ["| 课程 | 类型 | 学时 | 人数 | 合班 | 类型系数 | 人数系数 | 合班系数 | 新开系数 | 折算 |",
                      "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for course in row["courses"]:
                coef = course["coefficients"]
                lines.append(
                    f"| {esc(course['name'], 60)}({esc(course['course_id'], 40)}) | {esc(course['type'], 20)} | {course['hours']} | "
                    f"{course['students'] if course['students'] is not None else '-'} | {course['merged_classes']} | "
                    f"{coef['type']} | {coef['class_size']} | {coef['merged']} | {coef['new_course']} | {course['converted_hours']} |"
                )
        else:
            lines.append("- 无课程记录")
        for sup in row["supervisions"]:
            lines.append(f"- {esc(sup['label'], 40)}：{sup['count']} 人 × {sup['hours_each']} 学时 = {sup['converted_hours']} 学时")
        lines.append("")
    if result.get("department_summary"):
        lines += ["## 院系汇总", "| 院系 | 教师数 | 总折算 | 人均 | 超限 | 不足 |", "|---|---:|---:|---:|---:|---:|"]
        for row in result["department_summary"]:
            lines.append(f"| {esc(row['department'], 40)} | {row['teachers']} | {row['total_workload']} | {row['average_workload']} | {row['over_limit']} | {row['low']} |")
        lines.append("")
    if result.get("issues"):
        lines += ["## 数据问题", "| 级别 | 对象 | 说明 |", "|---|---|---|"]
        for item in result["issues"]:
            lines.append(f"| {esc(item.get('level'), 20)} | {esc(item.get('target'), 60)} | {esc(item.get('message'))} |")
        lines.append("")
    lines += [
        "## 人工确认",
        "- 折算系数、超课时上下限须以本校教学工作量管理办法为准，本结果只是按输入规则的复算。",
        "- error 级问题对应的课程或指导条目未计入合计，需先补齐数据再复算。",
        "- 涉及绩效、津贴发放前必须由教务处与人事部门人工复核。",
        "- 本结果为离线预览，不写回教务系统、不触发任何审批或发放流程。",
    ]
    return "\n".join(lines) + "\n"


def demo():
    return json.loads(Path(__file__).parents[1].joinpath("examples/sample_input.json").read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description="离线教师教学工作量核算与超限校验")
    ap.add_argument("--input", help="JSON 输入文件，- 表示 stdin")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--demo", action="store_true", help="使用内置示例数据")
    ap.add_argument("--json", action="store_true", dest="json_only", help="仅打印结构化结果")
    ap.add_argument("--strict", action="store_true", help="存在数据错误或超限/不足时以非零码退出")
    args = ap.parse_args()
    if not args.demo and not args.input:
        ap.error("请提供 --input 或 --demo")
    try:
        raw = demo() if args.demo else (json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8")))
        result = calculate(raw)
        if args.json_only or args.strict:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.strict and result["status"] != "ok":
            return 2
        if not args.json_only and not args.strict:
            out = Path(args.out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "workload_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "workload_report.md").write_text(markdown(result), encoding="utf-8")
            print(f"已生成 {out / 'workload_report.json'} 和 {out / 'workload_report.md'}")
        return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError, RecursionError, MemoryError) as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
