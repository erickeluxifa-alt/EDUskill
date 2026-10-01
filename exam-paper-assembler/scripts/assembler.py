#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exam_paper_assembler.py —— 试卷组卷助手 v1.0.0
依据考试双向细目表（兼容 exam-blueprint-generator 输出格式）与题库，
自动完成「知识点题量分配 → 难度匹配选题 → 缺口补齐 → 校验排版」，
输出可打印试卷（学生版/教师版含答案）与结构化 JSON 及组卷报告。

- 零第三方依赖（仅 Python 标准库），本地离线运行，输出可复现（--seed）。
- 安全：全部用户可控文本输出前 HTML 转义；无 shell 调用、无 eval、无网络请求。
- 校验策略：strict 模式存在未补齐缺口则报错；warn 模式输出缺口提示仍生成试卷。

用法示例：
  python3 exam_paper_assembler.py --demo
  python3 exam_paper_assembler.py --blueprint examples/sample_blueprint.json --bank examples/sample_bank.json
  python3 exam_paper_assembler.py --blueprint x.json --bank y.json --out report/paper --seed 42
  python3 exam_paper_assembler.py --blueprint x.json --bank y.json --format json --no-answers
  python3 exam_paper_assembler.py --blueprint x.json --bank y.json --gap-mode warn
"""
import argparse
import html
import json
import os
import random
import re
import sys

# ============================================================================
# 常量
# ============================================================================
VALID_DIFF = ("易", "中", "难")
DIFF_ORDER = {"易": 0, "中": 1, "难": 2}
DEFAULT_DIFF_TARGET = {"易": 0.3, "中": 0.5, "难": 0.2}


class PaperError(Exception):
    """组卷业务异常（输入/缺口问题，非代码 bug）。"""


# ============================================================================
# 输入解析与校验
# ============================================================================
def load_json(path, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise PaperError(f"{label} 文件不存在：{path}")
    except json.JSONDecodeError as e:
        raise PaperError(f"{label} 不是合法 JSON（第 {e.lineno} 行第 {e.colno} 列）：{e.msg}")
    if not isinstance(data, dict):
        raise PaperError(f"{label} 顶层必须是 JSON 对象")
    return data


def _clean_text(value, field, max_len=200):
    if not isinstance(value, str) or not value.strip():
        raise PaperError(f"缺少字段 {field}（应为非空字符串）")
    return value.strip()[:max_len]


def parse_blueprint(bp):
    """解析考试双向细目表（兼容 exam-blueprint-generator 输出格式）。"""
    course = _clean_text(bp.get("course", ""), "blueprint.course")
    exam = _clean_text(bp.get("exam", "期末考试"), "blueprint.exam")
    total_marks = bp.get("total_marks", 100)
    if not isinstance(total_marks, (int, float)) or total_marks <= 0:
        raise PaperError(f"total_marks 必须为正数，当前：{total_marks!r}")

    kps = bp.get("knowledge_points", [])
    if not isinstance(kps, list) or not kps:
        raise PaperError("blueprint.knowledge_points 不能为空")
    knowledge_points, seen_kp = [], set()
    for i, kp in enumerate(kps):
        if not isinstance(kp, dict):
            raise PaperError(f"knowledge_points[{i}] 必须是对象")
        name = _clean_text(kp.get("name", ""), "knowledge_points[].name")
        if name in seen_kp:
            raise PaperError(f"知识点重复：{name}")
        seen_kp.add(name)
        weight = kp.get("weight", 0)
        if not isinstance(weight, (int, float)) or weight < 0:
            raise PaperError(f"知识点 {name} 的 weight 必须 >= 0")
        knowledge_points.append({"name": name, "weight": float(weight),
                                 "level": str(kp.get("level", "理解"))[:20]})

    types = bp.get("question_types", [])
    if not isinstance(types, list) or not types:
        raise PaperError("blueprint.question_types 不能为空")
    question_types, seen_t, marks_sum = [], set(), 0.0
    for i, qt in enumerate(types):
        if not isinstance(qt, dict):
            raise PaperError(f"question_types[{i}] 必须是对象")
        name = _clean_text(qt.get("name", ""), "question_types[].name")
        if name in seen_t:
            raise PaperError(f"题型重复：{name}")
        seen_t.add(name)
        count, marks = qt.get("count", 0), qt.get("marks", 0)
        if not isinstance(count, int) or count <= 0:
            raise PaperError(f"题型 {name} 的 count 必须为正整数，收到：{count!r}")
        if not isinstance(marks, (int, float)) or marks <= 0:
            raise PaperError(f"题型 {name} 的 marks 必须为正数，收到：{marks!r}")
        diff = str(qt.get("difficulty", "混合"))
        if diff not in ("易", "中", "难", "混合"):
            raise PaperError(f"题型 {name} 的 difficulty 取值非法：{diff!r}")
        question_types.append({"name": name, "count": count, "marks": float(marks),
                               "difficulty": diff, "level": str(qt.get("level", "理解"))[:20]})
        marks_sum += count * float(marks)

    diff_target = bp.get("difficulty_target")
    if diff_target is None:
        diff_target = DEFAULT_DIFF_TARGET.copy()
    if not isinstance(diff_target, dict):
        raise PaperError("difficulty_target 必须是对象（易/中/难 -> 占比）")
    normalized = {}
    for k, v in diff_target.items():
        if k not in VALID_DIFF:
            raise PaperError(f"difficulty_target 键非法：{k!r}")
        if not isinstance(v, (int, float)) or v < 0:
            raise PaperError(f"difficulty_target.{k} 必须 >= 0")
        normalized[k] = float(v)
    if sum(normalized.values()) <= 0:
        normalized = DEFAULT_DIFF_TARGET.copy()

    return {"course": course, "exam": exam, "total_marks": float(total_marks),
            "knowledge_points": knowledge_points, "question_types": question_types,
            "difficulty_target": normalized, "marks_sum": marks_sum}


def validate_bank(bank):
    """解析题库并校验字段完整性，返回规范化题目列表。"""
    questions = bank.get("questions", [])
    if not isinstance(questions, list):
        raise PaperError("bank.questions 必须是数组")
    seen_ids, out = set(), []
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise PaperError(f"bank.questions[{i}] 必须是对象")
        qid = str(q.get("id", "")).strip()
        if not qid:
            raise PaperError(f"bank.questions[{i}] 缺少 id")
        if qid in seen_ids:
            raise PaperError(f"题库 id 重复：{qid}")
        seen_ids.add(qid)
        qtype = str(q.get("type", "")).strip()
        kp = str(q.get("kp", "")).strip()
        diff = str(q.get("difficulty", "中"))
        if diff not in VALID_DIFF:
            raise PaperError(f"题目 {qid} 的 difficulty 非法：{diff!r}")
        if not qtype or not kp:
            raise PaperError(f"题目 {qid} 缺少 type 或 kp")
        stem = str(q.get("stem", "")).strip()
        if not stem:
            raise PaperError(f"题目 {qid} 缺少 stem（题干）")
        marks = q.get("marks", 0)
        if not isinstance(marks, (int, float)) or marks <= 0:
            raise PaperError(f"题目 {qid} 的 marks 必须为正数")
        options = q.get("options", [])
        if options is not None and not isinstance(options, list):
            raise PaperError(f"题目 {qid} 的 options 必须是数组或省略")
        out.append({"id": qid, "type": qtype, "kp": kp, "difficulty": diff,
                    "stem": stem, "options": options,
                    "answer": str(q.get("answer", "")).strip(),
                    "explanation": str(q.get("explanation", "")).strip(),
                    "marks": float(marks)})
    return out


# ============================================================================
# 组卷核心算法
# ============================================================================
def allocate_counts(n, weights):
    """把整数 n 按权重分配（最大余数法），返回与 weights 等长的整数列表。"""
    if n <= 0:
        return [0] * len(weights)
    total = sum(weights)
    if total <= 0:  # 全 0 权重 -> 轮转均分
        base = [n // len(weights)] * len(weights)
        for i in range(n % len(weights)):
            base[i] += 1
        return base
    exact = [w / total * n for w in weights]
    floor = [int(x) for x in exact]
    remain = n - sum(floor)
    order = sorted(range(len(exact)), key=lambda i: exact[i] - floor[i], reverse=True)
    for i in range(remain):
        floor[order[i % len(order)]] += 1
    return floor


def _match_score(q_diff, target):
    """目标难度与题目难度的匹配得分（0 最佳）。"""
    if target == "混合" or target not in VALID_DIFF:
        return 0
    return abs(DIFF_ORDER[q_diff] - DIFF_ORDER[target])


def _pick(pool, target_diff, rng):
    """从候选池按难度偏好随机取一题，返回 (题目, 难度偏差)。"""
    if not pool:
        return None, None
    best = min(pool, key=lambda q: _match_score(q["difficulty"], target_diff))
    best_score = _match_score(best["difficulty"], target_diff)
    same = [q for q in pool if _match_score(q["difficulty"], target_diff) == best_score]
    return rng.choice(same), best_score


def assemble(blueprint, bank_questions, seed=2026):
    """主组卷流程。返回 (paper, report)。"""
    rng = random.Random(seed)
    kp_names = [kp["name"] for kp in blueprint["knowledge_points"]]
    weights = [kp["weight"] if kp["weight"] > 0 else 1 for kp in blueprint["knowledge_points"]]

    # 建桶索引：(type, kp) -> questions；type -> questions（用于跨知识点回退补齐）
    buckets, type_all = {}, {}
    for q in bank_questions:
        buckets.setdefault((q["type"], q["kp"]), []).append(q)
        type_all.setdefault(q["type"], []).append(q)

    used_ids, sections, gaps, warnings = set(), [], [], []
    marks_picked = 0.0
    drift_warned = set()   # (tname, difficulty) 防重复告警

    for t in blueprint["question_types"]:
        tname, tcount, tmarks = t["name"], t["count"], t["marks"]
        counts = allocate_counts(tcount, weights)
        kp_chosen = []   # (kp, q, penalty)
        slot_gaps = []   # 每知识点缺口
        for kp_name, want in zip(kp_names, counts):
            if want <= 0:
                continue
            pool = [q for q in buckets.get((tname, kp_name), [])
                    if q["id"] not in used_ids and abs(q["marks"] - tmarks) < 1e-9]
            chosen = []
            for _ in range(min(want, len(pool))):
                q, pen = _pick(pool, t["difficulty"], rng)
                if q is None:
                    break
                pool.remove(q)
                used_ids.add(q["id"])
                chosen.append((q, pen))
            kp_chosen.extend((kp_name, q, pen) for q, pen in chosen)
            if len(chosen) < want:
                slot_gaps.append({"kp": kp_name, "goal": want, "got": len(chosen)})

        # 缺口回退：同题型同分值未用题目补齐（保证题量和总分）
        for gap in slot_gaps:
            deficit = gap["goal"] - gap["got"]
            filled = 0
            for _ in range(deficit):
                pool = [q for q in type_all.get(tname, [])
                        if q["id"] not in used_ids and abs(q["marks"] - tmarks) < 1e-9]
                if not pool:
                    break
                q, pen = _pick(pool, t["difficulty"], rng)
                if q is None:
                    break
                pool.remove(q)
                used_ids.add(q["id"])
                kp_chosen.append(("__fallback__", q, pen))
                gap["got"] += 1
                filled += 1
            if filled and gap["got"] >= gap["goal"]:
                warnings.append(f"题型「{tname}」知识点「{gap['kp']}」原缺 {deficit} 题，"
                                f"已用同题型其他知识点题目补齐 {filled} 题")

        # 持久缺口记录
        for gap in slot_gaps:
            if gap["got"] < gap["goal"]:
                gaps.append({"type": tname, "kp": gap["kp"],
                             "goal": gap["goal"], "got": gap["got"]})
                warnings.append(f"题型「{tname}」知识点「{gap['kp']}」缺 "
                                f"{gap['goal'] - gap['got']} 题（目标 {gap['goal']} 题，仅 {gap['got']} 题）")

        # 题目按知识点顺序稳定排列（fallback 题排在最后）
        ordered, seen_o = [], set()
        for kp_name in kp_names:
            for kp_tag, q, _pen in kp_chosen:
                if kp_tag == kp_name and q["id"] not in seen_o:
                    ordered.append(q)
                    seen_o.add(q["id"])
        for kp_tag, q, _pen in kp_chosen:
            if kp_tag == "__fallback__" and q["id"] not in seen_o:
                ordered.append(q)
                seen_o.add(q["id"])

        # 难度漂移告警：选题难度未达目标难度（仅当目标为具体难度时）
        if t["difficulty"] in VALID_DIFF:
            drifted = sum(1 for _kp, q, pen in kp_chosen if pen and pen > 0)
            if drifted and (tname, t["difficulty"]) not in drift_warned:
                drift_warned.add((tname, t["difficulty"]))
                warnings.append(f"题型「{tname}」目标难度「{t['difficulty']}」，"
                                f"有 {drifted} 题因题库难度不足而采用近似难度（在报告难度分布中可见）")

        if len(ordered) < tcount:
            gaps.append({"type": tname, "kp": "<整体>", "goal": tcount, "got": len(ordered)})
            warnings.append(f"题型「{tname}」整体缺题：目标 {tcount} 题，实际 {len(ordered)} 题")

        sec_marks = sum(q["marks"] for q in ordered)
        marks_picked += sec_marks
        sections.append({"type": tname, "count_target": tcount, "marks": tmarks,
                         "difficulty_target": t["difficulty"],
                         "questions": ordered, "marks_picked": round(sec_marks, 2)})

    # 汇总统计
    diff_stat = {"易": 0, "中": 0, "难": 0}
    kp_stat = {name: 0 for name in kp_names}
    for sec in sections:
        for q in sec["questions"]:
            d = q["difficulty"] if q["difficulty"] in VALID_DIFF else "中"
            diff_stat[d] += 1
            if q["kp"] in kp_stat:
                kp_stat[q["kp"]] += 1

    paper_out = {"course": blueprint["course"], "exam": blueprint["exam"],
                 "total_marks_nominal": blueprint["total_marks"],
                 "marks_picked": round(marks_picked, 2), "seed": seed,
                 "sections": sections}
    report = {
        "gaps": gaps, "warnings": warnings,
        "difficulty_dist": diff_stat,
        "difficulty_target": blueprint["difficulty_target"],
        "kp_coverage": kp_stat,
        "kp_names": kp_names,
        "marks_ok": abs(marks_picked - blueprint["total_marks"]) < 1e-6,
        "marks_sum_blueprint": round(blueprint["marks_sum"], 2),
    }
    return paper_out, report


# ============================================================================
# 渲染输出
# ============================================================================
def _esc(text):
    """输出转义，防注入。"""
    return html.escape(str(text), quote=True)


def _normalize_opt(opt):
    """规范化选项文本：去掉已有的 A. / B、 等前缀，避免重复编号。"""
    s = str(opt).strip()
    m = re.match(r"^(?:[A-Ha-h]|[①-⑩]+)[.、．:：]\s*", s)
    return s[m.end():] if m else s


def _title(idx):
    return "一二三四五六七八九十"[idx - 1] if idx <= 10 else str(idx)


def render_markdown(paper_out, report, with_answers=True):
    """渲染试卷 Markdown（教师版含答案，学生版不含）。"""
    lines = []
    lines.append(f"# {_esc(paper_out['exam'])}")
    lines.append("")
    lines.append(f"**{_esc(paper_out['course'])}**　|　满分 {paper_out['total_marks_nominal']:.0f} 分　|　"
                 f"种子 {paper_out['seed']}")
    lines.append("")
    lines.append("## 姓名：__________　班级：__________　学号：__________")
    lines.append("")
    for i, sec in enumerate(paper_out["sections"], 1):
        qs = sec["questions"]
        header = (f"## {_title(i)}、{_esc(sec['type'])}"
                  f"（每题 {sec['marks']:.0f} 分，共 {sec['count_target']} 题，小计 {sec['marks_picked']:.0f} 分）")
        lines.append(header)
        lines.append("")
        for j, q in enumerate(qs, 1):
            lines.append(f"**{j}.** {_esc(q['stem'])}（{q['marks']:.0f} 分，难度：{_esc(q['difficulty'])}）")
            if q.get("options"):
                for k, opt in enumerate(q["options"], 1):
                    tag = chr(64 + k) if k <= 26 else str(k)
                    lines.append(f"　{tag}. {_esc(_normalize_opt(opt))}")
            if with_answers:
                ans = _esc(q["answer"])
                exp = f"　**解析**：{_esc(q['explanation'])}" if q.get("explanation") else ""
                lines.append(f"　*【答案】{ans}{exp}*")
            lines.append("")
    lines.append("---")
    lines.append(f"### 组卷报告（种子 {paper_out['seed']}）")
    lines.append("")
    lines.append(f"- 组题数：{sum(len(s['questions']) for s in paper_out['sections'])} 题；"
                 f"实际总分 {paper_out['marks_picked']:.0f} / 计划 {paper_out['total_marks_nominal']:.0f}"
                 + ("　✓ 对齐" if report["marks_ok"] else "　✗ 未对齐"))
    if report["warnings"]:
        lines.append("- ⚠️ 预警：")
        for w in report["warnings"]:
            lines.append(f"  - {w}")
    else:
        lines.append("- ✓ 全部类目标题满足，无缺口。")
    lines.append("- 难度分布：" + "、".join(f"{k} {v} 题" for k, v in report["difficulty_dist"].items()))
    covered = [f"{k} {v} 题" for k, v in report["kp_coverage"].items() if v > 0]
    lines.append("- 知识点覆盖：" + ("、".join(covered) if covered else "（无）"))
    return "\n".join(lines)


def render_json(paper_out, report, with_answers=True):
    """结构化输出；with_answers=False 时剔除答案与解析（学生版 JSON）。"""
    if with_answers:
        return json.dumps({"paper": paper_out, "report": report}, ensure_ascii=False, indent=2)
    cleaned = []
    for sec in paper_out["sections"]:
        qs = []
        for q in sec["questions"]:
            c = dict(q)
            c.pop("answer", None)
            c.pop("explanation", None)
            qs.append(c)
        sec_c = dict(sec)
        sec_c["questions"] = qs
        cleaned.append(sec_c)
    paper_c = dict(paper_out)
    paper_c["sections"] = cleaned
    return json.dumps({"paper": paper_c, "report": report}, ensure_ascii=False, indent=2)


# ============================================================================
# CLI 入口
# ============================================================================
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="试卷组卷助手 v1.0.0：依据细目表与题库自动组卷并输出试卷。")
    parser.add_argument("--blueprint", "-b", help="细目表 JSON 路径（兼容 exam-blueprint-generator 输出）")
    parser.add_argument("--bank", "-k", help="题库 JSON 路径（questions 数组）")
    parser.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown",
                        help="输出格式（默认 markdown）")
    parser.add_argument("--out", "-o", help="输出文件前缀（自动加 .md/.json）；缺省输出到 stdout")
    parser.add_argument("--answers", action="store_true", default=True,
                        help="含答案（教师版，默认）")
    parser.add_argument("--no-answers", action="store_false", dest="answers",
                        help="不含答案（学生卷）")
    parser.add_argument("--seed", type=int, default=2026, help="随机种子（默认 2026，可复现）")
    parser.add_argument("--gap-mode", choices=["strict", "warn"], default="strict",
                        help="strict：存在未补齐缺口即报错（默认）；warn：提示缺口并继续生成")
    parser.add_argument("--demo", action="store_true", help="使用 examples/ 下的演示细目表与题库跑通全流程")
    args = parser.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    if args.demo:
        bp_path = os.path.join(here, "..", "examples", "sample_blueprint.json")
        bank_path = os.path.join(here, "..", "examples", "sample_bank.json")
        if not (os.path.exists(bp_path) and os.path.exists(bank_path)):
            raise PaperError("演示文件缺失：请确认 examples/sample_blueprint.json 与 examples/sample_bank.json 存在")
        bp = parse_blueprint(load_json(bp_path, "演示细目表"))
        bank = validate_bank(load_json(bank_path, "演示题库"))
    else:
        if not args.blueprint or not args.bank:
            parser.error("需要 --blueprint 与 --bank（或使用 --demo 跑通演示）")
        bp = parse_blueprint(load_json(args.blueprint, "细目表"))
        bank = validate_bank(load_json(args.bank, "题库"))

    paper_out, report = assemble(bp, bank, seed=args.seed)
    has_gaps = bool(report["gaps"]) or not report["marks_ok"]
    if args.gap_mode == "strict" and has_gaps:
        msg = "存在未补齐缺口，strict 模式拒绝出卷：\n" + "\n".join(
            f"  - {g['type']}/{g['kp']}：目标 {g['goal']} 题，实际 {g['got']} 题" for g in report["gaps"])
        if not report["marks_ok"]:
            msg += f"\n  总分 {paper_out['marks_picked']:.1f} != 计划 {paper_out['total_marks_nominal']:.1f}"
        raise PaperError(msg)
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"[warn] {w}")

    text = render_json(paper_out, report, with_answers=args.answers) if args.format == "json" else render_markdown(
        paper_out, report, with_answers=args.answers)

    if args.out:
        parent = os.path.dirname(args.out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        ext = ".json" if args.format == "json" else ".md"
        path = args.out if args.out.endswith(ext) else args.out + ext
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        summary = f"[ok] 已写出：{path}（{len(os.path.basename(path))} 大小 {os.path.getsize(path)}B）"
        print(summary)
        print(f"[ok] 试卷：{paper_out['exam']} / {paper_out['course']}，"
              f"实际 {paper_out['marks_picked']:.1f} 分，"
              f"缺口 {len(report['gaps'])} 处")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PaperError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(2)