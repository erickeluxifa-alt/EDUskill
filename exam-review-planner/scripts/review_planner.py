#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考后讲评备课助手 exam-review-planner v1.0.0
===================================
输入：考试分析与逐题统计（推荐直接复用 exam-score-analyzer 输出的 analysis.json；
     亦可单独提供题目得分率表 qstats（CSV/JSON）与学生成绩单 students（CSV））。
输出：可直接上课的讲评课教学方案：
  - review_plan.md     讲评课教学方案（总体反馈/时间轴/题单/变式/分层/跟踪）
  - review_plan.json   全量结构化结果（供二次处理或前端组件）
  - question_cards.csv 讲题讲单（Excel 直开）
  - tier_students.csv  分层辅导名单（Excel 直开）
  - review_deck.html   自包含讲评课件（桌面/移动端自适应，离线可用）

设计要点：
  * 零第三方依赖、纯标准库、确定性输出（相同输入两次运行结果一致）；
  * 无 shell/eval/网络调用；用户可控文本写 HTML 前统一转义截断，防 XSS；
  * CSV 单元格以 = + - @ 或制表符开头时加 ' 前缀，防公式注入；
  * Markdown 单元格做竖线/换行/控制字符清洗；
  * 数据缺失/非法时按约定降级并告警，不静默出错。

退出码：0=成功（含告警）；2=输入错误（文件缺失/格式非法/口径冲突）；1=内部异常。
"""
import argparse
import csv
import html
import json
import os
import re
import sys

VERSION = "1.0.0"

# ---------- 安全与清洗工具 ----------
_FORMULA_PREFIX = re.compile(r'^[=\+\-@\t]')
_CTRL = re.compile(r'[\x00-\x1f\x7f]')


def csv_cell(v):
    """防 Excel 公式注入：以 = + - @ 或制表符开头的单元格加 ' 前缀。"""
    s = str(v)
    if _FORMULA_PREFIX.match(s):
        return "'" + s
    return s


def md_cell(v):
    """清洗 Markdown 表格单元格：去竖线/换行/控制字符，并将 < > 转全角（防 HTML 注入进 Markdown）。"""
    s = str(v).replace('|', '\uff5c').replace('\r', ' ').replace('\n', ' ')
    s = s.replace('<', '\uff1c').replace('>', '\uff1e')
    return _CTRL.sub('', s)


def esc(v, limit=100):
    """HTML 转义 + 截断（用户可控文本输出到 HTML 前的统一处理）。"""
    s = str(v)
    if len(s) > limit:
        s = s[:limit] + '…'
    return html.escape(s, quote=True)


def to_num(v):
    """宽松转数值；失败/空返回 None。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().strip('%').replace(',', '')
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt_pct(p):
    return "—" if p is None else f"{p * 100:.1f}%"


def fmt2(v):
    return "—" if v is None else f"{v:.2f}"


# ---------- 教学口径常量 ----------
P_LOW = 0.50          # P<0.50 → 必讲（精讲）
P_MID = 0.85          # 0.50≤P<0.85 → 应讲；P≥0.85 → 略讲（自查）
D_GOOD = 0.30         # 区分度好：重点讲思路与典型错误
CAP_PER_Q = 7.0       # 单题精讲时长上限（分钟）
FIXED_OPEN = 3.0      # 开场反馈固定分钟
FIXED_SELF = 5.0      # 自查自纠固定分钟
FIXED_CLOSE = 3.0     # 收尾固定分钟

# ---------- 内置示例数据 ----------
SAMPLE_META = {
    "exam": "2026年秋 · Python 程序设计期中考试",
    "course": "Python 程序设计基础",
    "class_name": "计科2401班",
    "date": "2026-08-26",
    "total_marks": 100.0,
    "pass_rate": 0.60,
    "excellent_rate": 0.85,
    "low_rate": 0.30,
}
SAMPLE_QUESTIONS = [
    {"id": "1", "marks": 8, "kp": "基础语法", "type": "单选", "p": 0.83, "d": 0.25, "text": "变量命名与类型转换"},
    {"id": "2", "marks": 8, "kp": "基础语法", "type": "单选", "p": 0.90, "d": 0.25, "text": "运算符优先级"},
    {"id": "3", "marks": 10, "kp": "流程控制", "type": "单选", "p": 0.78, "d": 0.19, "text": "循环边界条件"},
    {"id": "4", "marks": 10, "kp": "流程控制", "type": "填空", "p": 0.67, "d": 0.27, "text": "分支嵌套与缩进"},
    {"id": "5", "marks": 15, "kp": "函数与模块", "type": "编程", "p": 0.54, "d": 0.31, "text": "函数参数传参与返回值"},
    {"id": "6", "marks": 15, "kp": "文件处理", "type": "编程", "p": 0.46, "d": 0.33, "text": "文件读写与异常处理"},
    {"id": "7", "marks": 16, "kp": "综合应用", "type": "综合", "p": 0.40, "d": 0.37, "text": "成绩统计系统综合题"},
    {"id": "8", "marks": 20, "kp": "综合应用", "type": "综合", "p": 0.42, "d": 0.12, "text": "数据分析与可视化综合"},
]
SAMPLE_STUDENTS = [
    {"sid": "2026010009", "name": "周涛", "total": 82}, {"sid": "2026010011", "name": "徐鹏", "total": 80},
    {"sid": "2026010013", "name": "王佳琪", "total": 78}, {"sid": "2026010001", "name": "陈宇轩", "total": 74},
    {"sid": "2026010004", "name": "李思远", "total": 70}, {"sid": "2026010016", "name": "张梦洁", "total": 68},
    {"sid": "2026010002", "name": "刘子墨", "total": 65}, {"sid": "2026010010", "name": "杨帆", "total": 60},
    {"sid": "2026010007", "name": "黄诗涵", "total": 58}, {"sid": "2026010014", "name": "孙浩然", "total": 55},
    {"sid": "2026010005", "name": "吴欣怡", "total": 50}, {"sid": "2026010008", "name": "郑雨桐", "total": 48},
    {"sid": "2026010003", "name": "赵晨曦", "total": 45}, {"sid": "2026010006", "name": "林志远", "total": 42},
    {"sid": "2026010015", "name": "高艺凡", "total": 38}, {"sid": "2026010012", "name": "罗天佑", "total": 34},
]

VARIANT_POOL = [
    "将题干数值替换（非整数/带单位/加大数据量），重算并核对结果",
    "把条件与结论互换，改编成逆向题让学生反推",
    "换成生活化情境（成绩统计/购物清单/班级事务）重新叙述",
    "把单一对象改为批量对象（列表/多组数据），强化遍历与重复",
    "给出一段错误代码/错误答案，让学生担任评委找出并修复",
    "把一步题拆成两步，先求中间量再求最终结果",
]


class ReviewError(Exception):
    """输入级错误（对应退出码 2）。"""


# ---------- 输入解析 ----------
def read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except OSError as e:
        raise ReviewError(f"无法读取文件 {path}: {e.strerror or e}")
    except json.JSONDecodeError as e:
        raise ReviewError(f"JSON 格式错误 {path}: 第{e.lineno}行 {e.msg}")


def read_csv_records(path, key_aliases):
    """读取 CSV 为 dict 列表；表头按别名归一（中英文/大小写不敏感）。"""
    records = []
    try:
        f = open(path, "r", encoding="utf-8-sig", newline="")
    except OSError as e:
        raise ReviewError(f"无法读取文件 {path}: {e.strerror or e}")
    with f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            raise ReviewError(f"CSV 表头为空: {path}")
        norm = [str(h).strip().lower() for h in header]
        idx = {}
        for i, h in enumerate(norm):
            for canon, names in key_aliases:
                if h in names:
                    idx.setdefault(canon, i)
                    break
        for row in reader:
            if not any(str(c).strip() for c in row):
                continue
            rec = {}
            for canon, i in idx.items():
                if i < len(row) and str(row[i]).strip():
                    rec[canon] = row[i].strip()
            if rec:
                records.append(rec)
    return records


# 列名别名（canon 键对应一组别名）
QSTAT_ALIASES = [
    ("id", ("id", "题号", "qid", "question")),
    ("marks", ("marks", "满分", "分值")),
    ("kp", ("kp", "知识点", "knowledge")),
    ("p", ("p", "得分率", "正确率", "avg", "score")),
    ("d", ("d", "区分度", "disc")),
    ("type", ("type", "题型", "qtype")),
    ("difficulty", ("difficulty", "难度")),
    ("text", ("text", "题干", "题目", "content")),
]
STUDENT_ALIASES = [
    ("sid", ("sid", "学号", "student_id", "id")),
    ("name", ("name", "姓名", "student")),
    ("total", ("total", "总分", "score")),
    ("class", ("class", "班级", "cls")),
]


def pick_key(d, names):
    for k, v in d.items():
        if str(k).strip().lower() in names:
            return v
    return None


def normalize_questions(recs):
    """规整为 q 标准字段；数值解析失败置 None，留给下游告警。"""
    out = []
    for r in recs:
        q = {
            "id": str(pick_key(r, ("id", "题号", "qid", "question")) or "-").strip(),
            "marks": to_num(pick_key(r, ("marks", "满分", "分值"))),
            "kp": (str(pick_key(r, ("kp", "知识点", "knowledge")) or "").strip()) or "未标注知识点",
            "p": to_num(pick_key(r, ("p", "得分率", "正确率", "avg", "score"))),
            "d": to_num(pick_key(r, ("d", "区分度", "disc"))),
            "type": str(pick_key(r, ("type", "题型", "qtype")) or "").strip(),
            "text": str(pick_key(r, ("text", "题干", "题目", "content")) or "").strip(),
        }
        out.append(q)
    return out


def parse_qstats(path):
    """逐题统计表：CSV（列名别名）或 JSON（对象数组，键名别名）。"""
    if path.lower().endswith(".json"):
        data = read_json_file(path)
        if not isinstance(data, list):
            raise ReviewError(f"qstats JSON 应为题目对象数组: {path}")
        return normalize_questions(data)
    return normalize_questions(read_csv_records(path, QSTAT_ALIASES))


def normalize_students(recs):
    """规整学生名单；total 非法置 None 交由分层告警。"""
    out = []
    for r in recs:
        out.append({
            "sid": str(pick_key(r, ("sid", "学号", "student_id", "id")) or "").strip(),
            "name": (str(pick_key(r, ("name", "姓名", "student")) or "").strip()) or "—",
            "total": to_num(pick_key(r, ("total", "总分", "score"))),
        })
    return out


# ---------- 核心 ----------
def build_plan(session_min, questions, students=None, meta=None):
    """逐题分级 → 知识点失分榜 → 时间轴 → 变式 → 分层名单。返回结构化方案。"""
    if not questions:
        raise ReviewError("题目统计为空，无法生成讲评方案")
    warns = []
    session = max(5.0, float(session_min))
    meta = dict(meta or {})
    meta["total_marks"] = to_num(meta.get("total_marks")) or 100.0
    meta["pass_rate"] = to_num(meta.get("pass_rate")) or 0.60
    meta["excellent_rate"] = to_num(meta.get("excellent_rate")) or 0.85
    meta["low_rate"] = to_num(meta.get("low_rate")) or 0.30

    # 1) 逐题分级与讲法建议
    cards = []
    for q in questions:
        qid = str(q.get("id") or "-")
        kp = str(q.get("kp") or "未标注知识点").strip()
        marks = to_num(q.get("marks"), )
        if marks is None or marks <= 0:
            marks = 1.0
            warns.append(f"题目 {qid} 满分缺失/非法，按 1 分计入")
        p = to_num(q.get("p"))
        if p is None:
            p = 0.65
            warns.append(f"题目 {qid} 得分率缺失，按适中 0.65 处理")
        elif not (0.0 <= p <= 1.0):
            warns.append(f"题目 {qid} 得分率 {p:.2f} 越界，已修正到 [0,1]")
            p = min(max(p, 0.0), 1.0)
        d = to_num(q.get("d"))
        if d is None:
            d = 0.0
            warns.append(f"题目 {qid} 区分度缺失，按 0 处理（不参与精讲加权）")
        elif d < 0:
            warns.append(f"题目 {qid} 区分度 {d:.2f} 为负，已修正为 0")
            d = 0.0
        elif d > 1:
            d = 1.0
        if p >= P_MID:
            cls = "略讲"
        elif p >= P_LOW:
            cls = "应讲"
        else:
            cls = "必讲"
        if cls == "必讲":
            if d >= D_GOOD:
                method = "重点讲思路与典型错误，展示错例，追问易错点"
            else:
                method = "全班统一讲概念：核对题意与概念，排除题干歧义后再评"
        elif cls == "应讲":
            method = "先点易错点，再由学生自查订正"
        else:
            method = "小组互查订正，仅口头点关键易错"
        urgency = round((1.0 - p) * 0.6 + max(d, 0.0) * 0.4, 3)
        cards.append({
            "id": qid, "marks": round(marks, 2), "kp": kp,
            "type": str(q.get("type") or "—"), "text": str(q.get("text") or ""),
            "p": p, "d": d, "cls": cls, "method": method,
            "urgency": urgency, "minutes": 0.0, "in_teach": False,
        })
    cards.sort(key=lambda c: (-c["urgency"], str(c["id"])))

    # 2) 知识点聚合（按失分降序）
    kp_map = {}
    for c in cards:
        b = kp_map.setdefault(c["kp"], {"kp": c["kp"], "qids": [], "loss": 0.0, "marks": 0.0})
        b["qids"].append(c["id"])
        b["marks"] += c["marks"]
        b["loss"] += c["marks"] * (1 - c["p"])
    kps = sorted(kp_map.values(), key=lambda b: -b["loss"])

    # 3) 时间轴与逐题时长
    if session < 15:
        open_min = min(FIXED_OPEN, session)
        close_min = min(FIXED_CLOSE, max(0.0, session - open_min))
        teach_min = max(0.0, session - open_min - close_min)
        timeline = [("开场反馈", round(open_min, 1), None),
                    ("核心讲评", round(teach_min, 1), "teach"),
                    ("收尾与作业", round(close_min, 1), None)]
    else:
        budget = max(0.0, session - FIXED_OPEN - FIXED_SELF - FIXED_CLOSE)
        timeline = [
            ("阶段反馈", FIXED_OPEN, None),
            ("自查自纠", FIXED_SELF, None),
            ("核心讲评", round(budget * 0.62, 1), "teach"),
            ("变式训练", round(budget * 0.24, 1), None),
            ("分层辅导", round(budget * 0.14, 1), None),
            ("收尾与作业", FIXED_CLOSE, None),
        ]
    teach_total = sum(t[1] for t in timeline if t[2] == "teach")
    teach_cards = [c for c in cards if c["cls"] in ("必讲", "应讲")]
    if not teach_cards and cards:
        teach_cards = cards[:2]
        warns.append("全班得分率高：无必讲/应讲题，核心讲评改为拔高引导题")
    for c in cards:
        c["in_teach"] = c in teach_cards
    if teach_total > 0 and teach_cards:
        w_sum = sum(max(c["urgency"], 0.05) for c in teach_cards)
        for c in teach_cards:
            t = teach_total * max(c["urgency"], 0.05) / w_sum
            c["minutes"] = round(min(t, CAP_PER_Q), 1)
        delta = round(teach_total - sum(c["minutes"] for c in teach_cards), 1)
        if delta != 0 and teach_cards:
            teach_cards[0]["minutes"] = round(max(1.0, teach_cards[0]["minutes"] + delta), 1)

    # 4) 变式建议（确定性模板轮换）
    for i, c in enumerate(cards):
        templ = VARIANT_POOL[i % len(VARIANT_POOL)]
        c["variant"] = f"{templ}（围绕「{c['kp']}」）"

    # 5) 分层名单
    tiers, tier_advice, tier_note = make_tiers(students, meta, kps, warns)

    counts = {
        "total": len(cards),
        "must": sum(1 for c in cards if c["cls"] == "必讲"),
        "should": sum(1 for c in cards if c["cls"] == "应讲"),
        "skip": sum(1 for c in cards if c["cls"] == "略讲"),
        "teach": len(teach_cards),
        "teach_minutes": round(sum(c["minutes"] for c in teach_cards), 1),
    }
    return {
        "meta": meta, "questions": cards, "kps": kps, "warns": warns,
        "timeline": [{"name": t[0], "minutes": t[1]} for t in timeline],
        "counts": counts, "session_min": session,
        "tier_list": tiers, "tier_advice": tier_advice, "tier_note": tier_note,
    }


def make_tiers(students, meta, kps, warns):
    """按分数线分层：A 优秀提升 / B 巩固 / C 补强。students 可为 None。"""
    advice = {
        "A": "完成错题订正 + 拓展变式，讲评课担任组内小讲师",
        "B": "错题订正 + 课上变式题全做，错题进错题本",
        "C": "结对帮扶 + 精讲题重做，优先掌握必讲知识点，完成后过一小测",
    }
    if not students:
        warns.append("未提供学生名单：分层辅导仅给出分层标准；传入成绩单 CSV 可生成具体名单")
        return [], advice, "未提供成绩单：仅给出分层标准（A≥优秀线 / B≥及格线 / C<及格线）"
    totals = [to_num(s.get("total")) for s in students]
    totals = [t for t in totals if t is not None]
    if not totals:
        warns.append("成绩单中无有效总分，分层名单为空")
        return [], advice, "成绩单无有效总分：无法分层"
    max_score = max(max(totals), float(meta.get("total_marks", 0.0)) or 100.0, 100.0)
    low_line = float(meta.get("low_rate", 0.30)) * max_score
    pass_line = float(meta.get("pass_rate", 0.60)) * max_score
    exc_line = float(meta.get("excellent_rate", 0.85)) * max_score
    topk = [b["kp"] for b in kps[:2]]
    rows, warned_names = [], set()
    for s in students:
        sid = str(s.get("sid") or "").strip()
        name = str(s.get("name") or "—").strip()
        total = to_num(s.get("total"))
        if total is None:
            if name not in warned_names:
                warns.append(f"学生 {name} 总分缺失/非法，跳过分层")
                warned_names.add(name)
            continue
        if total >= exc_line:
            tier, detail = "A", advice["A"]
        elif total >= pass_line:
            tier, detail = "B", advice["B"]
        else:
            tier, detail = "C", advice["C"]
            if topk:
                detail += "；优先任务：" + "、".join(topk)
        rows.append({"tier": tier, "sid": sid, "name": name,
                     "total": round(total, 1), "advice": detail})
    rows.sort(key=lambda t: (t["tier"], -t["total"]))
    return rows, advice, None


# ---------- 输出 ----------
def build_md(plan):
    m = plan.get("meta") or {}
    c = plan["counts"]
    L = []
    A = L.append
    A(f"# 讲评课教学方案：{md_cell(m.get('exam') or '考试')}")
    A("")
    A(f"- 课程：{md_cell(m.get('course') or '—')}　班级：{md_cell(m.get('class_name') or '—')}　考试时间：{md_cell(m.get('date') or '—')}")
    A(f"- 讲评时长：{plan['session_min']:.0f} 分钟；题目 {c['total']} 道（必讲 {c['must']} / 应讲 {c['should']} / 略讲 {c['skip']}）；课堂精讲 {c['teach']} 道，合计 {c['teach_minutes']} 分钟")
    A("")
    A("### 一、总体反馈（约 3 分钟）")
    A("")
    A("展示本次考试总体情况与得分率，肯定进步；说明讲评课环节：自查订正 → 核心讲评 → 变式训练。")
    A("")
    A("### 二、讲评时间轴")
    A("")
    A("| 阶段 | 时长 | 说明 |")
    A("|------|------|------|")
    stage_note = {
        "阶段反馈": "均分/得分率/进步学生；宣布课堂安排",
        "自查自纠": "略讲题小组互查订正",
        "核心讲评": "按下方题单顺序讲评（讲思路 > 讲答案）",
        "变式训练": "当堂完成 1~2 道变式题并互评",
        "分层辅导": "A 层做拓展、B 层巩固变式、C 层重做精讲题（教师巡回）",
        "收尾与作业": "布置订正/变式过关/错题本，预告复测",
        "开场反馈": "总体情况与课堂纪律要求",
    }
    for t in plan["timeline"]:
        A(f"| {t['name']} | {t['minutes']:.0f} 分钟 | {stage_note.get(t['name'], '')} |")
    A("")
    A("### 三、核心讲评题单（按精讲紧迫度降序）")
    A("")
    A("| 题号 | 知识点 | 得分率 | 区分度 | 分类 | 讲法 | 精讲时长 |")
    A("|------|--------|--------|--------|------|------|----------|")
    for q in plan["questions"]:
        if q.get("in_teach"):
            A(f"| {md_cell(q['id'])} | {md_cell(q['kp'])} | {fmt_pct(q['p'])} | {fmt2(q['d'])} | {q['cls']} | {md_cell(q['method'])} | {q['minutes']:.0f}′ |")
    A("")
    A("### 四、略讲题清单（小组自查 + 口头点易错）")
    A("")
    skips = [q for q in plan["questions"] if q["cls"] == "略讲"]
    if skips:
        A("| 题号 | 知识点 | 得分率 | 自查方式 |")
        A("|------|--------|--------|----------|")
        for q in skips:
            A(f"| {md_cell(q['id'])} | {md_cell(q['kp'])} | {fmt_pct(q['p'])} | 小组互查+改错 |")
    else:
        A("（无）")
    A("")
    A("### 五、变式练习建议")
    A("")
    vs = [q["variant"] for q in plan["questions"] if q["cls"] in ("必讲", "应讲")]
    A("\n".join(f"- {md_cell(v)}" for v in vs) if vs else "（无）")
    A("")
    A("### 六、分层辅导")
    A("")
    if plan.get("tier_note"):
        A(f"> {md_cell(plan['tier_note'])}")
        A("")
    tc = {"A": 0, "B": 0, "C": 0}
    for t in plan["tier_list"]:
        tc[t["tier"]] += 1
    A("| 层级 | 人数 | 建议任务 |")
    A("|------|------|----------|")
    for k in ("A", "B", "C"):
        A(f"| {k} | {tc.get(k, 0)} | {md_cell(plan['tier_advice'].get(k, ''))} |")
    A("")
    if plan["tier_list"]:
        A("具体名单见 `tier_students.csv`（含层级、总分与辅导任务）。")
    A("")
    A("### 七、课后跟踪")
    A("")
    A("1. 精讲题重做：当晚完成订正；2. 变式过关：24 小时内完成 1 道变式；3. 错题本收录必讲/应讲题；4. 下周课前 5 分钟复测必讲知识点。")
    A("")
    A("### 八、数据说明")
    A("")
    A(f"- 分类口径：P≥{int(P_MID * 100)}% 略讲、{int(P_LOW * 100)}%≤P<{int(P_MID * 100)}% 应讲、P<{int(P_LOW * 100)}% 必讲；区分度 D≥{D_GOOD:.2f} 按“讲思路”执行，否则“全班统一讲概念”。")
    A(f"- 精讲时长：按紧迫度 0.6×(1−P)+0.4×D 加权分配，单题上限 {CAP_PER_Q:.0f} 分钟；分层按优秀/及格/低分比例（默认 85%/60%，满分 {m.get('total_marks', 100):.0f} 分）分界线划分。")
    A("- 得分率缺失默认 0.65、区分度缺失默认 0，均有提示；所有文本字段均经安全清洗。")
    if plan["warns"]:
        A("")
        A("### 提示（共 {} 条）".format(len(plan["warns"])))
        for w in plan["warns"]:
            A(f"- {md_cell(w)}")
    return "\n".join(L)


def build_deck(plan):
    """自包含 HTML 讲评课件（响应式、可打印、无外部依赖）。"""
    m = plan.get("meta") or {}
    c = plan.get("counts") or {}
    tl = "".join(
        f'<div class="tl"><span class="tl-n">{esc(t["name"])}</span><span class="tl-m">{t["minutes"]:.0f}′</span></div>'
        for t in plan.get("timeline", []))
    qn = "".join(
        f"""<div class="card q-{esc(q['cls'])}">
  <div class="ch"><b>题{esc(q['id'])}</b><span class="qt">{esc(q['type'])} · {q['marks']:.0f}分</span>
  <span class="tag">{esc(q['cls'])}</span></div>
  <div class="bar"><i style="width:{min(100.0, max(0.0, q['p'] * 100)):.0f}%"></i></div>
  <div class="meta">得分率 {fmt_pct(q['p'])} · 区分度 {fmt2(q['d'])}</div>
  <div class="kp">知识点：{esc(q['kp'])}</div>
  {'<div class="txt">' + esc(q['text']) + '</div>' if q.get('text') else ''}
  <div class="how">📌 {esc(q.get('method', ''))}</div>
  <div class="va">✏️ {esc(q.get('variant', ''))}</div>
  {f'<div class="mm">⏱ 精讲 {q["minutes"]:.0f} 分钟</div>' if q.get('in_teach') else ''}
</div>"""
        for q in plan.get("questions", []))
    trs = "".join(
        f"<tr><td>{t['tier']}</td><td>{esc(t['name'])}</td><td>{t['total']:.1f}</td><td>{esc(t.get('advice', ''))}</td></tr>"
        for t in plan.get("tier_list", [])) or "<tr><td colspan=4>未提供名单</td></tr>"
    wrn = "".join(f"<li>{esc(w)}</li>" for w in plan.get("warns", [])) or "<li>无</li>"
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(m.get('exam') or '考后讲评课件')}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:#f2f5f9;color:#2a3546;font-size:14px}}
.wrap{{max-width:1100px;margin:0 auto;padding:20px}}
h1{{font-size:21px;margin:0 0 4px}}h2{{font-size:16px;margin:22px 0 8px;color:#1f3a57}}
.sub{{color:#6b7c8e;margin-bottom:10px}}
.stats{{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}}
.st{{flex:1 1 120px;background:#fff;border-radius:10px;border:1px solid #e3e9f0;padding:10px 14px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.st b{{display:block;font-size:19px;color:#1f3a57}}
.tl-wrap{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}}
.tl{{background:#e8eef6;border-radius:20px;padding:5px 12px;font-size:12px;color:#33506e}}
.tl-n{{font-weight:600}}.tl-m{{color:#c0392b;margin-left:6px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px}}
.card{{background:#fff;border-radius:12px;border:1px solid #e3e9f0;border-left:6px solid #7b9e6b;padding:12px}}
.card.q-必讲{{border-left-color:#c0392b}}.card.q-应讲{{border-left-color:#e67e22}}.card.q-略讲{{border-left-color:#8fa8bf}}
.ch{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-weight:600}}
.qt{{color:#7a8ba0;font-weight:400;font-size:13px}}
.tag{{margin-left:auto;background:#eef2f6;border-radius:12px;padding:2px 10px;font-size:12px;color:#43536b}}
.bar{{height:8px;background:#edf1f5;border-radius:4px;margin:9px 0 7px;overflow:hidden}}
.bar i{{display:block;height:100%;background:#2d7fb8;border-radius:4px}}
.meta{{color:#7a8ba0;font-size:12px}}.kp{{font-weight:600;margin:6px 0 2px}}
.txt{{color:#55677d;font-size:13px;margin:4px 0}}
.how,.va,.mm{{font-size:13px;margin:5px 0;line-height:1.55}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;margin:12px 0}}
th,td{{border-bottom:1px solid #edf1f5;padding:8px 10px;text-align:left}}th{{background:#eef3f8}}
.warn{{background:#fdf0ee;border:1px solid #f3cfc8;border-radius:8px;padding:10px 14px;margin-top:14px}}
@media(max-width:640px){{h1{{font-size:18px}}.grid{{grid-template-columns:1fr}}.st{{flex:1 1 40%}}}}
@media print{{body{{background:#fff}}.card{{break-inside:avoid}}}}
</style></head>
<body><div class="wrap">
<h1>{esc(m.get('exam') or '考后讲评课件')}</h1>
<div class="sub">{esc(m.get('course') or '')} · {esc(m.get('class_name') or '')} · {esc(m.get('date') or '')} · 本节 {plan['session_min']:.0f} 分钟</div>
<div class="stats">
<div class="st"><b>{c.get('total', 0)}</b>总题数</div>
<div class="st"><b>{c.get('must', 0)}</b>必讲题</div>
<div class="st"><b>{c.get('should', 0)}</b>应讲题</div>
<div class="st"><b>{c.get('skip', 0)}</b>略讲题</div>
<div class="st"><b>{c.get('teach_minutes', 0):.0f}′</b>精讲时长</div>
</div>
<h2>⏱ 时间轴</h2>
<div class="tl-wrap">{tl}</div>
<h2>📒 讲评题卡</h2>
<div class="grid">{qn}</div>
<h2>👥 分层辅导名单</h2>
<table><tr><th>层级</th><th>学生</th><th>得分</th><th>建议</th></tr>{trs}</table>
<h2>⚠ 数据提示（{len(plan.get('warns', []))}）</h2>
<ul class="warn">{wrn}</ul>
</div></body></html>"""
    return html_doc


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([csv_cell(x) for x in r])


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_file(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------- CLI ----------
def parse_args(argv):
    ap = argparse.ArgumentParser(
        prog="review_planner.py",
        description="考后讲评备课助手：把逐题统计与成绩单转化为讲评课教学方案（零依赖、离线、确定性输出）。")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--analysis", metavar="PATH", help="复用 exam-score-analyzer 输出的 analysis.json（推荐）")
    src.add_argument("--qstats", metavar="PATH",
                     help="逐题统计 CSV/JSON（列或键：id/marks/kp/p/d/type/text，p 可为得分率或正确率）")
    src.add_argument("--demo", action="store_true", help="内置示例数据跑通全流程")
    ap.add_argument("--students", metavar="PATH", help="学生名单 CSV（学号/姓名/总分 列，可选）")
    ap.add_argument("--exam", metavar="TEXT", help="考试名称（--qstats 模式）")
    ap.add_argument("--course", metavar="TEXT", help="课程名称")
    ap.add_argument("--class-name", metavar="TEXT", help="班级名称")
    ap.add_argument("--date", metavar="TEXT", help="考试日期")
    ap.add_argument("--total-marks", type=float, default=100.0, help="满分（默认 100）")
    ap.add_argument("--pass-rate", type=float, default=0.60, help="及格率阈值（默认 0.60）")
    ap.add_argument("--excellent-rate", type=float, default=0.85, help="优秀阈值（默认 0.85）")
    ap.add_argument("--low-rate", type=float, default=0.30, help="低分阈值（默认 0.30）")
    ap.add_argument("--session", type=float, default=45.0, help="讲评课时长（分钟，默认 45）")
    ap.add_argument("--out-dir", default="output", help="输出目录（默认 output/）")
    ap.add_argument("--no-html", action="store_true", help="不生成 HTML 课件")
    ap.add_argument("--no-md", action="store_true", help="不生成 Markdown 方案")
    ap.add_argument("--quiet", action="store_true", help="只打印摘要")
    return ap.parse_args(argv)


def run(args):
    # 1) 输入装载
    if args.demo:
        questions = [dict(q) for q in SAMPLE_QUESTIONS]
        students = [dict(s) for s in SAMPLE_STUDENTS]
        meta = dict(SAMPLE_META)
        src = "内置演示数据"
    elif args.analysis:
        raw = read_json_file(args.analysis)
        if not isinstance(raw, dict) or "questions" not in raw:
            raise ReviewError(f"{args.analysis} 不是合法的 analysis.json（缺少 questions 字段），"
                              "请确认为 exam-score-analyzer 的输出文件")
        m = raw.get("meta") or {}
        meta = {
            "exam": m.get("exam", ""), "course": m.get("course", ""),
            "class_name": m.get("class_name", m.get("className", "")),
            "date": m.get("date", ""), "total_marks": m.get("total_marks", 100.0),
            "pass_rate": m.get("pass_rate", 0.60), "excellent_rate": m.get("excellent_rate", 0.85),
            "low_rate": m.get("low_rate", 0.30),
        }
        questions = normalize_questions(raw.get("questions") or [])
        students = normalize_students(raw.get("students") or []) if raw.get("students") else None
        src = f"analysis.json（{args.analysis}）"
    else:  # args.qstats
        questions = parse_qstats(args.qstats)
        meta = {
            "exam": args.exam or "考试", "course": args.course or "",
            "class_name": args.class_name or "", "date": args.date or "",
            "total_marks": args.total_marks, "pass_rate": args.pass_rate,
            "excellent_rate": args.excellent_rate, "low_rate": args.low_rate,
        }
        students = None
        src = f"逐题统计（{args.qstats}）"
    # 显式传入的成绩单（--students）优先级最高：覆盖 demo/analysis 内置名单
    if args.students:
        students = normalize_students(read_csv_records(args.students, STUDENT_ALIASES))

    # 2) 计算方案
    plan = build_plan(args.session, questions, students, meta)

    # 3) 写产物
    os.makedirs(args.out_dir, exist_ok=True)
    written = []
    if not args.no_md:
        p = os.path.join(args.out_dir, "review_plan.md")
        write_file(p, build_md(plan))
        written.append(p)
    if not args.no_html:
        p = os.path.join(args.out_dir, "review_deck.html")
        write_file(p, build_deck(plan))
        written.append(p)
    p = os.path.join(args.out_dir, "review_plan.json")
    write_json(p, plan)
    written.append(p)
    p = os.path.join(args.out_dir, "question_cards.csv")
    write_csv(p, ["题号", "知识点", "满分", "得分率", "区分度", "分类", "讲法", "精讲分钟", "变式建议"],
              [[q["id"], q["kp"], q["marks"], f"{q['p'] * 100:.1f}%", f"{q['d']:.2f}",
                q["cls"], q["method"], f"{q['minutes']:.1f}", q["variant"]] for q in plan["questions"]])
    written.append(p)
    p = os.path.join(args.out_dir, "tier_students.csv")
    write_csv(p, ["层级", "学号", "姓名", "总分", "辅导建议"],
              [[t["tier"], t["sid"], t["name"], t["total"], t["advice"]] for t in plan["tier_list"]])
    written.append(p)

    # 4) 摘要
    c = plan["counts"]
    print(f"[ok] 讲评方案已生成（来源：{src}）")
    print(f"  题目 {c['total']} 道 → 必讲 {c['must']} / 应讲 {c['should']} / 略讲 {c['skip']}")
    print(f"  课堂精讲 {c['teach']} 道 · {c['teach_minutes']} 分钟；时间轴 {len(plan['timeline'])} 阶段；分层名单 {len(plan['tier_list'])} 人")
    if plan["warns"]:
        print(f"  提示 {len(plan['warns'])} 条：" + "；".join(plan["warns"][:4]) + ("…" if len(plan["warns"]) > 4 else ""))
    if not args.quiet:
        for p in written:
            print(f"  → {p}")


def main(argv=None):
    args = parse_args(argv) if argv is not None else parse_args(sys.argv[1:])
    try:
        run(args)
    except ReviewError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"[内部异常] {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(None))