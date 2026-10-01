#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作业截止日期冲突与学业负荷分析器，零依赖。"""
import argparse
import datetime as dt
import html
import json
import sys
from collections import defaultdict

MAX_FIELD_LEN = 200
DEFAULT_CAPACITY = 8.0
DEFAULT_WINDOW = 2


def clean(value):
    text = "" if value is None else str(value).strip()
    if len(text) > MAX_FIELD_LEN:
        text = text[:MAX_FIELD_LEN] + "...(truncated)"
    return html.escape(text)


def parse_date(value):
    try:
        return dt.date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def load_records(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取有效 JSON：%s" % clean(exc))
    if isinstance(data, dict):
        if "assignments" not in data:
            raise ValueError("JSON 根节点必须是数组或 assignments 数组")
        data = data["assignments"]
    if not isinstance(data, list):
        raise ValueError("JSON 根节点必须是数组或 assignments 数组")
    valid, invalid = [], []
    for index, raw in enumerate(data, 1):
        if not isinstance(raw, dict):
            invalid.append({"index": index, "reason": "记录不是对象"})
            continue
        due = parse_date(raw.get("due_date"))
        title = clean(raw.get("title"))
        class_name = clean(raw.get("class_name", raw.get("class")))
        course = clean(raw.get("course"))
        try:
            hours = float(raw.get("estimated_hours", 0))
        except (TypeError, ValueError):
            hours = -1
        if not title or not class_name or not course or due is None or hours < 0:
            invalid.append({"index": index, "reason": "缺少标题/课程/班级、日期格式错误或预计小时数非法"})
            continue
        try:
            priority = int(raw.get("priority", 3))
        except (TypeError, ValueError):
            priority = 3
        valid.append({"id": index, "title": title, "course": course, "class_name": class_name,
                      "due": due, "hours": hours, "priority": max(1, min(5, priority))})
    return valid, invalid


def in_window(date_a, date_b, window):
    return abs((date_a - date_b).days) <= window


def workload(items, anchor):
    start = anchor - dt.timedelta(days=6)
    end = anchor + dt.timedelta(days=6)
    return sum(item["hours"] for item in items if start <= item["due"] <= end)


def suggest(item, peers, capacity, window):
    candidates = []
    for offset in range(1, 8):
        new_date = item["due"] + dt.timedelta(days=offset)
        if any(other["id"] != item["id"] and in_window(new_date, other["due"], window) for other in peers):
            continue
        moved = [dict(other) for other in peers if other["id"] != item["id"]]
        moved.append(dict(item, due=new_date))
        load = workload(moved, new_date)
        score = (0 if load <= capacity else 1, load, offset, item["priority"])
        candidates.append((score, {"assignment_id": item["id"], "new_due_date": new_date.isoformat(),
                                   "window_hours": round(load, 2), "within_capacity": load <= capacity,
                                   "reason": "错开同班级截止日；移动后窗口负荷%s容量" % ("不超过" if load <= capacity else "仍超过")}))
    candidates.sort(key=lambda pair: pair[0])
    return [entry for _, entry in candidates[:3]]


def analyze(records, capacity=DEFAULT_CAPACITY, window=DEFAULT_WINDOW):
    by_class = defaultdict(list)
    for item in records:
        by_class[item["class_name"]].append(item)
    conflicts = []
    for class_name, items in by_class.items():
        items.sort(key=lambda x: (x["due"], x["id"]))
        for item in items:
            peers = [other for other in items if other["id"] != item["id"]]
            close = [other for other in peers if in_window(item["due"], other["due"], window)]
            load = workload(items, item["due"])
            types = []
            if close:
                types.append("截止日期密集")
            if load > capacity:
                types.append("周负荷超载")
            if types:
                conflicts.append({"class_name": class_name, "assignment": item["title"],
                                  "course": item["course"], "due_date": item["due"].isoformat(),
                                  "hours": item["hours"], "window_hours": round(load, 2),
                                  "capacity": capacity, "types": types,
                                  "nearby": [{"title": x["title"], "due_date": x["due"].isoformat()} for x in close],
                                  "suggestions": suggest(item, items, capacity, window) if close else []})
    return conflicts


def render(payload):
    lines = ["# 作业截止日期与学业负荷诊断", "", "## 摘要", "",
             "- 有效记录：%d 条" % payload["valid_count"],
             "- 无效记录：%d 条" % payload["invalid_count"],
             "- 发现问题：%d 条" % len(payload["conflicts"]), ""]
    if not payload["conflicts"]:
        lines += ["## 结论", "", "当前参数下未发现截止日期密集或周负荷超载问题。", ""]
    else:
        lines += ["## 问题清单", "", "| 班级 | 作业 | 截止日期 | 问题 | 窗口预计小时 | 容量 |", "|---|---|---|---|---:|---:|"]
        for item in payload["conflicts"]:
            lines.append("| %s | %s（%s） | %s | %s | %.2f | %.2f |" % (item["class_name"], item["assignment"], item["course"], item["due_date"], "、".join(item["types"]), item["window_hours"], item["capacity"]))
        lines += ["", "## 延期建议", ""]
        for item in payload["conflicts"]:
            if not item["suggestions"]:
                continue
            lines.append("- **%s / %s**：%s" % (item["class_name"], item["assignment"], "; ".join("移至 %s（窗口 %.2f 小时，%s）" % (s["new_due_date"], s["window_hours"], s["reason"]) for s in item["suggestions"])))
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="诊断作业截止日期密集与班级周负荷")
    parser.add_argument("schedule_file", nargs="?", help="作业 JSON 文件")
    parser.add_argument("--json", action="store_true", dest="want_json")
    parser.add_argument("--capacity", type=float, default=DEFAULT_CAPACITY)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    args = parser.parse_args()
    if not args.schedule_file:
        print("用法：python3 assignment_analyze.py <assignments.json> [--json]", file=sys.stderr)
        return 2
    try:
        records, invalid = load_records(args.schedule_file)
        payload = {"valid_count": len(records), "invalid_count": len(invalid), "invalid": invalid,
                   "capacity": args.capacity, "window_days": args.window,
                   "conflicts": analyze(records, args.capacity, args.window)}
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(render(payload))
    if args.want_json:
        print("\n## JSON\n\n```json\n%s\n```" % json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
