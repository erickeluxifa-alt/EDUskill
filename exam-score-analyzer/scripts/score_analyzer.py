#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
score_analyzer.py — 考后成绩智能分析助手 v1.0.0

面向一线教师 / 年级组长 / 教务管理人员：考试阅卷完成后，
输入「试卷元信息（题目→知识点·满分·题型·难度）+ 学生逐题得分明细（CSV）」，
自动产出：
  1. 班级总体统计（应考/实考/缺考/均分/标准差/优秀率/及格率/低分率/分数段分布）
  2. 试卷质量指标（每题得分率、区分度（高/低 27% 分组）、整卷信度 Cronbach α）
  3. 知识点掌握度诊断与薄弱点排序（讲评方向）
  4. 学生个体画像与预警名单（薄弱知识点、不及格、低分、缺考、未作答）
  5. 讲评课建议（重点讲评题、薄弱知识点讲评顺序、分层作业建议）
输出 Markdown 报告、结构化 JSON、多个 CSV（Excel 直开）与自包含 HTML 可视化报告。

- 零第三方依赖（仅 Python 标准库）、离线运行、确定性输出。
- 安全：无 shell / eval / 网络；用户可控文本输出前 HTML 转义并裁剪；
  CSV 输出带公式注入防护；Markdown 表格字段做竖线/换行清洗。
- 外部系统适配：本工具为独立本地计算器，不依赖具体教务系统；
  成绩明细由教务系统导出或任课教师整理为 CSV 后即可使用（见 examples/）。

用法示例：
  python3 score_analyzer.py --demo
  python3 score_analyzer.py --meta exam_meta.json --scores scores.csv
  python3 score_analyzer.py --meta m.json --scores s.csv --out-dir out/ --bins 10
  python3 score_analyzer.py --meta m.json --scores s.csv --strict --pass-rate 0.6 --excellent-rate 0.85
  python3 score_analyzer.py --meta m.json --scores s.csv --no-html
"""
import argparse
import csv
import html
import json
import math
import os
import random
import re
import statistics
import sys
from collections import Counter

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# 常量：统计口径（教育测量学常用阈值，可被 meta 或 CLI 覆盖）
# ---------------------------------------------------------------------------
DEFAULT_PASS_RATE = 0.60
DEFAULT_EXCELLENT_RATE = 0.85
DEFAULT_LOW_RATE = 0.30
DEFAULT_GROUP_FRACTION = 0.27
DEFAULT_BINS = 10

KP_MASTERED = 0.80
KP_WEAK = 0.60
P_EASY = 0.85
D_GOOD, D_MID, D_LOW = 0.40, 0.30, 0.20
ALERT_WEAK_KP = 2

STUDENT_ALIASES = ["student_id", "sid", "学号", "studentno", "xh"]
NAME_ALIASES = ["name", "姓名", "xm"]
CLASS_ALIASES = ["class", "班级", "classname", "class_name", "bj", "cls"]
QUESTION_COL_RE = re.compile(r"^(?:q|question|题|题目|t)\s*(\d+)$", re.I)
STEM_VALUES = {"", "-", "--", "nan", "na", "none", "null", "无", "未作答", "未答", "缺考", "absent"}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def safe_text(s, limit=200):
    if s is None:
        return ""
    s = str(s)
    s = "".join(ch for ch in s if ch not in "\r\n\t")
    return s[:limit]


def clean_md_cell(s, limit=2000):
    """Markdown 表格单元格清洗（更长上限供长名单等聚合文本使用）。"""
    return safe_text(s, limit).replace("|", "｜")


def excel_safe(v):
    s = str(v)
    if s.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + s
    return s


def esc(s):
    return html.escape(safe_text(s, 200), quote=True)


def fmt(x, nd=1):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    return f"{x:.{nd}f}"


def fmt_pct(x, nd=1):
    if x is None:
        return "-"
    return f"{x * 100:.{nd}f}%"


def p_tag(p):
    if p is None:
        return "无数据"
    if p >= P_EASY:
        return "偏易"
    if p >= 0.60:
        return "适中"
    if p >= 0.40:
        return "偏难"
    return "过难"


def d_tag(d):
    if d is None:
        return "无数据"
    if d >= D_GOOD:
        return "优秀"
    if d >= D_MID:
        return "良好"
    if d >= D_LOW:
        return "勉强"
    return "较差"


def mastery_level(m):
    if m is None:
        return "无数据"
    if m >= KP_MASTERED:
        return "已掌握"
    if m >= KP_WEAK:
        return "基本掌握"
    return "薄弱"


def r100(r):
    return f"{r * 100:.0f}%"


class ScoreError(Exception):
    """业务/输入错误（不是代码缺陷）。"""


# ---------------------------------------------------------------------------
# 试卷元数据
# ---------------------------------------------------------------------------
def _opt_ratio(raw, key, default, label):
    if key not in raw:
        return default
    try:
        v = float(raw[key])
    except (TypeError, ValueError):
        raise ScoreError(f"meta.{key}（{label}）必须是数字")
    if not 0 < v <= 1:
        raise ScoreError(f"meta.{key}（{label}）必须在 (0,1] 区间")
    return v


class Meta:
    def __init__(self, raw):
        if not isinstance(raw, dict):
            raise ScoreError("meta 必须是 JSON 对象")
        self.exam = safe_text(raw.get("exam", "未命名考试"))
        self.course = safe_text(raw.get("course", ""))
        self.date = safe_text(raw.get("date", ""))
        try:
            self.total_marks = float(raw["total_marks"])
        except (KeyError, TypeError, ValueError):
            raise ScoreError("meta.total_marks 必须为数字")
        if self.total_marks <= 0:
            raise ScoreError("meta.total_marks 必须大于 0")
        self.pass_rate = _opt_ratio(raw, "pass_rate", DEFAULT_PASS_RATE, "及格线")
        self.excellent_rate = _opt_ratio(raw, "excellent_rate", DEFAULT_EXCELLENT_RATE, "优秀线")
        self.low_rate = _opt_ratio(raw, "low_rate", DEFAULT_LOW_RATE, "低分线")
        self.group_fraction = _opt_ratio(raw, "group_fraction", DEFAULT_GROUP_FRACTION, "分组比例")
        self.class_name = safe_text(raw.get("className", raw.get("class_name", "")))
        qs = raw.get("questions") or raw.get("items")
        if not isinstance(qs, list) or not qs:
            raise ScoreError("meta.questions 必须是非空数组")
        self.questions = []
        seen = set()
        for i, q in enumerate(qs, 1):
            if not isinstance(q, dict):
                raise ScoreError(f"questions[{i}] 必须是对象")
            qid = str(q.get("id", q.get("qid", i)))
            if qid in seen:
                raise ScoreError(f"题号重复：{qid}")
            seen.add(qid)
            try:
                marks = float(q["marks"])
            except (KeyError, TypeError, ValueError):
                raise ScoreError(f"第 {qid} 题缺少数字 marks")
            if marks <= 0:
                raise ScoreError(f"第 {qid} 题 marks 必须大于 0")
            kp = safe_text(q.get("kp", q.get("knowledge_point", "未分类")), 60)
            qtype = safe_text(q.get("type", ""), 20) or "客观"
            diff = safe_text(q.get("difficulty", ""), 10)
            self.questions.append({"id": qid, "marks": marks, "kp": kp or "未分类",
                                   "type": qtype, "difficulty": diff})
        self.sum_marks = round(sum(q["marks"] for q in self.questions), 6)
        if abs(self.sum_marks - self.total_marks) > 0.51:
            raise ScoreError(
                f"题目满分合计 {self.sum_marks} 与 total_marks {self.total_marks} 相差超过 0.5 分")
        self.kps = list(dict.fromkeys(q["kp"] for q in self.questions))
        self.qmarks = {q["id"]: q["marks"] for q in self.questions}

    def to_dict(self):
        return {"exam": self.exam, "course": self.course, "date": self.date,
                "total_marks": self.total_marks, "pass_rate": self.pass_rate,
                "excellent_rate": self.excellent_rate, "low_rate": self.low_rate,
                "group_fraction": self.group_fraction, "class_name": self.class_name,
                "questions": self.questions, "kps": self.kps, "sum_marks": self.sum_marks,
                "version": VERSION}


def load_meta(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise ScoreError(f"meta 文件不存在：{path}")
    except json.JSONDecodeError as e:
        raise ScoreError(f"meta 不是合法 JSON（第 {e.lineno} 行）：{e.msg}")
    return Meta(raw)


# ---------------------------------------------------------------------------
# 成绩明细（CSV，支持中英文字段别名）
# ---------------------------------------------------------------------------
def _norm(c):
    return re.sub(r"\s+", "", str(c).strip().lower())


def _find_col(colmap, aliases):
    for a in aliases:
        k = _norm(a)
        if k in colmap:
            return colmap[k]
    return None


def parse_scores(path, meta):
    """返回 (students, warns)。
    students: [{"sid","name","class","scores":{qid:float},"missing":[qid],
                "absent":bool,"total":float}]"""
    if not os.path.exists(path):
        raise ScoreError(f"成绩文件不存在：{path}")
    try:
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ScoreError("成绩 CSV 表头为空")
            fieldnames = reader.fieldnames
            raw_rows = list(reader)
    except UnicodeDecodeError:
        raise ScoreError("成绩文件编码需为 UTF-8（可带 BOM）")
    except csv.Error as e:
        raise ScoreError(f"成绩 CSV 解析失败：{e}")

    colmap = {_norm(c): c for c in fieldnames}
    c_sid = _find_col(colmap, STUDENT_ALIASES)
    c_name = _find_col(colmap, NAME_ALIASES)
    c_cls = _find_col(colmap, CLASS_ALIASES)

    q_meta_ids = [q["id"] for q in meta.questions]
    q_cols = {}
    n_idx = 0
    for col in fieldnames:
        if _qnum_from_col(col) is not None:
            if n_idx < len(q_meta_ids):
                q_cols[q_meta_ids[n_idx]] = col
            n_idx += 1
    warns = []
    missing_cols = [qid for qid in q_meta_ids if qid not in q_cols]
    if missing_cols:
        warns.append("CSV 中缺少以下题目列，这些题不做统计：" + ", ".join(missing_cols))

    students = []
    cell_warns = []
    for idx, r in enumerate(raw_rows, 2):
        sid = safe_text((r.get(c_sid) or "").strip() if c_sid else None, 40) or f"S{idx:04d}"
        name = safe_text((r.get(c_name) or "").strip() if c_name else None, 40) or sid
        cls_ = safe_text((r.get(c_cls) or "").strip() if c_cls else None, 40) or ""
        scores, missing = {}, []
        for qid in q_meta_ids:
            col = q_cols.get(qid)
            if not col:
                continue
            rawv = (r.get(col) or "").strip()
            if rawv == "" or rawv.lower() in STEM_VALUES:
                missing.append(qid)
                continue
            try:
                v = float(rawv)
            except (TypeError, ValueError):
                cell_warns.append(f"{name} 第 {qid} 题的值「{safe_text(rawv, 30)}」不是数字，按缺失处理")
                missing.append(qid)
                continue
            if v < 0 or v > meta.qmarks[qid] + 1e-6:
                cell_warns.append(
                    f"{name} 第 {qid} 题得分 {v:g} 超出 [0,{meta.qmarks[qid]:g}]，按缺失处理")
                missing.append(qid)
                continue
            scores[qid] = v
        if not scores and missing:
            students.append({"sid": sid, "name": name, "class": cls_, "scores": {},
                             "missing": [], "absent": True, "total": 0.0})
            continue
        total = round(sum(scores.values()), 4)
        students.append({"sid": sid, "name": name, "class": cls_, "scores": scores,
                         "missing": missing, "absent": False, "total": total})
    warns.extend(cell_warns)
    if not students:
        raise ScoreError("成绩 CSV 中没有数据行")
    return students, warns


def _qnum_from_col(c):
    m = QUESTION_COL_RE.match(_norm(c))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# 核心统计
# ---------------------------------------------------------------------------
def _build_dist(totals, total_marks, width):
    out = []
    n = len(totals)
    low = 0.0
    while low < total_marks - 1e-9 and len(out) < 100:
        hi = min(low + width, total_marks)
        c = 0
        for t in totals:
            if low <= t < hi - 1e-9:
                c += 1
            elif abs(t - total_marks) < 1e-9 and hi >= total_marks - 1e-9:
                c += 1
        out.append({"label": f"{low:.0f}~{hi:.0f}", "count": c, "ratio": c / n})
        low = hi
    if not out:
        out.append({"label": "0~0", "count": 0, "ratio": 0.0})
    return out


def percentile_rank(sorted_totals, t):
    n = len(sorted_totals)
    if n == 0:
        return None
    less = sum(1 for x in sorted_totals if x < t)
    return round(less / n * 100, 1)


def cronbach_alpha(present, qids):
    """Cronbach α：仅用每题都答了的学生；k<2 或完整样本 <4 返回 None。"""
    if len(qids) < 2:
        return None
    complete = [s for s in present if all(q in s["scores"] for q in qids)]
    if len(complete) < 4:
        return None
    item_var = 0.0
    for q in qids:
        vals = [s["scores"][q] for s in complete]
        item_var += statistics.pvariance(vals)
    total_var = statistics.pvariance([s["total"] for s in complete])
    if total_var <= 1e-12:
        return None
    k = len(qids)
    return max(-1.0, min(1.0, (k / (k - 1)) * (1 - item_var / total_var)))


def analyze(meta, students, bins=DEFAULT_BINS):
    """核心计算：返回结果字典（纯数据，供各渲染器使用）。"""
    present = [s for s in students if not s["absent"]]
    absent = [s for s in students if s["absent"]]
    n = len(present)
    if n == 0:
        raise ScoreError("没有可分析的有效学生（全体缺考或成绩为空）")

    qids = [q["id"] for q in meta.questions]
    qmarks = meta.qmarks
    pass_line = meta.total_marks * meta.pass_rate
    excl_line = meta.total_marks * meta.excellent_rate
    low_line = meta.total_marks * meta.low_rate

    totals = [s["total"] for s in present]
    mean = statistics.mean(totals)
    sd = statistics.pstdev(totals) if n >= 2 else None
    median = statistics.median(totals)
    cnt = Counter(totals)
    mode = cnt.most_common(1)[0][0] if cnt.most_common(1)[0][1] > 1 else None
    mx, mn = max(totals), min(totals)

    width = meta.total_marks / max(2, bins)
    dist = _build_dist(totals, meta.total_marks, width)

    n_pass = sum(1 for t in totals if t >= pass_line)
    n_excl = sum(1 for t in totals if t >= excl_line)
    n_low = sum(1 for t in totals if t < low_line)

    # —— 每题统计 ——
    ranked = sorted(present, key=lambda s: s["total"])
    q_stats = []
    for q in meta.questions:
        qid = q["id"]
        vals = [s["scores"][qid] for s in present if qid in s["scores"]]
        m = len(vals)
        if m == 0:
            q_stats.append({"id": qid, "marks": q["marks"], "kp": q["kp"], "type": q["type"],
                            "difficulty": q["difficulty"], "n": 0, "mean": None, "p": None,
                            "full_rate": None, "d": None, "p_tag": "无数据", "d_tag": "无数据"})
            continue
        mean_q = statistics.mean(vals)
        p = mean_q / q["marks"]
        full_rate = sum(1 for v in vals if v >= q["marks"] - 1e-6) / m
        d = None
        if len(present) >= 6:
            k = max(1, int(round(len(present) * meta.group_fraction)))
            k = min(k, len(present) // 2)
            if k >= 2:
                high = ranked[-k:]
                low_grp = ranked[:k]

                rh, rl = rate_high_hand(high, low_grp, qid, qmarks)
                if rh is not None and rl is not None:
                    d = rh - rl
        q_stats.append({"id": qid, "marks": q["marks"], "kp": q["kp"], "type": q["type"],
                        "difficulty": q["difficulty"], "n": m, "mean": mean_q, "p": p,
                        "full_rate": full_rate, "d": d, "p_tag": p_tag(p),
                        "d_tag": d_tag(d) if d is not None else "无数据"})

    # —— 知识点 ——
    kp_stats = []
    for kp in meta.kps:
        qs_kp = [q for q in meta.questions if q["kp"] == kp]
        tot_full = sum(q["marks"] for q in qs_kp)
        if tot_full <= 0:
            continue
        tot_earn = 0.0
        for s in present:
            for q in qs_kp:
                if q["id"] in s["scores"]:
                    tot_earn += s["scores"][q["id"]]
        mastery = min(1.0, tot_earn / (tot_full * n))
        kp_stats.append({"kp": kp, "qids": [q["id"] for q in qs_kp], "questions": len(qs_kp),
                         "marks": tot_full, "mastery": mastery, "level": mastery_level(mastery)})
    kp_stats.sort(key=lambda x: x["mastery"])

    # —— 学生 ——
    sorted_totals = sorted(totals)
    stu_stats = []
    for s in present:
        stu_weak = []
        for k in kp_stats:
            owned = [q for q in k["qids"] if q in s["scores"]]
            if not owned:
                continue
            earn = sum(s["scores"][q] for q in owned)
            if earn / sum(qmarks[q] for q in owned) < KP_WEAK:
                stu_weak.append(k["kp"])
        alerts = []
        if s["total"] < low_line:
            alerts.append("低分")
        elif s["total"] < pass_line:
            alerts.append("不及格")
        if s["missing"]:
            alerts.append(f"有 {len(s['missing'])} 题未作答")
        if len(stu_weak) >= ALERT_WEAK_KP:
            alerts.append(f"薄弱知识点 {len(stu_weak)} 个")
        stu_stats.append({"sid": s["sid"], "name": s["name"], "class": s["class"],
                          "total": s["total"],
                          "percentile": percentile_rank(sorted_totals, s["total"]),
                          "missing": s["missing"], "weak_kps": stu_weak, "alerts": alerts})
    stu_stats.sort(key=lambda x: x["total"], reverse=True)

    # —— 讲评建议 ——
    focus = []
    for q in q_stats:
        if q["p"] is None or q["p"] >= 0.60:
            continue
        if q["d"] is not None and q["d"] >= D_LOW:
            focus.append({"id": q["id"], "p": q["p"], "d": q["d"], "tag": "重点讲评",
                          "reason": "得分率低且区分度较好：学生分化明显，建议课堂重点讲思路与常见错误"})
        else:
            focus.append({"id": q["id"], "p": q["p"], "d": q["d"], "tag": "集中讲评",
                          "reason": "得分率低且区分度不足：可能存在概念性困难或题干问题，建议全班讲评并核对题目"})
    focus.sort(key=lambda x: (x["p"], -(x["d"] or 0)))
    weak_kps = [{"kp": k["kp"], "mastery": k["mastery"],
                 "advice": "课堂重讲 + 变式练习 + 收录错题本"} for k in kp_stats if k["mastery"] < KP_WEAK]
    base = [s for s in stu_stats if s["total"] < pass_line]
    mid = [s for s in stu_stats if pass_line <= s["total"] < excl_line]
    adv = [s for s in stu_stats if s["total"] >= excl_line]
    teaching = {"focus": focus, "weak_kps": weak_kps, "layered": {
        "base": {"count": len(base), "advice": "重做错题 + 针对薄弱知识点的基础练习"},
        "mid": {"count": len(mid), "advice": "薄弱知识点的变式练习 + 限时训练"},
        "adv": {"count": len(adv), "advice": "综合应用题拓展与一题多解"}}}

    return {"meta": meta.to_dict(),
            "n_total": len(students), "n_present": n, "n_absent": len(absent),
            "absent_list": [{"sid": a["sid"], "name": a["name"], "class": a["class"]} for a in absent],
            "totals": {"mean": mean, "sd": sd, "median": median, "mode": mode,
                       "max": mx, "min": mn, "n_pass": n_pass, "n_excl": n_excl, "n_low": n_low,
                       "pass_rate": n_pass / n, "excel_rate": n_excl / n, "low_rate": n_low / n,
                       "p_overall": mean / meta.total_marks},
            "dist": dist, "questions": q_stats, "kps": kp_stats, "students": stu_stats,
            "alpha": cronbach_alpha(present, qids),
            "teaching": teaching,
            "warns": [],
            }


def rate_high_hand(high, low, qid, qmarks):
    def r(grp):
        vals = [s["scores"].get(qid) for s in grp if qid in s["scores"]]
        return statistics.mean(vals) / qmarks[qid] if vals else None
    return r(high), r(low)


# ---------------------------------------------------------------------------
# 渲染：Markdown
# ---------------------------------------------------------------------------
def render_md(res):
    meta = res["meta"]
    t = res["totals"]
    pass_line = meta["total_marks"] * meta["pass_rate"]
    excl_line = meta["total_marks"] * meta["excellent_rate"]
    low_line = meta["total_marks"] * meta["low_rate"]
    L = [f"# 成绩分析报告：{meta['exam']}"]
    if meta["course"] or meta["class_name"]:
        L.append("")
        L.append(f"**课程**：{meta['course'] or '-'}　**日期**：{meta['date'] or '-'}　"
                 f"**班级**：{meta['class_name'] or '-'}")
    L.append("")
    L.append("## 一、总体概况")
    L.append("")
    L.append(f"- 应考 {res['n_present']} 人，缺考 {res['n_absent']} 人，实考有效 {res['n_present']} 人")
    L.append(f"- 平均分 **{fmt(t['mean'])}**（满分 {fmt(meta['total_marks'], 0)}），"
             f"标准差 {fmt(t['sd'])}，中位数 {fmt(t['median'])}"
             f"{'，众数 ' + fmt(t['mode']) if t['mode'] is not None else ''}")
    L.append(f"- 最高分 {fmt(t['max'])}，最低分 {fmt(t['min'])}")
    L.append(f"- 优秀率 {fmt_pct(t['excel_rate'])}（≥{r100(meta['excellent_rate'])}）· "
             f"及格率 {fmt_pct(t['pass_rate'])}（≥{r100(meta['pass_rate'])}）· "
             f"低分率 {fmt_pct(t['low_rate'])}（<{r100(meta['low_rate'])}）")
    L.append(f"- 整体得分率 {fmt_pct(t['p_overall'])} → 整体难度「{p_tag(t['p_overall'])}」")
    if t["sd"] is not None and t["mean"] > 0:
        L.append(f"- 变异系数 {fmt(t['sd'] / t['mean'], 2)}（离散程度参考）")
    L.append("")
    L.append(f"## 二、分数段分布（{len(res['dist'])} 段）")
    L.append("")
    L.append("| 分数段 | 人数 | 占比 | 分布 |")
    L.append("|---|---:|---:|---|")
    for d in res["dist"]:
        bar = "█" * max(1, int(round(d["ratio"] * 40)))
        L.append(f"| {d['label']} | {d['count']} | {fmt_pct(d['ratio'])} | {bar} |")
    L.append("")
    L.append("## 三、试卷质量指标（每题）")
    L.append("")
    L.append("| 题号 | 分值 | 题型 | 知识点 | 有效 | 平均分 | 得分率 | 难度 | 满分率 | 区分度 | 评价 |")
    L.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---|")
    for q in res["questions"]:
        L.append(f"| {q['id']} | {fmt(q['marks'])} | {clean_md_cell(q['type'])} | {clean_md_cell(q['kp'])} "
                 f"| {q['n']} | {fmt(q['mean'])} | {fmt_pct(q['p'])} | {q['p_tag']} "
                 f"| {fmt_pct(q['full_rate'])} | {fmt(q['d'])} | {q['d_tag']} |")
    if res["alpha"] is not None:
        L.append("")
        L.append(f"- 整卷信度 Cronbach α ≈ **{fmt(res['alpha'])}**（α≥0.7 视为内部一致性可接受）")
    else:
        L.append("")
        L.append("- 信度（Cronbach α）：完整作答样本不足（需 ≥4 名且 ≥2 题），未计算")
    L.append("")
    L.append("## 四、知识点掌握度分析")
    L.append("")
    L.append("| 知识点 | 题量 | 满分合计 | 掌握度 | 水平 | 薄弱排序 |")
    L.append("|---|---|---:|---:|---|---|")
    for i, k in enumerate(res["kps"], 1):
        flag = " ⚠" if k["mastery"] < KP_WEAK else ""
        L.append(f"| {clean_md_cell(k['kp'])} | {k['questions']} | {fmt(k['marks'])} "
                 f"| {fmt_pct(k['mastery'])} | {k['level']}{flag} | #{i} |")
    L.append("")
    L.append("## 五、学生个体画像（Top 5）")
    L.append("")
    L.append("| 排名 | 学号 | 姓名 | 班级 | 总分 | 百分位 | 未答 | 薄弱知识点 | 预警 |")
    L.append("|---|---|---|---|---:|---:|---:|---|---|")
    for i, s in enumerate(res["students"][:5], 1):
        L.append(f"| {i} | {clean_md_cell(s['sid'])} | {clean_md_cell(s['name'])} | {clean_md_cell(s['class'])} "
                 f"| {fmt(s['total'])} | {fmt(s['percentile'])} | {len(s['missing'])} "
                 f"| {clean_md_cell('、'.join(s['weak_kps'][:3]) or '-')} "
                 f"| {clean_md_cell('、'.join(s['alerts']) or '-')} |")
    warn_names = [f"{s['name']}（{'、'.join(s['alerts'])}）" for s in res["students"] if s["alerts"]]
    L.append("")
    L.append(f"- 预警学生 {len(warn_names)} 人：" + (clean_md_cell("；".join(warn_names)) or "无"))
    if res["absent_list"]:
        L.append(f"- 缺考 {len(res['absent_list'])} 人："
                 f"{clean_md_cell('、'.join(a['name'] for a in res['absent_list']))}")
    L.append("")
    L.append("## 六、讲评课建议")
    L.append("")
    L.append("### 重点讲评题")
    if res["teaching"]["focus"]:
        for f in res["teaching"]["focus"]:
            L.append(f"- 第 {f['id']} 题（得分率 {fmt_pct(f['p'])}，区分度 {fmt(f['d'])}）：【{f['tag']}】{f['reason']}")
    else:
        L.append("- 无低得分率题目，课堂以梳理归纳为主")
    L.append("")
    L.append("### 薄弱知识点（按掌握度升序）")
    if res["teaching"]["weak_kps"]:
        for k in res["teaching"]["weak_kps"]:
            L.append(f"- {clean_md_cell(k['kp'])}：掌握度 {fmt_pct(k['mastery'])} → {k['advice']}")
    else:
        L.append("- 无薄弱知识点")
    lay = res["teaching"]["layered"]
    L.append("")
    L.append("### 分层作业建议")
    L.append(f"- 基础层（{lay['base']['count']} 人，总分 <{fmt(pass_line, 0)}）：{lay['base']['advice']}")
    L.append(f"- 提升层（{lay['mid']['count']} 人，{fmt(pass_line, 1)}~{fmt(excl_line, 1)}）：{lay['mid']['advice']}")
    L.append(f"- 拓展层（{lay['adv']['count']} 人，≥{fmt(excl_line, 1)}）：{lay['adv']['advice']}")
    L.append("")
    L.append("## 七、数据说明")
    L.append("")
    L.append(f"- 统计口径：及格线 ≥{fmt(pass_line, 1)}（{r100(meta['pass_rate'])}）· "
             f"优秀线 ≥{fmt(excl_line, 1)}（{r100(meta['excellent_rate'])}）· "
             f"低分线 <{fmt(low_line, 1)}（{r100(meta['low_rate'])}）")
    L.append(f"- 区分度：按总分取前/后 {r100(meta['group_fraction'])} 学生的题得分率差；"
             f"信度：Cronbach α")
    L.append(f"- 生成工具：考后成绩智能分析助手 v{VERSION}（本地离线计算，结果可复现）")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# 渲染：CSV（Excel 直开，UTF-8 BOM + 公式注入防护）
# ---------------------------------------------------------------------------
def _write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow([excel_safe(x) for x in r])
    return path


def write_csvs(res, out_dir):
    """写出 4 个 CSV（班级汇总/每题/知识点/学生），返回文件路径列表。"""
    meta = res["meta"]
    t = res["totals"]
    out = []

    rows = [["指标", "数值", "口径"]]
    rows.append(["应考人数", res["n_present"], "实到应考人数"])
    rows.append(["缺考人数", res["n_absent"], ""])
    rows.append(["实考有效人数", res["n_present"], ""])
    rows.append(["平均分", round(t["mean"], 2), f"满分 {meta['total_marks']:g}"])
    rows.append(["标准差", round(t["sd"], 2) if t["sd"] is not None else "", ""])
    rows.append(["中位数", round(t["median"], 2), ""])
    rows.append(["众数", round(t["mode"], 2) if t["mode"] is not None else "", ""])
    rows.append(["最高分", round(t["max"], 2), ""])
    rows.append(["最低分", round(t["min"], 2), ""])
    rows.append(["优秀率%", round(t["excel_rate"] * 100, 2), f"≥{r100(meta['excellent_rate'])}"])
    rows.append(["及格率%", round(t["pass_rate"] * 100, 2), f"≥{r100(meta['pass_rate'])}"])
    rows.append(["低分率%", round(t["low_rate"] * 100, 2), f"<{r100(meta['low_rate'])}"])
    rows.append(["整体得分率%", round(t["p_overall"] * 100, 2), "平均分/满分"])
    if res["alpha"] is not None:
        rows.append(["信度 Cronbach α", round(res["alpha"], 3), "≥0.7 视为可接受"])
    out.append(_write_csv(os.path.join(out_dir, "class_summary.csv"), rows))

    rows = [["题号", "分值", "题型", "知识点", "难度", "有效人数", "平均分",
             "得分率%", "难度评价", "满分率%", "区分度", "区分度评价"]]
    for q in res["questions"]:
        rows.append([q["id"], q["marks"], safe_text(q["type"]), safe_text(q["kp"]) if isinstance(q.get("kp"), str) else q["kp"],
                     safe_text(q["difficulty"]), q["n"],
                     round(q["mean"], 2) if q["mean"] is not None else "",
                     round(q["p"] * 100, 1) if q["p"] is not None else "",
                     q["p_tag"],
                     round(q["full_rate"] * 100, 1) if q["full_rate"] is not None else "",
                     round(q["d"], 3) if q["d"] is not None else "",
                     q["d_tag"]])
    out.append(_write_csv(os.path.join(out_dir, "question_stats.csv"), rows))

    rows = [["知识点", "题量", "满分合计", "掌握度%", "水平", "薄弱"]]
    for k in res["kps"]:
        rows.append([safe_text(k["kp"]), k["questions"], k["marks"],
                     round(k["mastery"] * 100, 1), k["level"],
                     "是" if k["mastery"] < KP_WEAK else "否"])
    out.append(_write_csv(os.path.join(out_dir, "knowledge_stats.csv"), rows))

    rows = [["排名", "学号", "姓名", "班级", "总分", "百分位", "未答题目", "薄弱知识点", "预警"]]
    for i, s in enumerate(res["students"], 1):
        rows.append([i, safe_text(s["sid"]), safe_text(s["name"]), safe_text(s["class"]),
                     round(s["total"], 2), s["percentile"] if s["percentile"] is not None else "",
                     "、".join(s["missing"]), "、".join(s["weak_kps"]), "、".join(s["alerts"])])
    out.append(_write_csv(os.path.join(out_dir, "students.csv"), rows))
    return out


# ---------------------------------------------------------------------------
# 渲染：JSON
# ---------------------------------------------------------------------------
def write_json(res, out_dir):
    path = os.path.join(out_dir, "analysis.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    return path


# ---------------------------------------------------------------------------
# 渲染：HTML（自包含、无外部依赖）
# ---------------------------------------------------------------------------
_H_STYLE = """
:root{--ink:#22314a;--mut:#6b7a93;--line:#e3e9f2;--bg:#f6f8fc;--card:#fff;
        --blue:#3b6fe0;--red:#e05555;--green:#2fa86a;--amber:#e8a13a;}
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
       "Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
  .wrap{max-width:980px;margin:0 auto;padding:20px 16px 48px}
  h1{font-size:22px;margin:6px 0 2px}
  .sub{color:var(--mut);font-size:13px;margin-bottom:18px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
         gap:10px;margin-bottom:20px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;
        padding:10px 12px;text-align:center}
  .card .v{font-size:20px;font-weight:700}
  .card .k{font-size:12px;color:var(--mut)}
  section{background:var(--card);border:1px solid var(--line);border-radius:12px;
          padding:14px 16px;margin-bottom:16px}
  h2{font-size:16px;margin:0 0 10px;border-left:4px solid var(--blue);padding-left:8px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;white-space:nowrap}
  th{color:var(--mut);font-weight:600;background:#f7f9fd}
  .bar{background:#edf2fb;border-radius:6px;height:12px;overflow:hidden;min-width:80px}
  .bar>i{display:block;height:100%;background:linear-gradient(90deg,#5b8def,#3b82e0);
         border-radius:6px}
  .bar.red>i{background:linear-gradient(90deg,#ef7d7d,#e05555)}
  .bar.green>i{background:linear-gradient(90deg,#67c48f,#2fa86a)}
  .tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;
       background:#eef2fb;color:#3b5bb5}
  .tag.warn{background:#fdeeee;color:#c23a3a}
  .layer{margin:6px 0}
  .foot{color:var(--mut);font-size:12px;margin-top:22px;text-align:center}
  .scroll{overflow-x:auto}
  @media (max-width:640px){.cards{grid-template-columns:repeat(2,1fr)}h1{font-size:18px}}
  @media print{body{background:#fff}section{border-color:#ccc;box-shadow:none}}
"""


def _bar_html(p, color="blue"):
    if p is None:
        return '<div class="bar"><i style="width:0%"></i></div>'
    w = max(2.0, min(100.0, p * 100))
    cls = "" if color == "blue" else f" {color}"
    return f'<div class="bar{cls}"><i style="width:{w:.1f}%"></i></div>'


def render_html(res):
    meta = res["meta"]
    t = res["totals"]
    p = []
    p.append("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">")
    p.append("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">")
    p.append(f"<title>成绩分析 · {esc(meta['exam'])}</title><style>{_H_STYLE}</style></head><body>")
    p.append('<div class="wrap">')
    p.append(f"<h1>{esc(meta['exam'])}</h1>")
    p.append(f'<div class="sub">{esc(meta["course"]) or "—"}　·　{esc(meta["date"]) or "—"}'
             f'　·　{esc(meta["class_name"]) or "未分班级"}　·　满分 {fmt(meta["total_marks"], 0)} 分</div>')
    p.append('<div class="cards">')
    cards = [
        ("实考", f"{res['n_present']} 人"),
        ("缺考", f"{res['n_absent']} 人"),
        ("平均分", fmt(t["mean"])),
        ("及格率", pctstr(t["pass_rate"])),
        ("优秀率", pctstr(t["excel_rate"])),
        ("最高分", fmt(t["max"])),
        ("最低分", fmt(t["min"])),
    ]
    for k, v in cards:
        p.append(f'<div class="card"><div class="v">{esc(v)}</div><div class="k">{esc(k)}</div></div>')
    p.append("</div>")

    # 分数段
    p.append("<section><h2>分数段分布</h2><div class=\"scroll\"><table>")
    p.append("<tr><th>分数段</th><th>人数</th><th>占比</th><th style=\"width:40%\">分布</th></tr>")
    for d in res["dist"]:
        p.append(f"<tr><td>{esc(d['label'])}</td><td>{d['count']}</td>"
                 f"<td>{fmt_pct(d['ratio'])}</td><td>{_bar_html(0.001, 'blue')}</td></tr>")
    p.append("</table></div></section>")

    # 试卷质量
    p.append('<section><h2>试卷质量指标（每题）</h2><div class="scroll"><table>')
    p.append("<tr><th>题</th><th>分值</th><th>题型</th><th>知识点</th><th>得分率</th>"
             "<th style=\"width:22%\">得分率条</th><th>难度</th><th>区分度</th><th>评价</th></tr>")
    for q in res["questions"]:
        p.append(f"<tr><td>{esc(q['id'])}</td><td>{fmt(q['marks'])}</td><td>{esc(q['type'])}</td>"
                 f"<td>{esc(q['kp'])}</td><td>{fmt_pct(q['p'])}</td>"
                 f"<td>{_bar_html(q['p'], 'red' if q['p'] is not None and q['p'] < 0.6 else 'green')}</td>"
                 f"<td>{esc(q['p_tag'])}</td><td>{fmt(q['d'])}</td><td>{esc(q['d_tag'])}</td></tr>")
    if res["alpha"] is not None:
        p.append(f"<tr><td colspan='9' style='text-align:left'>整卷信度 Cronbach α ≈ "
                 f"<b>{fmt(res['alpha'])}</b>（≥0.7 视为内部一致性可接受）</td></tr>")
    else:
        p.append("<tr><td colspan='9' style='text-align:left'>信度（Cronbach α）：完整作答样本不足，未计算</td></tr>")
    p.append("</table></div></section>")

    # 知识点
    p.append('<section><h2>知识点掌握度（按薄弱程度排序）</h2><div class="scroll"><table>')
    p.append("<tr><th>知识点</th><th>题量</th><th>满分</th><th>掌握度</th>"
             "<th style='width:22%'>掌握度条</th><th>水平</th></tr>")
    for k in res["kps"]:
        weak = k["mastery"] < KP_WEAK
        bar = _bar_html(k["mastery"], "red" if weak else "blue")
        tag = '<span class="tag warn">薄弱</span>' if weak else '<span class="tag">已掌握</span>' if k["mastery"] >= KP_MASTERED else '<span class="tag">基本掌握</span>'
        p.append(f"<tr><td>{esc(k['kp'])}</td><td>{k['questions']}</td><td>{fmt(k['marks'])}</td>"
                 f"<td>{fmt_pct(k['mastery'])}</td><td>{bar}</td><td>{tag}</td></tr>")
    p.append("</table></div></section>")

    # 学生 top
    p.append('<section><h2>学生个体画像（Top 10）</h2><div class="scroll"><table>')
    p.append("<tr><th>排名</th><th>学号</th><th>姓名</th><th>班级</th><th>总分</th>"
             "<th>百分位</th><th>未答</th><th>薄弱知识点</th><th>预警</th></tr>")
    for i, s in enumerate(res["students"][:10], 1):
        weak = "、".join(s["weak_kps"][:3]) or "-"
        alerts = "、".join(s["alerts"]) or "-"
        p.append(f"<tr><td>{i}</td><td>{esc(s['sid'])}</td><td>{esc(s['name'])}</td>"
                 f"<td>{esc(s['class'])}</td><td>{fmt(s['total'])}</td><td>{fmt(s['percentile'])}</td>"
                 f"<td>{len(s['missing'])}</td><td>{esc(weak)}</td><td>{esc(alerts)}</td></tr>")
    p.append("</table></div>")
    warn_cnt = sum(1 for s in res["students"] if s["alerts"])
    p.append(f"<p style='font-size:13px;margin:8px 0 0'>预警学生 <b>{warn_cnt}</b> 人；"
             f"缺考 <b>{res['n_absent']}</b> 人"
             + ("：" + esc("、".join(a["name"] for a in res["absent_list"])) if res["absent_list"] else "")
             + "</p></section>")
    # 讲评建议
    p.append('<section><h2>讲评课建议</h2><div style="font-size:13px">')
    p.append("<b>重点讲评题：</b></div>")
    if res["teaching"]["focus"]:
        ul = []
        for f in res["teaching"]["focus"]:
            ul.append(f"<div style='margin:6px 0 0 12px'>第 {esc(f['id'])} 题（得分率 {fmt_pct(f['p'])}"
                      f"，区分度 {fmt(f['d'])}）：【{esc(f['tag'])}】{esc(f['reason'])}</div>")
        p.append("".join(ul))
    else:
        p.append("<div style='margin:6px 0 0 12px'>无低得分率题目，课堂以梳理归纳为主。</div>")
    p.append("<div style='margin-top:10px'><b>薄弱知识点：</b></div>")
    if res["teaching"]["weak_kps"]:
        for k in res["teaching"]["weak_kps"]:
            p.append(f"<div style='margin:4px 0 0 12px'>{esc(k['kp'])}（掌握度 {fmt_pct(k['mastery'])}）"
                     f"→ {esc(k['advice'])}</div>")
    else:
        p.append("<div style='margin:4px 0 0 12px'>无薄弱知识点。</div>")
    lay = res["teaching"]["layered"]
    p.append("<div style='margin-top:10px'><b>分层作业建议：</b></div>")
    p.append(f"<div style='margin:4px 0 0 12px'>基础层 {lay['base']['count']} 人：{esc(lay['base']['advice'])}</div>")
    p.append(f"<div style='margin:4px 0 0 12px'>提升层 {lay['mid']['count']} 人：{esc(lay['mid']['advice'])}</div>")
    p.append(f"<div style='margin:4px 0 0 12px'>拓展层 {lay['adv']['count']} 人：{esc(lay['adv']['advice'])}</div>")
    p.append(f"<div style='margin-top:10px;color:#6b7a93'>口径：及格线 {r100(meta['pass_rate'])}"
             f"　优秀线 {r100(meta['excellent_rate'])}　低分线 {r100(meta['low_rate'])}；"
             f"区分度按总分前/后 {r100(meta['group_fraction'])} 学生题得分率差计算。</div>")
    p.append("</section>")
    p.append(f'<div class="foot">考后成绩智能分析助手 v{VERSION} · 本地离线生成 · 结果仅供参考，'
             f'结合教师教学判断使用</div>')
    p.append("</div></body></html>")
    return "".join(p)


def pctstr(x):
    return f"{x * 100:.0f}%"


# ---------------------------------------------------------------------------
# 示例数据（确定性伪随机，供 --demo 与演示）
# ---------------------------------------------------------------------------
def generate_demo(out_dir):
    """写入示例 meta 与成绩 CSV，返回 (meta_path, scores_path)。"""
    meta = {
        "exam": "2026年秋季学期 Python 程序设计期中考试（模拟）",
        "course": "Python 程序设计基础",
        "date": "2026-08-26",
        "total_marks": 100,
        "className": "计科2401班",
        "questions": [
            {"id": "1", "marks": 8, "kp": "基础语法", "type": "单选", "difficulty": "易"},
            {"id": "2", "marks": 8, "kp": "基础语法", "type": "单选", "difficulty": "易"},
            {"id": "3", "marks": 10, "kp": "流程控制", "type": "单选", "difficulty": "中"},
            {"id": "4", "marks": 10, "kp": "流程控制", "type": "填空", "difficulty": "中"},
            {"id": "5", "marks": 15, "kp": "函数与模块", "type": "简答", "difficulty": "中"},
            {"id": "6", "marks": 15, "kp": "文件处理", "type": "简答", "difficulty": "难"},
            {"id": "7", "marks": 17, "kp": "综合应用", "type": "综合", "difficulty": "难"},
            {"id": "8", "marks": 17, "kp": "综合应用", "type": "综合", "difficulty": "难"},
        ],
    }
    rng = random.Random(20260826)
    students = []
    names = ["张伟", "李娜", "王强", "赵敏", "刘洋", "陈静", "杨磊", "黄婷",
             "周涛", "吴丹", "徐鹏", "孙悦", "胡军", "朱琳", "高翔", "林芳",
             "何平", "郭雪", "马超", "罗茜"]  # 20 人
    kp_mastery = {"基础语法": 0.86, "流程控制": 0.72, "函数与模块": 0.55,
                  "文件处理": 0.48, "综合应用": 0.41}
    marks = {q["id"]: q["marks"] for q in meta["questions"]}
    kp_of = {q["id"]: q["kp"] for q in meta["questions"]}
    rows = [["student_id", "name", "class", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"]]
    for i, nm in enumerate(names, 1):
        sid = f"202601{i:04d}"
        ability = rng.gauss(0, 0.12)  # 学生个体能力波动
        row = [sid, nm, "计科2401班"]
        for q in meta["questions"]:
            expect = max(0.05, min(0.98, kp_mastery[q["kp"]] + ability + rng.gauss(0, 0.10)))
            score = round(marks[q["id"]] * expect / 2) * 2  # 取偶数分便于辨识
            score = max(0, min(marks[q["id"]], score))
            row.append(str(score))
        rows.append(row)
    # 加入缺考与部分缺答样例
    rows.append(["202601021", "钱伟", "计科2401班", "", "", "", "", "", "", "", ""])
    rows.append(["202601022", "孙静", "计科2401班", "8", "8", "10", "8", "10", "6", "", ""])

    meta_path = os.path.join(out_dir, "example_exam_meta.json")
    scores_path = os.path.join(out_dir, "example_scores.csv")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(scores_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerows(rows)
    return meta_path, scores_path


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="考后成绩智能分析助手（本地离线，零依赖）")
    ap.add_argument("--meta", help="试卷元信息 JSON（题目→知识点·满分·题型·难度）")
    ap.add_argument("--scores", help="学生逐题得分 CSV")
    ap.add_argument("--out-dir", default="output", help="输出目录（默认 output/）")
    ap.add_argument("--bins", type=int, default=DEFAULT_BINS, help=f"分数段数量（默认 {DEFAULT_BINS}）")
    ap.add_argument("--pass-rate", type=float, help="及格线比例（默认 0.60）")
    ap.add_argument("--excellent-rate", type=float, help="优秀线比例（默认 0.85）")
    ap.add_argument("--low-rate", type=float, help="低分线比例（默认 0.30）")
    ap.add_argument("--group-fraction", type=float, help="区分度高低分组比例（默认 0.27）")
    ap.add_argument("--no-html", action="store_true", help="不生成 HTML 可视化报告")
    ap.add_argument("--strict", action="store_true", help="存在任何告警即失败退出（码 2）")
    ap.add_argument("--demo", action="store_true", help="生成内置示例数据并跑通全流程")
    ap.add_argument("--version", action="version", version=f"score_analyzer {VERSION}")
    args = ap.parse_args(argv)

    try:
        out_dir = os.path.abspath(args.out_dir)
        os.makedirs(out_dir, exist_ok=True)
        if args.demo:
            if args.meta or args.scores:
                raise ScoreError("--demo 模式不要同时传入 --meta/--scores")
            meta_path, scores_path = generate_demo(out_dir)
        else:
            if not args.meta or not args.scores:
                raise ScoreError("请提供 --meta 与 --scores（或使用 --demo 试跑）")
            meta_path, scores_path = args.meta, args.scores

        meta = load_meta(meta_path)
        for key, attr in (("--pass-rate", "pass_rate"), ("--excellent-rate", "excellent_rate"),
                          ("--low-rate", "low_rate"), ("--group-fraction", "group_fraction")):
            v = getattr(args, attr.replace("-", "_"))
            if v is not None:
                if not 0 < v <= 1:
                    raise ScoreError(f"{key} 必须在 (0,1] 区间")
                setattr(meta, attr, v)

        students, warns = parse_scores(scores_path, meta)
        res = analyze(meta, students, bins=args.bins)
        res["warns"] = warns

        md = render_md(res)
        with open(os.path.join(out_dir, "analysis_report.md"), "w", encoding="utf-8") as f:
            f.write(md)
        files = write_csvs(res, out_dir)
        write_json(res, out_dir)
        files.append(os.path.join(out_dir, "analysis.json"))
        if not args.no_html:
            html_path = os.path.join(out_dir, "report.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(render_html(res))
            files.append(html_path)
        files.insert(0, os.path.join(out_dir, "analysis_report.md"))
    except ScoreError as e:
        print(f"[输入错误] {e}", file=sys.stderr)
        return 2
    except Exception as e:  # 兜底：把意外异常转为友好提示，避免裸堆栈
        print(f"[错误] {e}", file=sys.stderr)
        return 1

    t = res["totals"]
    print(f"已完成成绩分析：{meta.exam}")
    print(f"  实考 {res['n_present']} 人（缺考 {res['n_absent']}）｜平均分 {fmt(t['mean'])} "
          f"｜及格率 {fmt_pct(t['pass_rate'])} ｜优秀率 {fmt_pct(t['excel_rate'])}")
    if warns:
        print("提示：")
        for w in warns[:10]:
            print(f"  - {w}")
        if len(warns) > 10:
            print(f"  …另有 {len(warns) - 10} 条提示，详见报告")
    print("输出文件：")
    for fp in files:
        print(f"  {fp}")
    if args.strict and warns:
        print("[strict] 存在告警，按失败处理", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())