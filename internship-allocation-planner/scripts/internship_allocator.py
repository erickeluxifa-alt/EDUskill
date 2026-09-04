#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实习分配规划器 internship_allocator.py
教育场景「实习组织管理」：将学生按志愿分配到 实习单位×期次，显式揭示缺口与冲突。

两种模式：
  * 分配模式（默认）：按「志愿数量少优先 > 姓名字典序」确定性贪心分配；
    校验单位期次容量、专业匹配（可选硬约束）、开放期次与可用期次约束；
    输出分配建议 + 未分配缺口清单（含原因与处置建议）+ 单位×期次利用率统计。
  * 检查模式（--check）：不重新分配，仅对已有 assignments 做冲突体检：
    单位×期次超额、同学生被分多个单位、引用未知单位/未知期次。

安全与交互约束：
  * 用户可控文本（姓名/单位/期次等）输出时统一 HTML 转义 + Markdown 转义，防 XSS 与表格注入；
  * 默认只读：仅打印到 stdout；--out 写盘需显式指定，目标文件已存在时必须 --force 才覆盖；
  * 零第三方依赖、不访问网络、不执行输入中的任何代码。

输入 JSON（中英文字段别名，详见 README）：
{
  "students": [ {"name":"李明","class":"计科2301","major":"计算机",
                 "options":["云智科技","星云软件"],"windows":["w1","w2"]} ],
  "units":    [ {"name":"云智科技","capacity":20,"majors":["计算机"],"windows":["w1"]} ],
  "windows":  [ {"id":"w1","label":"第1-4周"}, {"id":"w2","label":"第5-8周"} ],
  "rules":    {"major_strict": false, "fallback_any": false, "default_capacity": 10}
}
"""

import argparse
import json
import os
import re
import sys

DEFAULT_CAPACITY = 10

STUDENT_KEYS = {
    "name": ["name", "姓名", "学生姓名"],
    "class_": ["class", "班级"],
    "major": ["major", "专业"],
    "options": ["options", "志愿", "志愿单位", "意向单位", "choice"],
    "windows": ["windows", "可用期次", "可实习期次", "available"],
}
UNIT_KEYS = {
    "name": ["name", "名称", "单位名", "企业名"],
    "industry": ["industry", "行业", "领域"],
    "majors": ["majors", "专业", "专业要求"],
    "capacity": ["capacity", "容量", "每期容量", "可接收人数"],
    "windows": ["windows", "开放期次", "可接期次", "期次"],
}
WINDOW_KEYS = {"id": ["id", "编号"], "label": ["label", "名称", "说明"],
               "start": ["start", "开始"], "end": ["end", "结束"]}
ASSIGN_KEYS = {"student": ["student", "学生", "学生姓名"],
               "unit": ["unit", "单位", "实习单位"],
               "window": ["window", "期次", "批次"]}


def pick(obj, keys, default=None):
    """按别名顺序取字段（跳过 None）。"""
    if not isinstance(obj, dict):
        return default
    for k in keys:
        v = obj.get(k)
        if v is not None:
            return v
    return default


def as_int(v, label, errors, default=None):
    """宽容整数解析：支持 12 / "12" / "12人"。负数与非法值返回 None 并记错。"""
    if v is None:
        return default
    if isinstance(v, bool):
        errors.append(f"{label} 不能是布尔值")
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip().replace(",", "").replace("，", "").replace("人", "").replace("名", "")
    if re.fullmatch(r"\d+", s):
        return int(s)
    errors.append(f"{label} 的值 '{v}' 不是合法数字")
    return None


def as_list(v, label, errors):
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    errors.append(f"{label} 必须是字符串或数组")
    return []


def esc(text):
    """HTML 转义 + Markdown 表格转义 + 控制字符清理（防 XSS 与表格注入）。"""
    if text is None:
        return ""
    s = str(text)
    s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
          .replace('"', "&quot;").replace("'", "&#39;"))
    s = s.replace("|", "\\|").replace("\n", "<br>").replace("\r", "")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)


class InputError(Exception):
    pass


# ---------------------------------------------------------------- 输入解析
def get_rules(data, errors):
    rules = {"major_strict": False, "fallback_any": False, "default_capacity": DEFAULT_CAPACITY}
    src = pick(data, ["rules", "规则"])
    if isinstance(src, dict):
        ms = src.get("major_strict", src.get("专业严格匹配"))
        if ms is not None:
            rules["major_strict"] = bool(ms)
        fb = src.get("fallback_any", src.get("自动调剂"))
        if fb is not None:
            rules["fallback_any"] = bool(fb)
        cap = as_int(src.get("default_capacity", src.get("默认容量")), "规则-默认容量", errors)
        if cap and cap > 0:
            rules["default_capacity"] = cap
    return rules


def get_students(data, errors):
    src = pick(data, ["students", "学生", "名单", "实习生"])
    if src is None:
        return None
    if not isinstance(src, list):
        errors.append("字段 students/学生 必须是数组")
        return []
    out = []
    for i, item in enumerate(src, 1):
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            errors.append(f"students[{i}] 必须是对象")
            continue
        name = str(pick(item, STUDENT_KEYS["name"], "") or "").strip()
        if not name:
            errors.append(f"students[{i}] 缺少姓名")
            continue
        out.append({
            "name": name,
            "class_": str(pick(item, STUDENT_KEYS["class_"], "") or "").strip(),
            "major": str(pick(item, STUDENT_KEYS["major"], "") or "").strip(),
            "options": as_list(pick(item, STUDENT_KEYS["options"]), f"学生 {name} 的志愿", errors),
            "windows": as_list(pick(item, STUDENT_KEYS["windows"]), f"学生 {name} 的期次", errors),
        })
    return out


def get_units(data, errors, default_cap):
    src = pick(data, ["units", "单位", "企业", "实习单位"])
    if src is None:
        return None
    if not isinstance(src, list):
        errors.append("units/单位 必须是数组")
        return []
    out = []
    for i, item in enumerate(src, 1):
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            errors.append(f"units[{i}] 必须是对象")
            continue
        name = str(pick(item, UNIT_KEYS["name"], "") or "").strip()
        if not name:
            errors.append(f"units[{i}] 缺少单位名称")
            continue
        cap = as_int(pick(item, UNIT_KEYS["capacity"]), f"单位 {name} 的容量", errors, default_cap)
        if cap is not None and cap < 0:
            errors.append(f"单位 {name} 的容量不能为负数")
            cap = 0
        out.append({
            "name": name,
            "industry": str(pick(item, UNIT_KEYS["industry"], "") or "").strip(),
            "majors": as_list(pick(item, UNIT_KEYS["majors"]), f"单位 {name} 的专业要求", errors),
            "capacity": int(cap) if cap is not None else default_cap,
            "windows": as_list(pick(item, UNIT_KEYS["windows"]), f"单位 {name} 的开放期次", errors),
        })
    return out


def get_windows(data, errors):
    src = pick(data, ["windows", "期次", "批次"])
    if src is None:
        return {}
    if not isinstance(src, list):
        errors.append("windows/期次 必须是数组")
        return {}
    out = {}
    for i, item in enumerate(src, 1):
        if isinstance(item, str):
            item = {"id": item}
        if not isinstance(item, dict):
            continue
        wid = str(pick(item, WINDOW_KEYS["id"], "") or "").strip()
        if not wid:
            errors.append(f"windows[{i}] 缺少期次编号")
            continue
        out[wid] = {"label": str(pick(item, WINDOW_KEYS["label"], wid) or wid).strip(),
                    "start": str(pick(item, WINDOW_KEYS["start"], "") or "").strip(),
                    "end": str(pick(item, WINDOW_KEYS["end"], "") or "").strip()}
    return out


def get_assignments(data, errors):
    src = pick(data, ["assignments", "已分配", "分配结果"])
    if src is None:
        return []
    if not isinstance(src, list):
        errors.append("assignments/已分配 必须是数组")
        return []
    out = []
    for i, item in enumerate(src, 1):
        if not isinstance(item, dict):
            errors.append(f"assignments[{i}] 必须是对象")
            continue
        student = str(pick(item, ASSIGN_KEYS["student"], "") or "").strip()
        unit = str(pick(item, ASSIGN_KEYS["unit"], "") or "").strip()
        window = str(pick(item, ASSIGN_KEYS["window"], "") or "").strip()
        if not student or not unit:
            errors.append(f"assignments[{i}] 必须同时包含学生和单位")
            continue
        out.append({"student": student, "unit": unit, "window": window})
    return out


def load(data, need_students=True):
    """解析并校验输入。返回 (rules, students, units, windows, assignments)。"""
    errors = []
    rules = get_rules(data, errors)
    students = get_students(data, errors)
    units = get_units(data, errors, rules["default_capacity"])
    windows = get_windows(data, errors)
    assigns = get_assignments(data, errors)
    if students is None:
        if need_students:
            errors.append("缺少必要字段：students/学生 名单")
        students = []
    if units is None:
        errors.append("缺少必要字段：units/单位 列表")
        units = []
    if need_students and not students:
        errors.append("学生名单不能为空")
    if errors:
        raise InputError("；".join(errors))
    return rules, students, units, windows, assigns


# ---------------------------------------------------------------- 分配逻辑
def major_match(student, unit):
    """专业匹配：单位无要求=匹配；学生无专业=匹配；否则查包含关系。"""
    if not unit["majors"]:
        return True
    if not student["major"]:
        return True
    return student["major"] in unit["majors"]


def unit_windows(unit, windows):
    """单位开放期次：显式列表 > 全按期次 > 单桶（空期次）。"""
    if unit["windows"]:
        return sorted(unit["windows"])
    if windows:
        return sorted(windows.keys())
    return [""]


def order_word(level):
    cn = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    return f"{cn[level - 1]}志愿" if level <= 10 else f"第{level}志愿"


def place_one(student, units_by, rules, windows, usage, fallback=False):
    """为单个学生尝试分配。返回 placement dict 或 None。"""
    if fallback:
        pool = sorted((u for u in units_by.values()
                       if not u["majors"] or not student["major"] or student["major"] in u["majors"]),
                      key=lambda u: u["name"])
    else:
        pool = [units_by[opt] for opt in student["options"] if opt in units_by]
    for unit in pool:
        if not fallback and rules["major_strict"] and not major_match(student, unit):
            continue
        for w in unit_windows(unit, windows):
            if student["windows"] and w not in student["windows"]:
                continue
            key = (unit["name"], w)
            cur = usage.get(key)
            if cur is None:
                usage[key] = [0, unit["capacity"]]
                cur = usage[key]
            if cur[0] < cur[1]:
                usage[key] = [cur[0] + 1, cur[1]]
                level = ("调剂" if fallback
                         else order_word(student["options"].index(unit["name"]) + 1))
                return {"student": student["name"], "class_": student["class_"],
                        "major": student["major"], "unit": unit["name"],
                        "window": w, "level": level}
    return None


def diagnose(student, units_by, windows):
    """未分配原因归因：无志愿 / 志愿不存在 / 专业不符 / 时段无交集 / 志愿全满。"""
    if not student["options"]:
        return "无志愿", "该学生未填写志愿单位，请人工安排"
    known = [o for o in student["options"] if o in units_by]
    if not known:
        return "志愿单位不存在", "志愿名单中的单位未出现在单位列表中，请核对名称"
    majors_ok = any(not units_by[o]["majors"] or not student["major"]
                    or student["major"] in units_by[o]["majors"] for o in known)
    if not majors_ok:
        return "专业不符", "志愿单位均有专业要求且不匹配，可与单位协商放宽或调整志愿"
    if student["windows"]:
        any_overlap = any(any(w in student["windows"] for w in unit_windows(units_by[o], windows))
                          for o in known)
        if not any_overlap:
            return "时段无交集", "学生的可用期次与志愿单位的开放期次无交集，请协商调整期次"
    return "志愿全满", "志愿单位在当前期次内均无剩余容量，请协商增开班次量或调整志愿"


def alloc(data):
    """分配模式主流程。返回 (placements, unplaced, rules, usage, total_students)。"""
    rules, students, units, windows, assigns = load(data)
    units_by = {u["name"]: u for u in units}
    usage = {}
    for u in units:
        for w in unit_windows(u, windows):
            usage[(u["name"], w)] = [0, u["capacity"]]
    for a in assigns:  # 已有分配先占用容量
        key = (a["unit"], a["window"])
        if key in usage:
            usage[key][0] += 1

    placements, unplaced = [], []
    ordered = sorted(students, key=lambda s: (len(s["options"]), s["name"]))
    for stu in ordered:
        p = place_one(stu, units_by, rules, windows, usage)
        if p is None and rules["fallback_any"]:
            p = place_one(stu, units_by, rules, windows, usage, fallback=True)
        if p:
            placements.append(p)
        else:
            reason, detail = diagnose(stu, units_by, windows)
            unplaced.append({"student": stu["name"], "class_": stu["class_"],
                             "major": stu["major"], "reason": reason, "detail": detail})
    return placements, unplaced, rules, usage, len(students) + len(assigns)


def check(data):
    """检查模式：体检已有分配方案。返回 (findings, checked_count, rules)。"""
    rules, _, units, windows, assigns = load(data, need_students=False)
    units_by = {u["name"]: u for u in units}
    findings = []
    per_key = {}
    for a in assigns:
        key = (a["unit"], a["window"])
        per_key[key] = per_key.get(key, 0) + 1
    for (uname, w), n in per_key.items():
        if uname not in units_by:
            findings.append({"type": "未知单位", "unit": uname, "window": w,
                             "detail": f"该单位不在单位清单中（{n} 名学生受影响）"})
            continue
        unit = units_by[uname]
        if n > unit["capacity"]:
            findings.append({"type": "单位期次数超额", "unit": uname, "window": w,
                             "detail": f"已分配 {n} 人，超出容量 {unit['capacity']} 人，多出 {n - unit['capacity']} 人"})
        elif unit["windows"] and w and w not in unit["windows"]:
            findings.append({"type": "未知期次", "unit": uname, "window": w,
                             "detail": "该期次不在单位的开放期次内"})
    per_student = {}
    for a in assigns:
        per_student.setdefault(a["student"], set()).add(a["unit"])
    for stu, units_set in per_student.items():
        if len(units_set) > 1:
            findings.append({"type": "学生分属多单位", "student": stu,
                             "detail": f"同一学生被分配到 {len(units_set)} 个单位：{', '.join(sorted(units_set))}"})
    return findings, len(assigns), rules


# ---------------------------------------------------------------- 输出
def md_report(placements, unplaced, usage):
    total = len(placements) + len(unplaced)
    lines = ["# 学生实习分配方案（预览）"]
    lines.append("## 一、需人工处理（未分配缺口）" if unplaced else "## 一、需人工处理")
    if unplaced:
        for it in unplaced:
            lines.append(f"- **{esc(it['student'])}**（{esc(it['class_'])}/{esc(it['major'] or '未填专业')}）："
                         f"{esc(it['reason'])} — {esc(it['detail'])}")
    else:
        lines.append("无，全部学生已分配。")
    lines.append("## 二、分配方案")
    if placements:
        lines.append("| 学生 | 班级 | 专业 | 单位 | 期次 | 志愿命中 |")
        lines.append("|---|---|---|---|---|---|")
        for p in sorted(placements, key=lambda x: (x["class_"], x["student"])):
            lines.append(f"| {esc(p['student'])} | {esc(p['class_'])} | {esc(p['major'])} | "
                         f"{esc(p['unit'])} | {esc(p['window']) or '-'} | {esc(p['level'])} |")
    else:
        lines.append("（暂无安排）")
    if usage:
        rows = [(k, v) for k, v in usage.items() if v[1] > 0]
        lines.append("## 三、单位×期次利用率")
        lines.append("| 单位 | 期次 | 已分配 | 容量 | 利用率 |")
        lines.append("|---|---|---|---|---|")
        for (unit, w), (used, cap) in sorted(rows):
            rate = f"{used * 100.0 // cap:.0f}%" if cap else "-"
            lines.append(f"| {esc(unit)} | {esc(w) or '-'} | {used} | {cap} | {rate} |")
    lines.append("## 四、统计汇总")
    rate = f"{len(placements) * 100 // total}%" if total else "0%"
    lines.append(f"- 学生总数：{total}；已分配 {len(placements)} 人；未分配 {len(unplaced)} 人；整体分配率 {rate}")
    if placements:
        hit1 = sum(1 for p in placements if p["level"] == "一志愿")
        lines.append(f"- 第一志愿命中：{hit1}/{len(placements)}（{hit1 * 100 // len(placements)}%）")
    return "\n".join(lines)


def md_check(findings):
    lines = ["# 已有实习分配体检报告"]
    if not findings:
        lines.append("## 一、检查通过")
        lines.append("未发现超额、未知引用或学生多单位等冲突。")
        return "\n".join(lines)
    lines.append("## 一、发现的问题（需处理）")
    for f in findings:
        who = f.get("unit") or f.get("student") or ""
        lines.append(f"- **{esc(f['type'])}**：{esc(who)} {esc(f.get('window') or '')} "
                     f"— {esc(f['detail'])}")
    return "\n".join(lines)


def emit(text, args):
    if args.out:
        if os.path.exists(args.out) and not args.force:
            print(f"错误：输出文件已存在：{args.out}（如需覆盖请加 --force）", file=sys.stderr)
            sys.exit(2)
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            print(f"错误：无法写入 {args.out}：{e}", file=sys.stderr)
            sys.exit(2)
    else:
        print(text)


def main():
    ap = argparse.ArgumentParser(description="实习单位分配与排期助手（零依赖，离线可跑）")
    ap.add_argument("input", nargs="?", default="-", help="输入 JSON 文件，缺省从 stdin 读取")
    ap.add_argument("--json", action="store_true", help="输出 JSON 结果")
    ap.add_argument("--check", action="store_true", help="检查模式：只体检已有分配，不重新分配")
    ap.add_argument("--out", default=None, help="写盘保存到指定文件（默认仅打印预览）")
    ap.add_argument("--force", action="store_true", help="写盘时允许覆盖已存在文件")
    args = ap.parse_args()

    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            try:
                raw = open(args.input, "r", encoding="utf-8").read()
            except OSError:
                print(f"错误：无法读取输入文件 {args.input}", file=sys.stderr)
                sys.exit(2)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise InputError(f"JSON 解析失败：{e}")
        if not isinstance(data, dict):
            raise InputError("输入必须是 JSON 对象")

        if args.check:
            findings, checked, rules = check(data)
            if args.json:
                text = json.dumps({"mode": "check", "checked": checked, "ok": not findings,
                                   "findings": findings}, ensure_ascii=False, indent=2)
            else:
                text = md_check(findings)
        else:
            placements, unplaced, rules, usage, total = alloc(data)
            if args.json:
                text = json.dumps({
                    "mode": "alloc",
                    "summary": {"total_students": total, "assigned": len(placements),
                                "unassigned": len(unplaced)},
                    "placements": placements,
                    "issues": unplaced,
                    "utilization": [{"unit": u, "window": w, "assigned": c, "capacity": cap}
                                    for (u, w), (c, cap) in sorted(usage.items()) if cap > 0],
                    "rules": {"major_strict": rules["major_strict"],
                              "fallback_any": rules["fallback_any"]},
                }, ensure_ascii=False, indent=2)
            else:
                text = md_report(placements, unplaced, usage)
        emit(text, args)
        if args.check:
            sys.exit(0 if not findings else 1)
        sys.exit(0 if not unplaced else 1)
    except (InputError, ValueError) as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()