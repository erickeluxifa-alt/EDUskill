#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
credit-progress-checker 学分达标预检助手
=========================================
面向教学秘书 / 教务处 / 班主任 / 毕业班学生：把「培养方案」与「成绩单」
自动比对，按类别核算必修逐门对照、选修/任选学分池达标、总学分校核，
输出可提交教务复核的 Markdown 报告，并支持导出缺课清单 CSV 与结构化 JSON。

零第三方依赖（仅 Python3 标准库），支持中英文表头/字段别名；
仅本地文件读写，无网络访问，不执行任何外部命令。

用法:
  python3 credit_checker.py plan.json transcript.csv
  python3 credit_checker.py plan.json transcript.csv --out report.md --json-out result.json --csv-out missing.csv
  python3 credit_checker.py plan.json transcript.csv --student 2022001 --pass-threshold 60 --pool-any
  python3 credit_checker.py --demo
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import tempfile
from collections import defaultdict

PASS_THRESHOLD_DEFAULT = 60.0

# 等级制 / 中文等级 → 是否通过（数字成绩按阈值判定）
PASS_LEVELS = {
    "A": True, "B": True, "C": True, "D": True, "E": False, "F": False,
    "PASS": True, "P": True, "PR": True, "FAIL": False, "NP": False,
    "优": True, "良": True, "中": True, "合格": True, "及格": True,
    "不及格": False, "不合格": False, "差": False,
}

FIELD_ID = ["id", "编号", "课程编号", "course_id", "code"]
FIELD_NAME = ["name", "名称", "课程名称", "course_name", "title"]
FIELD_CREDITS = ["credits", "学分", "credit", "course_credits", "学分数"]
FIELD_CATEGORY = ["category", "类别", "课程类别", "type", "kind", "课程性质"]
FIELD_SID = ["student_id", "学号", "student_no", "sid", "stuid"]
FIELD_SNAME = ["student_name", "姓名", "stu_name"]
FIELD_GRADE = ["grade", "成绩", "score", "result", "grade_value"]
FIELD_REQ_CREDITS = ["required_credits", "学分要求", "required", "credits", "要求学分", "学分"]

CATEGORY_WORDS = {
    "必修": ["必修", "required", "compulsory", "专业必修", "公共必修", "必修课"],
    "选修": ["选修", "elective", "optional", "专业选修", "限选", "限定选修"],
    "任选": ["任选", "open", "任意选修", "通选", "公选", "通识选修"],
}
CAT_ORDER = {"必修": 0, "选修": 1, "任选": 2}


class CheckError(Exception):
    """输入/校验错误，message 可直接展示给用户。"""


def norm_key(s):
    """规范化匹配键：去空白、全直角括号统一、小写。"""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = s.replace("，", ",").replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", s)


def first_field(row, aliases):
    """按别名集取 dict 首个命中值。"""
    if not isinstance(row, dict):
        return None
    low = {norm_key(k): v for k, v in row.items()}
    for a in aliases:
        v = low.get(norm_key(a))
        if v is not None:
            return v
    return None


def clean_cell(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("null", "none", "n/a", "na", "-", "无", "缺"):
        return None
    return s


def s_text(v):
    s = clean_cell(v)
    return s if s is not None else ""


def to_float(v, field="值"):
    s = clean_cell(v)
    if s is None:
        return None
    t = re.sub(r"[学分个]", "", str(s))
    try:
        return float(t)
    except ValueError:
        raise CheckError(f"字段「{field}」无法识别为数字: {v!r}")


def grade_to_pass(grade, threshold):
    """成绩 → (是否通过, 显示文本)。支持数字 / 等级 / 中文等级。"""
    s = clean_cell(grade)
    if s is None:
        return False, ""
    up = s.upper()
    if up in PASS_LEVELS:
        return PASS_LEVELS[up], up
    try:
        f = float(s)
        return f >= threshold, ("%.1f" % f).rstrip("0").rstrip(".")
    except ValueError:
        return False, s  # 无法识别的文本：未通过，保留原文待人工核对


def normalize_category(cat):
    if cat is None:
        return "必修"
    raw = str(cat).strip()
    low = norm_key(raw)
    for std, words in CATEGORY_WORDS.items():
        if low in {norm_key(w) for w in words}:
            return std
    if "任选" in raw or "任意" in raw or "open" in low:
        return "任选"
    if "必修" in raw or "compulsory" in low or "required" in low:
        return "必修"
    if "选" in raw or "elective" in low:
        return "选修"
    return "必修"


def csv_safe(v):
    """防 CSV 公式注入：以 = + - @ 制表符 开头的单元格加前缀单引号。"""
    if v is None:
        return ""
    s = str(v)
    if s[:1] in ("=", "+", "-", "@", "\t"):
        return "'" + s
    return s


def md_escape(s):
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", "<br>").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------ 输入解析

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except FileNotFoundError:
        raise CheckError(f"文件不存在: {path}")
    except UnicodeDecodeError:
        raise CheckError(f"文件不是 UTF-8（兼容 BOM）编码: {path}")


def load_plan(path):
    """培养方案：JSON（dict）或 CSV（首行表头）。"""
    text = read_text(path)
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext == "csv":
        return _plan_from_csv(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        if "课程" in text or "courses" in text:
            return _plan_from_csv(text)
        raise CheckError(f"培养方案 JSON 解析失败（{e.msg}）: {path}")
    if not isinstance(data, dict):
        raise CheckError("培养方案顶层必须是 JSON 对象（含 courses 数组）")
    return data


def _plan_from_csv(text):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise CheckError("培养方案 CSV 为空")
    header = [h.strip() for h in rows[0]]
    courses = []
    for r in rows[1:]:
        if not any(x.strip() for x in r):
            continue
        d = dict(zip(header, [x.strip() for x in r]))
        cid = s_text(first_field(d, FIELD_ID))
        name = s_text(first_field(d, FIELD_NAME)) or cid or "未命名课程"
        courses.append({
            "id": cid, "name": name,
            "credits": first_field(d, FIELD_CREDITS),
            "category": normalize_category(first_field(d, FIELD_CATEGORY)),
        })
    return {"courses": courses, "major": "", "plan": ""}


def load_transcript(path):
    """成绩单：CSV（首行表头）或 JSON（数组 / {records:[...]}）。"""
    text = read_text(path)
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else "csv"
    if ext == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise CheckError(f"成绩单 JSON 解析失败（{e.msg}）: {path}")
        if isinstance(data, dict):
            data = data.get("records") if data.get("records") is not None else data.get("成绩")
        if not isinstance(data, list):
            raise CheckError("成绩单 JSON 顶层必须是数组或 {records:[...]}")
        return data
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise CheckError("成绩单 CSV 为空")
    header = [h.strip() for h in rows[0]]
    recs = []
    for r in rows[1:]:
        if not any(x.strip() for x in r):
            continue
        d = dict(zip(header, [x.strip() for x in r]))
        # 跳过没有课程标识的行（如"平均学分绩点"等汇总行）
        if first_field(d, FIELD_ID) is None and first_field(d, FIELD_NAME) is None:
            continue
        recs.append(d)
    return recs


# ------------------------------------------------------------------ 匹配与核算

def build_plan_courses(plan):
    """展开培养方案课程并预计算匹配键（id / name / alias）。"""
    courses = plan.get("courses") or []
    if not isinstance(courses, list):
        raise CheckError("培养方案 courses 必须是数组")
    alias_map = {}
    for a in plan.get("aliases") or []:
        n = norm_key(a.get("name", ""))
        if n:
            alias_map[n] = [norm_key(x) for x in (a.get("alias") or []) if norm_key(x)]
    out = []
    for c in courses:
        if not isinstance(c, dict):
            raise CheckError(f"培养方案课程必须为对象（含 name/id）：{c!r}")
        pc = {"plan": c, "id": norm_key(s_text(first_field(c, FIELD_ID))),
              "name": norm_key(s_text(first_field(c, FIELD_NAME))),
              "aliases": set()}
        pc["aliases"] = set(alias_map.get(pc["name"], []))
        out.append(pc)
    return out


def analyze_student(records, plan_courses, threshold):
    """单个学生核算：每课程取最高成绩；必修逐门对照；选修/任选计学分池。"""
    # 1) 每门课的成绩（id 或 name 作键，保留通过与否 + 成绩文本）
    best = {}
    for r in records:
        key = norm_key(s_text(first_field(r, FIELD_ID))) or norm_key(s_text(first_field(r, FIELD_NAME)))
        if not key:
            continue
        passed, txt = grade_to_pass(first_field(r, FIELD_GRADE), threshold)
        cur = best.get(key)
        if cur is None or (passed, txt) >= (cur[0], cur[1]):
            best[key] = (passed, txt)
    # 2) 成绩单学分表（选修池用到）
    credit_by_key = {}
    for r in records:
        key = norm_key(s_text(first_field(r, FIELD_ID))) or norm_key(s_text(first_field(r, FIELD_NAME)))
        if not key:
            continue
        cr = to_float(first_field(r, FIELD_CREDITS), "成绩单学分")
        if cr is not None:
            credit_by_key[key] = cr
    # 3) 按培养方案逐门核算
    cat_earned = defaultdict(float)
    cat_list = defaultdict(list)
    missing_required = []
    plan_keys = set()
    for pc in plan_courses:
        c = pc["plan"]
        cat = normalize_category(c.get("category"))
        cid, cname = pc["id"], pc["name"]
        plan_keys.update(k for k in (cid, cname, *pc["aliases"]) if k)
        try:
            cm = to_float(c.get("credits"), f"课程 {cname or cid} 学分")
        except CheckError:
            cm = None
        hit = next((k for k in (cid, cname) if k and k in best), None)
        passed, txt = best[hit] if hit else (False, "")
        row = {"plan": c, "passed": passed, "grade": txt, "plan_credits": cm,
               "hit": hit, "category": cat}
        cat_list[cat].append(row)
        if cat == "必修":
            if not passed:
                missing_required.append({
                    "name": c.get("name") or c.get("id"),
                    "credits": cm,
                    "grade": txt,
                    "reason": "无成绩" if not txt else "未通过",
                })
            elif cm is not None:
                cat_earned[cat] += cm
            elif hit and credit_by_key.get(hit) is not None:
                cat_earned[cat] += credit_by_key[hit]
        else:
            # 选修/任选：池内通过才计入（--pool-any 时见 main 中的池外并入）
            if passed:
                cat_earned[cat] += cm if cm is not None else (credit_by_key.get(hit) or 0.0)
    # 4) 通过课程的学分池合计（用于 --pool-any 口径）
    pool_total = 0.0
    for key, (p, _) in best.items():
        if p:
            pool_total += credit_by_key.get(key, 0.0)
    return {
        "cat_earned": dict(cat_earned),
        "cat_list": dict(cat_list),
        "missing_required": missing_required,
        "unmatched": [k for k, (p, _) in best.items() if k not in plan_keys],
        "cat_total": sum(cat_earned.values()),
        "pool_total": pool_total,
    }


def apply_pool(an, reqs):
    """--pool-any 口径：通过但未匹配到方案选修课程的学分，按其类别要求学分分配。"""
    extra = an["pool_total"] - an["cat_total"]
    if extra <= 1e-9:
        return an
    for cat in ("选修", "任选"):
        rq = reqs.get(cat)
        if rq is None:
            continue
        need = max(0.0, rq - an["cat_earned"].get(cat, 0.0))
        give = min(need, extra)
        if give > 1e-9:
            an["cat_earned"][cat] = an["cat_earned"].get(cat, 0.0) + give
            an["cat_total"] += give
            extra -= give
    return an


def plan_requirements(plan):
    """读取各类别要求学分：{类别: float}，优先 categories 配置。"""
    req = {}
    cats = plan.get("categories")
    if isinstance(cats, dict):
        for k, v in cats.items():
            std = normalize_category(k)
            if isinstance(v, dict):
                v = first_field(v, FIELD_REQ_CREDITS)
            try:
                f = to_float(v)
            except CheckError:
                f = None
            req[std] = f
    return req


def plan_min_credits(plan):
    for k in ("min_credits", "最低总学分", "总学分"):
        v = plan.get(k)
        if v is not None:
            return to_float(v)
    return None


def build_summaries(plan, plan_courses, by_student, threshold, min_credits, pool_any):
    reqs = plan_requirements(plan)
    summaries = []
    for sid in sorted(by_student):
        recs = by_student[sid]
        an = analyze_student(recs, plan_courses, threshold)
        if pool_any:
            an = apply_pool(an, reqs)
        sname = next((first_field(r, FIELD_SNAME) for r in recs
                      if first_field(r, FIELD_SNAME)), "")
        cats = []
        total_required = 0.0
        ok = True
        shortfall = []
        all_cats = sorted(set(list(an["cat_earned"].keys()) + list(reqs.keys())),
                          key=lambda x: CAT_ORDER.get(x, 3))
        for cat in all_cats:
            required = reqs.get(cat)
            earned = an["cat_earned"].get(cat, 0.0)
            if required is not None:
                total_required += required
                if earned + 1e-9 < required:
                    ok = False
                    shortfall.append(f"{cat}缺 {required - earned:.1f} 学分")
            cats.append({"name": cat, "required": required,
                         "earned": round(earned, 1), "ok": required is None or earned + 1e-9 >= required})
        if an["missing_required"]:
            for m in an["missing_required"]:
                shortfall.append(f"必修课程「{m['name']}」{m['reason']}")
        diff = None
        if min_credits is not None:
            diff = an["cat_total"] - min_credits
            if diff < -1e-9:
                ok = False
                shortfall.append(f"总学分缺 {-diff:.1f}")
        summaries.append({
            "student_id": sid, "student_name": sname,
            "categories": cats,
            "missing_required": an["missing_required"],
            "shortfall": "；".join(shortfall),
            "unmatched": an["unmatched"],
            "total_required": round(total_required, 1) if total_required else None,
            "total_earned": round(an["cat_total"], 1),
            "total_diff": round(diff, 1) if diff is not None else None,
            "total_ok": ok, "ok": ok,
        })
    return summaries


# ------------------------------------------------------------------ 报告

def render_markdown(plan_meta, threshold, min_credits, summaries, pool_any):
    L = []
    L.append("# 学分达标预检报告")
    L.append("")
    L.append(f"- 专业：{plan_meta['major'] or '—'}")
    L.append(f"- 培养方案：{plan_meta['plan'] or '—'}")
    L.append(f"- 及格线：{threshold:g} 分" + (f"，最低总学分：{min_credits:g}" if min_credits else ""))
    L.append(f"- 选修池口径：{'任意通过的课程均计入' if pool_any else '仅培养方案内课程'}")
    L.append(f"- 分析学生数：{len(summaries)}")
    ok_n = sum(1 for s in summaries if s["ok"])
    L.append(f"- **达成人数：{ok_n} / {len(summaries)}**")
    L.append("")
    for s in summaries:
        verdict = "✅ 达到毕业要求" if s["ok"] else "❌ 未达到毕业要求"
        L.append(f"## {md_escape(s['student_id'])} {md_escape(s['student_name'])} — {verdict}")
        L.append("")
        L.append("| 类别 | 要求学分 | 已修学分 | 差额 | 状态 |")
        L.append("|---|---|---|---|---|")
        for c in s["categories"]:
            diff = f"{c['earned'] - c['required']:+.1f}" if c["required"] is not None else "_"
            if c["required"] is not None and abs(c["earned"] - c["required"]) < 1e-9:
                diff = "0.0"
            L.append(f"| {c['name']} | {c['required'] if c['required'] is not None else '—'} | "
                     f"{c['earned']:.1f} | {diff} | {'OK' if c['ok'] else '不足'} |")
        td = f"{s['total_diff']:+.1f}" if s["total_diff"] is not None else "—"
        L.append(f"| **合计** | {s['total_required'] if s['total_required'] is not None else '—'} | "
                 f"**{s['total_earned']:.1f}** | {td} | {'OK' if s['total_ok'] else '不足'} |")
        L.append("")
        if s["missing_required"]:
            L.append("**未通过 / 无成绩的必修课：**")
            L.append("")
            L.append("| 课程 | 学分 | 成绩 | 状态 |")
            L.append("|---|---|---|---|")
            for m in s["missing_required"]:
                L.append(f"| {md_escape(m['name'])} | {m['credits'] if m['credits'] is not None else '—'} | "
                         f"{md_escape(m['grade']) or '—'} | {m['reason']} |")
            L.append("")
        if s["shortfall"]:
            L.append(f"**差额说明：** {md_escape(s['shortfall'])}")
            L.append("")
        if s["unmatched"]:
            shown = "、".join(md_escape(x) for x in s["unmatched"][:8])
            if len(s["unmatched"]) > 8:
                shown += " 等"
            L.append(f"**成绩单中未在培养方案内的课程：** {shown}")
            L.append("")
    return "\n".join(L)


# ------------------------------------------------------------------ 入口

def main(argv=None):
    ap = argparse.ArgumentParser(description="学分达标预检助手（零依赖 Python3）")
    ap.add_argument("plan", nargs="?", help="培养方案 JSON/CSV 路径")
    ap.add_argument("transcript", nargs="?", help="成绩单 CSV/JSON 路径")
    ap.add_argument("--out", help="Markdown 报告写出路径（默认 stdout）")
    ap.add_argument("--json-out", dest="json_out", help="结构化 JSON 输出路径")
    ap.add_argument("--csv-out", dest="csv_out", help="缺课/缺口清单 CSV 输出路径")
    ap.add_argument("--pass-threshold", type=float, default=PASS_THRESHOLD_DEFAULT, help="及格分阈值（默认 60）")
    ap.add_argument("--min-credits", type=float, default=None, help="最低总学分（覆盖培养方案配置）")
    ap.add_argument("--student", default=None, help="仅分析指定学号")
    ap.add_argument("--pool-any", action="store_true", help="选修/任选按『任意通过课程均计入』口径（默认仅计方案内课程）")
    ap.add_argument("--demo", action="store_true", help="运行内置示例并输出报告")
    args = ap.parse_args(argv)

    if args.demo:
        tmp = tempfile.mkdtemp(prefix="cc_demo_")
        demo_plan = {
            "major": "计算机科学与技术", "plan": "2022 级培养方案",
            "min_credits": 43,
            "categories": {"必修": {"required_credits": 33}, "选修": {"required_credits": 6},
                           "任选": {"required_credits": 4}},
            "courses": [
                {"id": "CS101", "name": "高等数学(一)", "credits": 5},
                {"id": "CS102", "name": "大学英语", "credits": 4},
                {"id": "CS103", "name": "程序设计基础", "credits": 4},
                {"id": "CS104", "name": "数据结构", "credits": 4},
                {"id": "CS105", "name": "操作系统", "credits": 3},
                {"id": "CS106", "name": "计算机网络", "credits": 3},
                {"id": "CS107", "name": "数据库原理", "credits": 3},
                {"id": "CS108", "name": "软件工程", "credits": 2},
                {"id": "CS109", "name": "专业英语", "credits": 2},
                {"id": "CS110", "name": "毕业设计", "credits": 3},
            ],
            "aliases": [{"name": "高等数学(一)", "alias": ["高等数学", "高数"]}],
        }
        # 选修/任选池（池内任选若干门）
        for cid, name, cr, cat in (("CS201", "机器学习导论", 2, "选修"),
                                   ("CS202", "云计算技术", 2, "选修"),
                                   ("CS203", "嵌入式系统", 2, "选修"),
                                   ("CS204", "人工智能原理", 2, "选修"),
                                   ("GE101", "世界古代史", 2, "任选"),
                                   ("GE102", "音乐鉴赏", 2, "任选"),
                                   ("GE103", "大学生心理健康", 2, "任选"),
                                   ("GE104", "创新创业实践", 2, "任选")):
            demo_plan["courses"].append({"id": cid, "name": name, "credits": cr, "category": cat})
        demo_csv = (
            "学号,姓名,课程编号,课程名称,成绩,学分,学期\n"
            "2022001,张三,CS101,高等数学(一),85,5,2023秋\n"
            "2022001,张三,CS102,大学英语,72,4,2023秋\n"
            "2022001,张三,CS103,程序设计基础,68,4,2024春\n"
            "2022001,张三,CS104,数据结构,58,4,2024春\n"
            "2022001,张三,CS105,操作系统,91,3,2024秋\n"
            "2022001,张三,CS106,计算机网络,76,3,2024秋\n"
            "2022001,张三,CS107,数据库原理,82,3,2024秋\n"
            "2022001,张三,CS108,软件工程,75,2,2025春\n"
            "2022001,张三,CS109,专业英语,64,2,2025春\n"
            "2022001,张三,CS110,毕业设计,80,3,2025秋\n"
            "2022001,张三,CS201,机器学习导论,88,2,2025春\n"
            "2022001,张三,CS202,云计算技术,77,2,2025春\n"
            "2022001,张三,GE102,音乐鉴赏,92,2,2025春\n"
            "2022004,李四,CS101,高等数学(一),90,5,2023秋\n"
            "2022004,李四,CS102,大学英语,72,4,2023秋\n"
            "2022004,李四,CS103,程序设计基础,68,4,2024春\n"
            "2022004,李四,CS104,数据结构,55,4,2024春\n"
            "2022004,李四,CS104,数据结构,74,4,2025春\n"
            "2022004,李四,CS105,操作系统,良,3,2024秋\n"
            "2022004,李四,CS106,计算机网络,76,3,2024秋\n"
            "2022004,李四,CS107,数据库原理,82,3,2024秋\n"
            "2022004,李四,CS108,软件工程,75,2,2025春\n"
            "2022004,李四,CS109,专业英语,64,2,2025春\n"
            "2022004,李四,CS110,毕业设计,80,3,2025秋\n"
            "2022004,李四,CS201,机器学习导论,88,2,2025春\n"
            "2022004,李四,CS202,云计算技术,77,2,2025春\n"
            "2022004,李四,CS203,嵌入式系统,81,2,2025春\n"
            "2022004,李四,GE101,世界古代史,85,2,2025春\n"
            "2022004,李四,GE103,大学生心理健康,90,2,2025春\n"
        )
        p1 = os.path.join(tmp, "plan.json")
        p2 = os.path.join(tmp, "transcript.csv")
        with open(p1, "w", encoding="utf-8") as f:
            json.dump(demo_plan, f, ensure_ascii=False, indent=2)
        with open(p2, "w", encoding="utf-8") as f:
            f.write(demo_csv)
        args.plan, args.transcript = p1, p2

    if not (args.plan and args.transcript):
        ap.print_help()
        print("\n[错误] 必须提供培养方案与成绩单路径，或使用 --demo", file=sys.stderr)
        return 2

    plan = load_plan(args.plan)
    records = load_transcript(args.transcript)
    if not records:
        raise CheckError("成绩单没有任何有效记录（缺少课程编号/名称/成绩列）")
    plan_courses = build_plan_courses(plan)
    if not plan_courses:
        raise CheckError("培养方案没有课程（courses 为空）")

    min_credits = args.min_credits if args.min_credits is not None else plan_min_credits(plan)

    by_student = defaultdict(list)
    for r in records:
        sid = s_text(first_field(r, FIELD_SID)) or "（无学号）"
        by_student[sid].append(r)
    if args.student:
        if args.student not in by_student:
            raise CheckError(f"成绩单中未找到学号：{args.student}")
        by_student = {args.student: by_student[args.student]}

    summaries = build_summaries(plan, plan_courses, by_student,
                                args.pass_threshold, min_credits, args.pool_any)

    plan_meta = {"major": s_text(plan.get("major")), "plan": s_text(plan.get("plan"))}
    md = render_markdown(plan_meta, args.pass_threshold, min_credits, summaries, args.pool_any)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[OK] 报告已写入 {args.out}")
    else:
        print(md)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"meta": plan_meta, "min_credits": min_credits,
                       "pass_threshold": args.pass_threshold, "pool_any": args.pool_any,
                       "students": summaries}, f, ensure_ascii=False, indent=2)
        print(f"[OK] JSON 已写入 {args.json_out}")

    if args.csv_out:
        with open(args.csv_out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["学号", "姓名", "类别", "课程", "学分", "状态", "成绩", "备注"])
            for s in summaries:
                for m in s["missing_required"]:
                    w.writerow((csv_safe(s["student_id"]), csv_safe(s["student_name"]),
                                "必修", csv_safe(m["name"]), m["credits"],
                                "未通过" if m["grade"] else "无成绩",
                                csv_safe(m["grade"]), ""))
                if s["shortfall"]:
                    w.writerow((csv_safe(s["student_id"]), csv_safe(s["student_name"]),
                                "汇总", "", "", "" if s["ok"] else "未达标",
                                "", csv_safe(s["shortfall"])))
        print(f"[OK] 缺课/缺口清单已写入 {args.csv_out}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckError as e:
        print(f"[错误] {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)