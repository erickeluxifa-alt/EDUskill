#!/usr/bin/env python3
import argparse
import html
import json
import sys
from pathlib import Path

MAX_SEATS = 400
MAX_STUDENTS = 200
MAX_SEARCH_NODES = 100000


def text(value, limit=120):
    return str(value).replace("|", "/").replace("\n", " ")[:limit]


def seats_adjacent(first, second):
    return max(abs(first[0] - second[0]), abs(first[1] - second[1])) <= 1


def seat_key(row, col):
    return f"R{row}C{col}"


def parse_seat(value, rows, cols):
    if not isinstance(value, str) or len(value) < 4 or value[0] != "R" or "C" not in value:
        return None
    try:
        row, col = value[1:].split("C", 1)
        row, col = int(row), int(col)
    except (ValueError, TypeError):
        return None
    return (row, col) if 1 <= row <= rows and 1 <= col <= cols else None


def plan(data):
    errors, warnings = [], []
    if not isinstance(data, dict):
        return {"status": "data_error", "errors": ["输入顶层必须是 JSON 对象"], "assignments": [], "unmet_constraints": []}
    room = data.get("room") or {}
    if not isinstance(room, dict):
        return {"status": "data_error", "errors": ["room 必须是 JSON 对象"], "assignments": [], "unmet_constraints": []}
    rows, cols = room.get("rows"), room.get("cols")
    if (isinstance(rows, bool) or isinstance(cols, bool) or not isinstance(rows, int) or not isinstance(cols, int) or rows < 1 or cols < 1):
        return {"status": "data_error", "errors": ["room.rows 和 room.cols 必须为正整数"], "assignments": [], "unmet_constraints": []}
    if rows * cols > MAX_SEATS:
        return {"status": "data_error", "errors": [f"座位总数不能超过 {MAX_SEATS}"], "assignments": [], "unmet_constraints": []}
    students = data.get("students")
    if not isinstance(students, list) or not students:
        return {"status": "data_error", "errors": ["students 必须是非空列表"], "assignments": [], "unmet_constraints": []}
    if len(students) > MAX_STUDENTS:
        return {"status": "data_error", "errors": [f"学生数不能超过 {MAX_STUDENTS}"], "assignments": [], "unmet_constraints": []}
    ids, names = [], {}
    for item in students:
        raw_sid = item.get("id") if isinstance(item, dict) else None
        sid = raw_sid.strip() if isinstance(raw_sid, str) else ""
        if not sid or sid in ids:
            errors.append(f"学生 ID 缺失或重复: {raw_sid or '空值'}")
        else:
            ids.append(sid); names[sid] = text(item.get("name", "未命名"))
    available = [(r, c) for r in range(1, rows + 1) for c in range(1, cols + 1)]
    blocked = set()
    for raw in room.get("blocked_seats", []):
        seat = parse_seat(raw, rows, cols)
        if seat is None: errors.append(f"禁用座位无效: {raw}")
        else: blocked.add(seat)
    seats = [s for s in available if s not in blocked]
    if len(ids) > len(seats): errors.append(f"学生数 {len(ids)} 超过可用座位数 {len(seats)}")
    constraints = data.get("constraints") or {}
    if not isinstance(constraints, dict):
        return {"status": "data_error", "errors": ["constraints 必须是 JSON 对象"], "assignments": [], "unmet_constraints": []}
    pairs, pair_seen = [], set()
    for pair in constraints.get("separated_pairs", []):
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]:
            errors.append(f"分离约束格式无效: {pair}"); continue
        a, b = str(pair[0]), str(pair[1]); key = tuple(sorted((a, b)))
        if a not in ids or b not in ids: errors.append(f"分离约束引用不存在学生: {a},{b}")
        elif key not in pair_seen: pairs.append(key); pair_seen.add(key)
    separated = {sid: set() for sid in ids}
    for a, b in pairs: separated[a].add(b); separated[b].add(a)
    fixed, occupied = {}, set()
    fixed_input = constraints.get("fixed_seats") or {}
    if not isinstance(fixed_input, dict):
        return {"status": "data_error", "errors": ["constraints.fixed_seats 必须是 JSON 对象"], "assignments": [], "unmet_constraints": []}
    for sid, raw in fixed_input.items():
        sid = str(sid); seat = parse_seat(raw, rows, cols)
        if sid not in ids: errors.append(f"固定座位引用不存在学生: {sid}")
        elif seat is None or seat in blocked: errors.append(f"固定座位无效或已禁用: {sid}->{raw}")
        elif seat in occupied: errors.append(f"固定座位重复占用: {raw}")
        else: fixed[sid] = seat; occupied.add(seat)
    front = [str(s) for s in constraints.get("front_row_ids", [])]
    for sid in front:
        if sid not in ids: errors.append(f"前排约束引用不存在学生: {sid}")
    if errors:
        return {"status": "data_error", "errors": errors, "assignments": [], "unmet_constraints": []}

    original_position = {sid: index for index, sid in enumerate(ids)}
    order = sorted(ids, key=lambda sid: (-len(separated[sid]), 0 if sid in fixed else 1, original_position[sid]))
    assigned = dict(fixed)
    used = set(occupied)
    search_nodes = 0
    budget_exhausted = False
    def allowed(sid, seat):
        if seat in used: return False
        if sid in front and seat[0] != 1: return False
        for other in separated[sid]:
            if other in assigned and seats_adjacent(seat, assigned[other]):
                return False
        return True
    def search(index):
        nonlocal search_nodes, budget_exhausted
        search_nodes += 1
        if search_nodes > MAX_SEARCH_NODES:
            budget_exhausted = True
            return False
        if index == len(order): return True
        sid = order[index]
        if sid in assigned: return search(index + 1)
        candidates = [s for s in seats if allowed(sid, s)]
        for seat in candidates:
            assigned[sid] = seat; used.add(seat)
            if search(index + 1): return True
            used.remove(seat); del assigned[sid]
        return False
    solved = search(0)
    unmet = []
    for a, b in pairs:
        if a in assigned and b in assigned and seats_adjacent(assigned[a], assigned[b]):
            unmet.append({"type": "separated_pair", "students": [a, b], "message": "两名学生仍相邻"})
    for sid in front:
        if sid in assigned and assigned[sid][0] != 1:
            unmet.append({"type": "front_row", "student": sid, "message": "未安排在第一排"})
    if not solved:
        warnings.append("搜索预算耗尽，已输出固定座位和可安排的部分结果" if budget_exhausted else "约束无完全可行解，已输出固定座位和可安排的部分结果")
        for sid in order:
            if sid not in assigned:
                unmet.append({"type": "unassigned", "student": sid, "message": "没有可用座位"})
    assignments = [{"student_id": sid, "name": names[sid], "seat": seat_key(*assigned[sid])} for sid in ids if sid in assigned]
    return {"status": "ok" if solved and not unmet else "needs_review", "class_name": text(data.get("class_name", "未命名班级")), "room": {"rows": rows, "cols": cols, "blocked_seats": sorted(seat_key(*s) for s in blocked)}, "summary": {"students": len(ids), "assigned": len(assignments), "available_seats": len(seats), "unmet_constraints": len(unmet)}, "assignments": assignments, "unmet_constraints": unmet, "warnings": warnings}


def markdown(result):
    lines = [f"# 座位编排预览：{html.escape(result.get('class_name', '未命名'))}", "", f"状态：**{result.get('status')}**；已安排 {result.get('summary', {}).get('assigned', 0)} / {result.get('summary', {}).get('students', 0)} 人。", "", "## 座位表", "| 座位 | 学号 | 学生 |", "|---|---|---|"]
    for row in result.get("assignments", []): lines.append(f"| {row['seat']} | {html.escape(text(row['student_id']))} | {html.escape(text(row['name']))} |")
    if result.get("unmet_constraints"):
        lines += ["", "## 未满足约束", "| 类型 | 对象 | 说明 |", "|---|---|---|"]
        for item in result["unmet_constraints"]: lines.append(f"| {text(item.get('type'))} | {text(item.get('student') or ','.join(item.get('students', [])))} | {text(item.get('message'))} |")
    lines += ["", "## 人工确认", "- 核对学生名单、隐私和特殊座位依据。", "- 核对考试纪律或课堂管理要求后再执行。", "- 本结果是离线预览，不会写回 LMS/SIS 或发送通知。"]
    return "\n".join(lines) + "\n"


def demo():
    return json.loads(Path(__file__).parents[1].joinpath("examples/sample_input.json").read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description="离线课堂座位编排")
    ap.add_argument("--input", help="JSON 输入文件，- 表示 stdin")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--json", action="store_true", dest="json_only")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if not args.demo and not args.input: ap.error("请提供 --input 或 --demo")
    try:
        raw = demo() if args.demo else (json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8")))
        result = plan(raw)
        if args.json_only or args.strict:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.strict and result["status"] != "ok": return 2
        if not args.json_only and not args.strict:
            out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
            (out / "seating_plan.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "seating_plan.md").write_text(markdown(result), encoding="utf-8")
            print(f"已生成 {out / 'seating_plan.json'} 和 {out / 'seating_plan.md'}")
        return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError, RecursionError, MemoryError) as exc:
        print(f"输入错误：{exc}", file=sys.stderr); return 2

if __name__ == "__main__": sys.exit(main())
