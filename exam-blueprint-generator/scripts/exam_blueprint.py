#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exam_blueprint.py - 考试双向细目表生成器（零依赖 Python 标准库）

根据课程知识点及权重、题型、单题分值、难度目标分布，自动生成：
  1) 知识点 × 题型 分值双向矩阵（行列合计与总分严格对齐）
  2) 题型统计（题数、分值、难度标签、认知层次）
  3) 难度分布（易/中/难）与目标对比
  4) 认知层次（布鲁姆）分值分布
  5) 校验结论（分值合计、知识点分配完整性、高阶层次提示、难度偏差）

输入 JSON 结构：
{
  "course": "Python程序设计",
  "exam": "2026年春季学期期末考试",
  "total_marks": 100,
  "knowledge_points": [
    {"name": "基础语法", "weight": 0.2, "level": "了解"},
    {"name": "函数与模块", "weight": 0.25, "level": "理解"}
  ],
  "question_types": [
    {"name": "单项选择题", "count": 10, "marks": 2, "difficulty": "易"}
  ],
  "difficulty_target": {"易": 0.3, "中": 0.5, "难": 0.2}
}

用法:
  python3 exam_blueprint.py <input.json> [--out report.md] [--json] [--csv]
  python3 exam_blueprint.py --demo

退出码: 0=成功（可能含警告） 1=输入校验失败或输出失败
"""
import argparse
import html
import json
import sys

ALLOWED_LEVELS = ("了解", "理解", "应用", "分析", "综合", "评价")
ALLOWED_DIFF = ("易", "中", "难")
DEFAULT_DIFF_TARGET = {"易": 0.3, "中": 0.5, "难": 0.2}
CELL_MAX_LEN = 200
NAME_MAX_LEN = 60
TOTAL_MARKS_MAX = 500
FILE_MAX_BYTES = 2 * 1024 * 1024


def esc(text):
    """HTML 转义用户可控文本，防止报告被注入 HTML/脚本。"""
    return html.escape(str(text), quote=True)


def trunc(text, n=NAME_MAX_LEN):
    s = str(text)
    return s[:n] + ("…" if len(s) > n else "")


def esc_trunc(text, n=NAME_MAX_LEN):
    return esc(trunc(text, n))


def fmt(x):
    """分值显示：整数不带小数点，非整数保留 1 位。"""
    f = float(x)
    return "%g" % f if abs(f - round(f)) < 1e-9 else "%.1f" % f


class Validator:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def fail(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    @property
    def ok(self):
        return not self.errors


# ---------------------------------------------------------------------------
# 输入解析
# ---------------------------------------------------------------------------
def load_json(path, V):
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        V.fail("无法读取输入文件: %s" % path)
        return None
    if len(raw.encode("utf-8")) > FILE_MAX_BYTES:
        V.fail("输入文件过大（超过 2MB）")
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        V.fail("JSON 解析失败（第%d行第%d列）: %s" % (e.lineno, e.colno, e.msg))
        return None
    if not isinstance(data, dict):
        V.fail("JSON 根节点必须是对象（{}）")
        return None
    return data


def obj_str(obj, key, where, V):
    v = obj.get(key)
    if v is None:
        V.fail("%s 缺少必填字段 %s" % (where, key))
        return None
    if not isinstance(v, str) or not v.strip():
        V.fail("%s 字段 %s 必须是非空字符串" % (where, key))
        return None
    return v.strip()


def obj_int(obj, key, where, V):
    v = obj.get(key)
    if v is None:
        V.fail("%s 缺少必填字段 %s" % (where, key))
        return None
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        V.fail("%s 字段 %s 必须是 ≥1 的整数" % (where, key))
        return None
    return v


def obj_num(obj, key, where, V, minimum=0.5):
    v = obj.get(key)
    if v is None:
        V.fail("%s 缺少必填字段 %s" % (where, key))
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < minimum:
        V.fail("%s 字段 %s 必须是 ≥%s 的数字" % (where, key, minimum))
        return None
    return float(v)


def parse_kps(data, V):
    raw = data.get("knowledge_points")
    if raw is None:
        V.fail("缺少必填字段 knowledge_points（知识点列表）")
        return None
    if not isinstance(raw, list) or len(raw) == 0:
        V.fail("knowledge_points 必须是非空数组")
        return None
    kps = []
    seen = set()
    for i, item in enumerate(raw):
        where = "knowledge_points[%d]" % i
        if not isinstance(item, dict):
            V.fail("%s 必须是对象" % where)
            continue
        name = obj_str(item, "name", where, V)
        if name is None:
            continue
        code = str(item.get("code") or name)
        if code in seen:
            V.fail("%s 名称/code 重复: %s" % (where, trunc(name)))
            continue
        seen.add(code)
        weight = item.get("weight", 0.0)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
            V.fail("%s 字段 weight 必须是非负数字" % where)
            continue
        level = str(item.get("level") or "了解")
        if level not in ALLOWED_LEVELS:
            V.warn("%s 认知层次「%s」不在标准集合，回退为「了解」" % (trunc(name), trunc(level)))
            level = "了解"
        kps.append({"name": name, "code": code, "weight": float(weight), "level": level})
    if not kps:
        V.fail("knowledge_points 无有效条目")
        return None
    return kps


def parse_qtypes(data, V):
    raw = data.get("question_types")
    if raw is None:
        V.fail("缺少必填字段 question_types（题型列表）")
        return None
    if not isinstance(raw, list) or len(raw) == 0:
        V.fail("question_types 必须是非空数组")
        return None
    qts = []
    seen = set()
    for i, item in enumerate(raw):
        where = "question_types[%d]" % i
        if not isinstance(item, dict):
            V.fail("%s 必须是对象" % where)
            continue
        name = obj_str(item, "name", where, V)
        if name is None:
            continue
        code = str(item.get("code") or name)
        if code in seen:
            V.fail("%s 题型重复: %s" % (where, trunc(name)))
            continue
        seen.add(code)
        count = obj_int(item, "count", where, V)
        marks = None if item.get("marks") is None else obj_num(item, "marks", where, V)
        if count is None or marks is None:
            continue
        if marks * count > TOTAL_MARKS_MAX + 100:
            V.warn("%s 题型「%s」总分 %g 偏高，请确认" % (where, trunc(name), marks * count))
        diff = str(item.get("difficulty") or "混合")
        if diff not in ALLOWED_DIFF and diff != "混合":
            V.warn("%s 题型「%s」难度标签「%s」无效，按「混合」处理" % (where, trunc(name), trunc(diff)))
            diff = "混合"
        level = str(item.get("level") or "理解")
        if level not in ALLOWED_LEVELS:
            V.warn("%s 题型「%s」认知层次「%s」无效，回退为「理解」" % (where, trunc(name), trunc(level)))
            level = "理解"
        qts.append({"name": name, "code": code, "count": count, "marks": marks,
                    "difficulty": diff, "level": level})
    if not qts:
        V.fail("question_types 无有效条目")
        return None
    return qts


def parse_diff_target(data, V):
    t = data.get("difficulty_target")
    if t is None:
        return dict(DEFAULT_DIFF_TARGET)
    if not isinstance(t, dict):
        V.fail("difficulty_target 必须是对象")
        return None
    out = {}
    s = 0.0
    for d in ALLOWED_DIFF:
        v = t.get(d, 0.0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            V.fail("difficulty_target.%s 必须是非负数字" % d)
            return None
        out[d] = float(v)
        s += out[d]
    if s <= 0:
        V.warn("difficulty_target 全为 0，使用默认 3:5:2")
        return dict(DEFAULT_DIFF_TARGET)
    return {k: v / s for k, v in out.items()}


# ---------------------------------------------------------------------------
# 双向分值矩阵（单位 0.5 分，行列合计严格对齐）
# ---------------------------------------------------------------------------
def fix_sum(arr, want):
    """最大余数修正：将整数数组总和调整到 want（单位 0.5 分）。"""
    diff = want - sum(arr)
    if diff == 0:
        return
    order = sorted(range(len(arr)), key=lambda i: -arr[i] if diff > 0 else arr[i])
    step = 1 if diff > 0 else -1
    for k in range(abs(diff)):
        i = order[k % len(arr)]
        if arr[i] + step < 0:
            continue
        arr[i] += step


def build_matrix(kps, qts, total):
    half = int(round(total * 2))
    n, m = len(kps), len(qts)
    rows = [int(round(k["weight"] * half)) for k in kps]
    cols = [int(round(q["count"] * q["marks"] * 2)) for q in qts]
    fix_sum(rows, half)
    fix_sum(cols, half)
    M = [[rows[i] * cols[j] / float(max(half, 1)) for j in range(m)] for i in range(n)]
    for _ in range(12):
        for i in range(n):
            r = rows[i] / max(sum(M[i]), 1e-9)
            M[i] = [v * r for v in M[i]]
        for j in range(m):
            c = cols[j] / max(sum(M[i][j] for i in range(n)), 1e-9)
            for i in range(n):
                M[i][j] *= c
    G = [[int(round(v)) for v in row] for row in M]
    refine(G, rows, cols)
    return G, rows, cols


def refine(G, rows, cols):
    """整数修补：轮番修正行/列差额直至全部对齐（有限步）。"""
    n, m = len(G), len(G[0])
    for _ in range(300):
        rdev = [sum(G[i]) - rows[i] for i in range(n)]
        cdev = [sum(G[i][j] for i in range(n)) - cols[j] for j in range(m)]
        if not any(rdev) and not any(cdev):
            return
        if any(rdev):
            i = max(range(n), key=lambda x: abs(rdev[x]))
            if rdev[i] > 0:
                j = max(range(m), key=lambda x: G[i][x])
                if G[i][j] <= 0:
                    return
                G[i][j] -= 1
            else:
                # 选择该行中仍小于列目标且行差需要的列加一
                j = max(range(m), key=lambda x: cols[x] - G[i][x])
                G[i][j] += 1
        else:
            j = max(range(m), key=lambda x: abs(cdev[x]))
            if cdev[j] > 0:
                i = next((x for x in range(n) if G[x][j] > 0), None)
                if i is None:
                    return
                j2 = max(range(m), key=lambda x: cdev[x])
                G[i][j] -= 1
                G[i][j2] += 1
            else:
                i = max(range(n), key=lambda x: G[x][j])
                j2 = min(range(m), key=lambda x: (G[i][x] if G[i][x] > 0 else 10 ** 9))
                G[i][j] += 1
                G[i][j2] -= 1


# ---------------------------------------------------------------------------
# 汇总与校验
# ---------------------------------------------------------------------------
def difficulty_stats(qts, cols, target):
    stats = []
    for i, q in enumerate(qts):
        s = cols[i] / 2
        if q["difficulty"] == "混合":
            stats.append((q["name"], s * target["易"], s * target["中"], s * target["难"]))
        elif q["difficulty"] == "易":
            stats.append((q["name"], s, 0.0, 0.0))
        elif q["difficulty"] == "难":
            stats.append((q["name"], 0.0, 0.0, s))
        else:
            stats.append((q["name"], 0.0, s, 0.0))
    return stats


def check_validations(cols, rows, total, kps, diff, easy, med, hard, raw_sum):
    issues = []
    # 题型合计基于原始 count×marks 判断，避免被矩阵分配掩盖输入问题
    if abs(raw_sum - total) < 0.01:
        issues.append("✓ 题型分值合计 %g = 满分 %d" % (raw_sum, total))
    else:
        issues.append("✗ 题型分值合计 %g ≠ 满分 %d，请调整题型 count/marks" % (raw_sum, total))
    zero_kp = [k["name"] for i, k in enumerate(kps) if rows[i] / 2 <= 0]
    if zero_kp:
        issues.append("✗ 以下知识点未获得分值分配: " + "、".join(trunc(x) for x in zero_kp))
    else:
        issues.append("✓ 全部 %d 个知识点均有分值分配" % len(kps))
    hi = [k["name"] for i, k in enumerate(kps) if k["level"] in ("分析", "综合", "评价")]
    if not hi:
        issues.append("⚠ 无「分析/综合/评价」层次知识点，高阶思维考察可能不足")
    if total:
        dev = abs(easy / total - diff["易"]) + abs(med / total - diff["中"]) + abs(hard / total - diff["难"])
        if dev > 0.15:
            issues.append("⚠ 难度分布与目标偏差较大（%.0f%%），建议调整单题难度标签" % (dev * 100))
        else:
            issues.append("✓ 难度分布与目标基本一致（总偏差 %.0f%%）" % (dev * 100))
    return issues


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def render_report(course, exam, total, kps, qts, G, rows, cols, stats, levels, diff, issues):
    n, m = len(kps), len(qts)
    L = []
    L.append("# 考试双向细目表生成报告")
    L.append("")
    L.append("- 课程: %s" % esc_trunc(course))
    L.append("- 考试: %s" % esc_trunc(exam))
    L.append("- 满分: %d 分 · 知识点 %d 个 · 题型 %d 种" % (total, n, m))
    L.append("")
    L.append("## 1. 知识点 × 题型分值矩阵（单位：分）")
    L.append("")
    L.append("| 知识点 | 权重 | " + " | ".join(esc_trunc(q["name"], 24) for q in qts) + " | 小计 |")
    L.append("| --- | --- | " + " | ".join("---" for _ in range(m)) + " | --- |")
    for i, k in enumerate(kps):
        cells = " | ".join(fmt(G[i][j] / 2) for j in range(m))
        L.append("| %s | %.2f | %s | %s |" % (esc_trunc(k["name"]), k["weight"], cells, fmt(rows[i] / 2)))
    col_sums = [sum(G[i][j] for i in range(n)) / 2 for j in range(m)]
    L.append("| **合计** | **1.00** | %s | **%s** |" % (" | ".join(fmt(x) for x in col_sums), fmt(total)))
    L.append("")
    L.append("## 2. 题型统计")
    L.append("")
    L.append("| 题型 | 题数 | 单题分值 | 小计 | 占比 | 难度标签 | 认知层次 |")
    L.append("|---|---|---|---|---|---|---|")
    for j, q in enumerate(qts):
        s = q["count"] * q["marks"]
        L.append("| %s | %d | %s | %s | %.0f%% | %s | %s |" % (
            esc_trunc(q["name"], 24), q["count"], fmt(q["marks"]), fmt(s),
            s / total * 100 if total else 0, q["difficulty"], q["level"]))
    L.append("")
    L.append("## 3. 难度分布（按题型）")
    L.append("")
    L.append("| 题型 | 易 | 中 | 难 |")
    L.append("|---|---|---|---|")
    easy = med = hard = 0.0
    for name, e0, m0, h0 in stats:
        L.append("| %s | %s | %s | %s |" % (esc_trunc(name, 24), fmt(e0), fmt(m0), fmt(h0)))
        easy += e0
        med += m0
        hard += h0
    L.append("| **合计** | **%s** | **%s** | **%s** |" % (fmt(easy), fmt(med), fmt(hard)))
    L.append("目标占比：%s" % " / ".join("%s %.0f%%" % (d, diff[d] * 100) for d in ALLOWED_DIFF))
    L.append("")
    L.append("## 4. 认知层次（布鲁姆）分布")
    L.append("")
    L.append("| 层次 | 分值 | 占比 |")
    L.append("|---|---|---|")
    for lv in ALLOWED_LEVELS:
        if lv in levels:
            v = levels[lv]
            L.append("| %s | %s | %.0f%% |" % (lv, fmt(v), v / total * 100 if total else 0))
    L.append("")
    L.append("## 5. 校验结论")
    L.append("")
    for it in issues:
        L.append("- " + it)
    L.append("")
    L.append("> 说明：本表为命题参考建议，最终以教研组审定为准；示例与输出均为模拟数据，不涉及真实试卷。")
    return "\n".join(L)


def sample_data():
    return {
        "course": "Python程序设计",
        "exam": "2026年春季学期期末考试",
        "total_marks": 100,
        "knowledge_points": [
            {"name": "基础语法", "weight": 0.2, "level": "了解"},
            {"name": "函数与模块", "weight": 0.25, "level": "理解"},
            {"name": "数据结构", "weight": 0.3, "level": "应用"},
            {"name": "面向对象", "weight": 0.15, "level": "分析"},
            {"name": "异常与文件", "weight": 0.1, "level": "综合"},
        ],
        "question_types": [
            {"name": "单项选择题", "count": 10, "marks": 2, "difficulty": "易"},
            {"name": "判断题", "count": 10, "marks": 1, "difficulty": "易"},
            {"name": "填空题", "count": 10, "marks": 2, "difficulty": "中"},
            {"name": "简答题", "count": 4, "marks": 5, "difficulty": "中"},
            {"name": "综合应用题", "count": 3, "marks": 10, "difficulty": "难"},
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="考试双向细目表生成器（零依赖）")
    ap.add_argument("input", nargs="?", help="输入 JSON 文件路径")
    ap.add_argument("--json", action="store_true", help="同时输出结构化 JSON")
    ap.add_argument("--csv", action="store_true", help="同时输出 CSV 矩阵明细")
    ap.add_argument("--out", help="将 Markdown 报告写入文件")
    ap.add_argument("--demo", action="store_true", help="使用内置示例数据演示")
    args = ap.parse_args()

    V = Validator()
    if args.demo:
        data = sample_data()
    elif args.input:
        data = load_json(args.input, V)
        if data is None:
            for e in V.errors:
                print("✗ " + e)
            return 1
    else:
        ap.print_help()
        return 0

    course = obj_str(data, "course", "顶层", V)
    exam = obj_str(data, "exam", "顶层", V)
    total = obj_int(data, "total_marks", "顶层", V)
    kps = parse_kps(data, V)
    qts = parse_qtypes(data, V)
    diff = parse_diff_target(data, V)
    if total is not None and total > TOTAL_MARKS_MAX:
        V.fail("total_marks 超过上限 %d" % TOTAL_MARKS_MAX)
    if V.errors:
        for e in V.errors:
            print("✗ " + e)
        return 1

    # 权重归一化
    wsum = sum(k["weight"] for k in kps)
    if wsum <= 0:
        V.warn("知识点权重全为 0，已按平均权重分配")
        for k in kps:
            k["weight"] = 1.0 / len(kps)
    else:
        for k in kps:
            k["weight"] /= wsum

    G, rows, cols = build_matrix(kps, qts, total)
    stats = difficulty_stats(qts, cols, diff)
    levels = {}
    for i, k in enumerate(kps):
        levels[k["level"]] = levels.get(k["level"], 0.0) + rows[i] / 2
    easy = sum(s[1] for s in stats)
    med = sum(s[2] for s in stats)
    hard = sum(s[3] for s in stats)
    raw_sum = sum(q["count"] * q["marks"] for q in qts)
    issues = check_validations(cols, rows, total, kps, diff, easy, med, hard, raw_sum)

    report = render_report(course, exam, total, kps, qts, G, rows, cols, stats, levels, diff, issues)

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(report)
        except OSError as e:
            print("✗ 写入文件失败: %s" % e, file=sys.stderr)
            return 1
        print("已生成报告: %s" % args.out)
    else:
        print(report)

    if args.json:
        result = {
            "course": course, "exam": exam, "total_marks": total,
            "knowledge_points": [{"name": k["name"], "weight": round(k["weight"], 4),
                                   "level": k["level"], "assigned_marks": rows[i] / 2}
                                  for i, k in enumerate(kps)],
            "question_types": [{"name": q["name"], "count": q["count"], "marks": q["marks"],
                                 "difficulty": q["difficulty"], "level": q["level"],
                                 "total_marks": sum(G[i][j] for i in range(len(kps))) / 2}
                                for j, q in enumerate(qts)],
            "matrix": [[G[i][j] / 2 for j in range(len(qts))] for i in range(len(kps))],
            "difficulty_summary": {"easy": easy, "medium": med, "hard": hard},
            "level_summary": levels,
            "issues": issues,
        }
        print("\n--- 结构化 JSON ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.csv:
        print("\n--- CSV 明细 ---")
        print("知识点,题型,分值")
        for i, k in enumerate(kps):
            for j in range(len(qts)):
                print("%s,%s,%.1f" % (trunc(k["name"]), trunc(qts[j]["name"]), G[i][j] / 2))

    if V.warnings:
        print("\n[提示]", file=sys.stderr)
        for w in V.warnings:
            print("- " + w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())