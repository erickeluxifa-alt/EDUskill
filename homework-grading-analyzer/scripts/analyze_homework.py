#!/usr/bin/env python3
"""homework-grading-analyzer: 批量批改与学情诊断 Skill"""
import argparse, csv, json, sys
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

FW = str.maketrans("ＡＢＣＤＥａｂｃｄｅ１２３４５６７８９０", "ABCDEabcde1234567890")

def norm(s):
    if s is None: return ""
    return str(s).strip().translate(FW).lower()

def load_key(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    qs = raw.get("questions", [])
    if not qs:
        raise ValueError("answer_key questions 为空")
    seen = set()
    for q in qs:
        q["id"] = int(q["id"])
        if q["id"] in seen: raise ValueError(f"题号重复:{q['id']}")
        seen.add(q["id"])
        q.setdefault("type","single_choice")
        q.setdefault("points",0)
        q.setdefault("knowledge_point","未分类")
    raw.setdefault("total_points", sum(float(q["points"]) for q in qs))
    return raw

def parse_csv(path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fn_map = {fn.lower().strip(): fn for fn in reader.fieldnames}
        def fc(*cands):
            for c in cands:
                lc = c.lower()
                if lc in fn_map: return fn_map[lc]
            return None
        col_sid = fc("student_id","sid","学号")
        col_nm = fc("name","姓名")
        for i,row in enumerate(reader,1):
            sid = (row[col_sid] or "").strip() if col_sid else f"S{i:03d}"
            nm = (row[col_nm] or "").strip() if col_nm else sid
            if not sid: sid = f"S{i:03d}"
            row_out = {"student_id":sid,"name":nm,"answers":{}}
            yield row_out, row, reader.fieldnames



def fq(fm, qi):
    """find question column"""
    cs = [f"q{qi}", f"Q{qi}", f"question_{qi}", str(qi), f"t{qi}"]
    for c in cs:
        if c.lower() in fm: return fm[c.lower()]
    return None

def gv(r, v):
    """get value safely"""
    return (r.get(v) or "").strip() if r else ""

def gr_sc(r, e):
    ok = norm(r) == norm(e)
    return 1.0 if ok else 0.0

def gr_mc(r, e):
    eo = {c.upper() for c in norm(e) if c.isalpha()}
    go = {c.upper() for c in norm(r) if c.isalpha()}
    if go == eo: return 1.0
    if go and go <= eo: return 0.5
    return 0.0

def gr_fb(r, qs):
    acc = [str(a) for a in qs.get("accepted_answers", [])]
    if isinstance(qs.get("answer"), str):
        acc = acc or [qs["answer"]]
    rc = r.strip().lower()
    for a in acc:
        if rc == str(a).strip().lower(): return 1.0
    pks = qs.get("partial_keywords") or []
    pratio = float(qs.get("partial_ratio", .5))
    if qs.get("allow_partial_credit") and pks:
        hits = sum(1 for k in pks if k.lower() in rc)
        rt = min(hits/max(len(pks),1), 1)
        if rt >= pratio: return round(rt*.5+.3, 4)
    return 0.0


def gr_num(r, e, tol=None):
    """numeric tolerance match"""
    try:
        rv = float(str(r).replace(",", "").strip())
        ev = float(e)
    except Exception:
        return 0.0
    if tol is None:
        tol = abs(ev) * 0.01 + 1e-9
    return 1.0 if abs(rv - ev) <= float(tol) else 0.0


def gr_sa(r, qs):
    """short answer: keyword-based scoring"""
    acc = [str(a) for a in qs.get("accepted_answers", [])]
    rc = r.strip().lower()
    for a in acc:
        al = str(a).strip().lower()
        if al and al in rc:
            return 1.0
    pks = qs.get("partial_keywords") or []
    pratio = float(qs.get("partial_ratio", .5))
    if pks and len(pks) > 0:
        hits = sum(1 for k in pks if k.lower() in rc)
        rt = min(hits / max(len(pks), 1), 1)
        if rt > 0:
            base = rt * .6 + .2
            if rt >= pratio:
                return round(min(base, .95), 4)
            return round(max(.15, base * .5), 4)
    return 0.0


GRADERS = {
    "single_choice": lambda r, a, q: gr_sc(r, a),
    "true_false":    lambda r, a, q: gr_sc(r, a),
    "multi_choice":  lambda r, a, q: gr_mc(r, a),
    "fill_blank":    lambda r, a, q: gr_fb(r, q),
    "numeric":       lambda r, a, q: gr_num(r, a, (q or {}).get("tolerance")),
    "short_answer":  lambda r, a, q: gr_sa(r, q),
}


def tier(pct):
    if pct >= .9: return "A"
    if pct >= .75: return "B"
    if pct >= .6: return "C"
    return "D"


ADVICE = {
    "A": "保持优秀，建议尝试拓展性学习任务",
    "B": "整体掌握良好，针对薄弱知识点做专项巩固",
    "C": "存在明显薄弱环节，建议增加练习并重点辅导",
    "D": "基础掌握不足，需系统性复习与重难点突破",
}


def grade_all(key_path, csv_path):
    ak = load_key(key_path)
    students = list(parse_csv(csv_path))
    fn_map_global = None
    results = []

    for so, raw, fns in students:
        if fn_map_global is None:
            fn_map_global = {fn.lower().strip(): fn for fn in (fns or [])}

        total_pts = float(ak["total_points"])
        earned = 0.0
        detail = []
        kp_hits = defaultdict(lambda: [0, 0])

        for q in ak["questions"]:
            qi = int(q["id"])
            col = fq(fn_map_global, qi)
            resp = gv(raw, col) if col else ""
            ans = str(q.get("answer", ""))
            t = q["type"]
            g_fn = GRADERS.get(t, gr_sc)
            sc = g_fn(resp, ans, q)
            pts = sc * float(q["points"])
            earned += pts

            k = q["knowledge_point"]
            kp_hits[k][1] += 1
            if sc >= .999: kp_hits[k][0] += 1

            detail.append({
                "qid": qi, "type": t, "response": resp, "answer": ans,
                "score_ratio": round(sc, 4),
                "points_awarded": round(pts, 4),
                "correct": sc >= .999, "kp": k,
            })

        pct = round(earned / max(total_pts, 1e-9), 4)
        stier = tier(pct)
        advice = ADVICE[stier]
        weak_kps = [k for k, h in kp_hits.items() if h[1] > 0 and h[0]/h[1] < .6]
        if weak_kps:
            advice += f"；薄弱知识点：{'、'.join(weak_kps)}"

        results.append({
            **so,
            "answers_detail": detail,
            "total_earned": round(earned, 4),
            "total_possible": total_pts,
            "pct": pct, "tier": stier, "advice": advice,
            "weak_kps": weak_kps,
        })

    return {
        "key_meta": {
            "title": ak.get("title"), "subject": ak.get("subject"),
            "date": ak.get("date"),
            "n_questions": len(ak["questions"]),
            "total_points": ak["total_points"],
        },
        "students": results,
    }


def aggregate(report):
    n = len(report["students"])
    if n == 0:
        return {"class_size": 0}

    avgs = [s["pct"] for s in report["students"]]
    pq = defaultdict(list)
    for s in report["students"]:
        for d in s["answers_detail"]:
            pq[d["qid"]].append(d["score_ratio"])

    pq_stats = {
        qid: {
            "avg_correct_rate": round(sum(v)/len(v), 4),
            "wrong_rate": round(sum(x < .999 for x in v)/len(v), 4),
            "n": len(v),
        }
        for qid, v in pq.items()
    }

    kp_buckets = defaultdict(list)
    for s in report["students"]:
        for d in s["answers_detail"]:
            kp_buckets[d["kp"]].append(d["score_ratio"])

    kp_stats = {
        kk: {"avg_mastery": round(sum(v)/len(v), 4), "count": len(v)}
        for kk, v in kp_buckets.items()
    }

    weak_kps = [kk for kk, v in kp_stats.items() if v["avg_mastery"] < .6]
    sorted_scores = sorted(avgs)

    return {
        "class_size": n,
        "average": round(sum(avgs)/len(avgs), 4),
        "median": round(sorted_scores[len(sorted_scores)//2], 4),
        "high": round(max(avgs), 4), "low": round(min(avgs), 4),
        "pass_rate": round(sum(1 for v in avgs if v >= .6) / n, 4),
        "per_question_stats": pq_stats,
        "kp_stats": kp_stats,
        "weak_kps": weak_kps,
        "tier_counts": dict(Counter(s["tier"] for s in report["students"])),
    }


def render_md(meta, agg, students):
    L = []
    L.append("# 批量批改与学情诊断报告\n")
    title = meta.get("title") or "（未命名测验）"
    subj = meta.get("subject") or ""
    date_s = meta.get("date") or ""
    L.append(f"**标题**：{title}  ")
    if subj: L.append(f"**学科**：{subj}  ")
    if date_s: L.append(f"**日期**：{date_s}")
    L.append("")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L.append(f"_生成时间：{ts}_\n")

    n = agg.get("class_size", 0)
    if n == 0:
        L.append("_无可分析学生数据_\n")
        return "\n".join(L)

    avg = agg["average"]; med = agg["median"]
    hi = agg["high"]; lo = agg["low"]
    pr = agg["pass_rate"]

    L.append("## 一、班级概览\n")
    L.append("| 指标 | 数值 |")
    L.append("|---|---|")
    L.append(f"| 班级人数 | {n} |")
    L.append(f"| 平均得分率 | {avg*100:.1f}% |")
    L.append(f"| 中位数得分率 | {med*100:.1f}% |")
    L.append(f"| 最高得分率 | {hi*100:.1f}% |")
    L.append(f"| 最低得分率 | {lo*100:.1f}% |")
    L.append(f"| 及格率(≥60%) | {pr*100:.1f}% |\n")

    tc = agg.get("tier_counts", {})
    A = tc.get("A",0); B = tc.get("B",0)
    C = tc.get("C",0); D = tc.get("D",0)
    def bar(c):
        filled = int(c/max(n,1)*20+0.5); filled=min(20,max(0,filled))
        b = "█"*filled + "░"*(20-filled)
        pct = c/n*100
        return f"{b}  {c}/{n} ({pct:.0f}%)"
    L.append("## 二、分层分布\n")
    L.append("- **A级 (≥90%)**："+bar(A))
    L.append("- **B级 (75~89%)**："+bar(B))
    L.append("- **C级 (60~74%)**："+bar(C))
    L.append("- **D级 (<60%)**："+bar(D)+"\n")

    pq = agg.get("per_question_stats", {})
    L.append("## 三、逐题正误分布\n")
    L.append("| 题号 | 平均正确率 | 错答比例 | 作答人数 |")
    L.append("|---|---|---|---|")
    for qid in sorted(pq.keys()):
        s = pq[qid]
        cr = s.get("avg_correct_rate",0)*100
        wr = s.get("wrong_rate",0)*100
        cn = s.get("n",0)
        flag = " ⚠️" if wr > .5 else ""
        L.append(f"| 第{qid}题 | {cr:.1f}%{flag} | {wr:.1f}%{flag} | {cn} |")
    L.append("")

    kps = agg.get("kp_stats", {})
    weak = set(agg.get("weak_kps", [])) or []
    L.append("## 四、知识点掌握情况\n")
    if kps:
        L.append("| 知识点 | 班级掌握度 | 题目数 | 预警 |")
        L.append("|---|---|---|---|")
        for kk, st in sorted(kps.items(), key=lambda kv: kv[1]["avg_mastery"]):
            m = st["avg_mastery"]*100; cnt = st["count"]
            fl = "🔴 重点回顾" if m < 60 else ("🟡 巩固强化" if m < 75 else "🟢 良好")
            L.append(f"| {kk} | {m:.1f}% | {cnt} | {fl} |")
        L.append("")
    else:
        L.append("_未配置知识点_\n")

    L.append("## 五、个性化干预建议\n")
    top_d = [s for s in students if s["tier"] == "D"][:5]
    top_c = [s for s in students if s["tier"] == "C"][:3]
    if top_d or top_c:
        focus_list = top_c[:2] + top_d
        seen_ids=set()
        for s in focus_list:
            sid=s["student_id"];
            if sid in seen_ids: continue
            seen_ids.add(sid)
            nm=s["name"]; wk="、".join(s.get("weak_kps",[])) or "-"
            adv=s.get("advice","-")
            L.append(f"- **{nm}（{sid}）**：分层={s['tier']}，薄弱知识点：{wk} → 建议：{adv}")
        L.append("")
    else:
        L.append("_暂无C/D级需要重点关注的学生_\n")

    low_qids=[qid for qid,s in pq.items() if s.get("wrong_rate",0)>.5]
    if low_qids and kps:
        qid_to_kp={}
        for s_ in students:
            for d in s_.get("answers_detail",[]):
                qid_to_kp.setdefault(d["qid"],d["kp"])
        kp_summary=defaultdict(list)
        for qid in low_qids:
            kp=qid_to_kp.get(qid,"未分类"); kp_summary[kp].append(qid)
        L.append("> 全班错答率>50%的题号涉及以下知识点，建议优先讲解复习：\n")
        for kp,qids_v in kp_summary.items():
            qs_str="、".join([f"第{x}题" for x in sorted(qids_v)])
            L.append(f"- {kp}：{qs_str}")

    return "\n".join(L)




def render_csv(students):
    import io as _io
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(['student_id', 'name', 'total_earned',
                'total_possible', 'score_pct', 'tier',
                'weak_kps', 'advice'])
    for s in students:
        w.writerow([
            s['student_id'], s['name'],
            round(s['total_earned'], 4),
            round(s['total_possible'], 4),
            f"{round(s['pct']*100, 2)}%",
            s['tier'],
            ';'.join(s.get('weak_kps', []) or ['']),
            s.get('advice', ''),
        ])
    return buf.getvalue()


def esc(s):
    if s is None: return ''
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')


def render_html(meta, agg, students):
    pq = agg.get('per_question_stats', {}) or {}
    tc = agg.get('tier_counts', {}) or {}
    kps = agg.get('kp_stats', {}) or {}

    n = agg.get('class_size', 0) or len(students)
    avg = agg.get('average', 0); med = agg.get('median', 0)
    hi = agg.get('high', 0); lo = agg.get('low', 0)
    pr = agg.get('pass_rate', 0)

    title_t = esc(meta.get('title') or '')
    subj_s = esc(meta.get('subject') or '')

    parts = []
    parts.append('<!DOCTYPE html>')
    parts.append("<html lang='zh-CN'><head><meta charset='UTF-8'>")
    parts.append(f"<title>学情诊断报告 · {title_t}</title>")
    parts.append("<style>body{font-family:'PingFang SC',sans-serif;margin:24px;background:#fafafa;color:#333}")
    parts.append(".card{background:#fff;border-radius:12px;padding:18px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}")
    parts.append(".stat-grid{display:flex;flex-wrap:wrap;gap:14px;margin-top:6px}")
    parts.append(".kpi{flex:1;min-width:120px;text-align:center;padding:14px;background:#f9fbff;border-radius:8px}")
    parts.append(".kpi .val{font-size:28px;font-weight:bold;color:#2563eb;display:block}")
    parts.append(".kpi .lbl{font-size:13px;color:#666;margin-top:4px}")
    parts.append("table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}")
    parts.append("th{text-align:left;padding:8px;background:#eff6ff;color:#3730a3;border-bottom:2px solid #bfdbfe}")
    parts.append("td{padding:8px;border-bottom:1px solid #e5e7eb}")
    parts.append("tr.warn td{color:#b91c1c;font-weight:bold}")
    parts.append(".barwrap{width:160px;height:18px;background:#eee;border-radius:9px;display:inline-block;vertical-align:middle}")
    parts.append(".bar{height:100%}.red{background:#ef4444}.yellow{background:#eab308}.green{background:#22c55e}")
    parts.append("</style></head><body>")

    parts.append("<div class='card'><h1>📊 学情诊断报告</h1>")
    parts.append(f"<div style='color:#666'>{title_t} · {subj_s} <span style='float:right;color:#999;'>{datetime.now().strftime('%Y-%m-%d %H:%M')}</span></div>")
    parts.append('</div>')

    stats_tiles = [
        ('班级规模', str(n)),
        ('平均分率', f'{avg*100:.1f}%'),
        ('中位数', f'{med*100:.1f}%'),
        ('最高分率', f'{hi*100:.1f}%'),
        ('最低分率', f'{lo*100:.1f}%'),
        ('及格率≥60%', f'{pr*100:.1f}%'),
    ]
    tiles_html = "<div class='card stat-grid'>" + ''.join(
        f"<div class='kpi'><span class='val'>{v}</span><div class='lbl'>{lbl}</div></div>"
        for lbl,v in stats_tiles
    ) + '</div>'
    parts.append(tiles_html)

    colors_map = {'A':'#22c55e','B':'#84cc16','C':'#eab308','D':'#ef4444'}
    ranges_map = {'A':'≥90%','B':'75~89%','C':'60~74%','D':'<60%'}
    total_n = max(sum(tc.values()) or n, 1)

    tier_html_parts=[]
    for t_name in ['A','B','C','D']:
        cnt=tc.get(t_name,0); w_pct=int(cnt/total_n*220)+30
        color=colors_map[t_name]
        pct_share=f"{cnt*100//max(total_n,1)}%"
        block=(f"<div style='text-align:center;margin-right:12px'>"
               f"<div style='background:{color};width:{w_pct}px;height:36px;text-align:center;line-height:36px;color:white;font-weight:bold'>{cnt}</div>"
               f"<div>{t_name}级<br><small>{ranges_map[t_name]}<br>{pct_share}</small></div>"
               "</div>")
        tier_html_parts.append(block)
    parts.append("<div class='card'><h2>分层分布</h2>" + "".join(p for p in tier_html_parts) + '</div>')

    q_rows=''
    for qid in sorted(pq.keys()):
        v=pq[qid]; r=v.get('avg_correct_rate',0)*100; wr=v.get('wrong_rate',0)*100
        cls_attr="class='warn'" if r<60 else ""
        bg='#ef4444'if r<60 else '#eab308' if r<80 else '#22c55e'
        q_rows+=(
            f"<tr {cls_attr}><td>第{qid}题</td>"
            f"<td><div class='barwrap'><div class='bar' style='width:{int(r)}%;background:{bg}'></div></div></td>"
            f"<td>{r:.1f}%</td><td>{wr:.1f}%</td><td>{v.get('n',0)}</td>"
            f"</tr>"
        )
    pq_table=(
        "<table><thead><tr><th>#题号</th><th width=200>正确率条形图</th>"
        "<th>%</th><th>错答%</th><th>n</th></tr></thead><tbody>"+q_rows+"</tbody></table>"
    )
    parts.append("<div class='card'><h2>逐题正确率热力图</h2>"+pq_table+'</div>')

    kp_rows_html=""
    for kk,st in sorted(kps.items(), key=lambda x:x[1]['avg_mastery']):
        ms=st['avg_mastery']*100; cnt=st['count']
        tag_label='<span class=\"badge red\">重点回顾</span>' if ms<60 else ('巩固强化' if ms<75 else '良好')
        bgc='#ef4444' if ms<60 else '#eab308' if ms<75 else '#22c55e'
        kp_rows_html+=(
            f"<tr><td>{esc(kk)}</td>"
            f"<td><div class='barwrap'><div class='bar' style='width:{int(ms)}%;background:{bgc}'></div></div></td>"
            f"<td>{ms:.1f}%</td><td>{cnt}</td><td>{tag_label}</td></tr>"
        )
    kp_table=(
        "<table><thead><tr><th>知识模块</th><th width=200>掌握进度</th>"
        "<th>%</th><th>题目数</th><th>标签</th></tr></thead><tbody>"+kp_rows_html+"</tbody></table>"
    )
    parts.append("<div class='card'><h2>知识点掌握矩阵</h2>"+kp_table+"</div>")

    by_tier={'A':[], 'B':[], 'C':[], 'D':[]}
    for s in students:
        by_tier[s['tier']].append(s)
    focus_list = by_tier['C'][:5] + by_tier['D'] + by_tier['A'][-1:]
    seen_sid=set(); stu_rows_html=""
    dots={'A':'🟢','B':'🟡','C':'🟠','D':'🔴'}
    for s in focus_list:
        sid=s['student_id']
        if sid in seen_sid: continue
        seen_sid.add(sid)
        wk=", ".join(s.get('weak_kps',[])or []) or '-'
        ad=esc(s.get('advice','-'))
        score_disp=f"{int(round(s['pct']*100))}%"
        sty_class="" if s['pct']>=.6 else "style='color:red'"
        stu_rows_html+=(
            f"<tr {sty_class}><td>{dots[s['tier']]}{esc(sid)}</td>"
            f"<td>{esc(s['name'])}</td><td>{score_disp}</td>"
            f"<td>{esc(wk)}</td><td>{ad}</td></tr>"
        )
    stu_table=(
        "<table><thead><tr><th>ID学号</th><th>姓名</th><th>得分率</th>"
        "<th>薄弱知识点</th><th>干预建议摘要</th></tr></thead><tbody>"+
        stu_rows_html+"</tbody></table>"
    )
    parts.append("<div class='card'><h2>需重点关注的学生清单</h2>"+stu_table+"</div>")

    bad_qs=len([qv for qv in pq.values() if qv.get('wrong_rate',0)>0.5])
    weak_count=len(agg.get('weak_kps',[]))
    note_text=f"共识别出 <strong>{bad_qs}</strong> 道全班高错误率题目和 <strong>{weak_count}</strong> 个低掌握度知识点。建议教师按上述顺序安排讲评。"
    note_div="<div style='margin-top:10px;padding:10px;background:#fefce8;border-left:4px solid #ca8a04;font-size:13px;border-radius:4px'>💡 "+note_text+" 本数据基于示例作答生成，仅供原型验证参考。</div>"
    parts.append(note_div+"<footer style='text-align:center;color:#999;font-size:12px;margin-top:20px'>教育场景 Skill 原型 · homework-grading-analyzer</footer>")
    parts.append("</body></html>")
    return "\n".join(parts)


def run_cli():
    ap = argparse.ArgumentParser(description='homework-grading-analyzer 批量批改与学情诊断')
    ap.add_argument('--key','-k',required=True,help='answer_key JSON 文件路径')
    ap.add_argument('--csv','-s',required=True,help='student responses CSV 路径')
    ap.add_argument('--out-dir','-o',default='./output',help='输出目录')
    args=ap.parse_args()

    out_dir=Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True,exist_ok=True)

    try:
        report=grade_all(args.key,args.csv)
        agg=aggregate(report)
    except FileNotFoundError as e:
        print(f"[ERROR] 输入文件不存在：{e.filename}",file=sys.stderr); sys.exit(2)
    except ValueError as e:
        print(f"[ERROR] 数据校验失败：{e}",file=sys.stderr); sys.exit(3)
    except Exception as e:
        print(f"[ERROR] 处理失败：{type(e).__name__}: {e}",file=sys.stderr); sys.exit(1)

    meta=report["key_meta"]; students=report["students"]

    md_path=out_dir/'grading_summary.md'
    md_path.write_text(render_md(meta,agg,students),encoding='utf-8')
    print(f"[OK] Markdown 报告已生成 → {md_path}")

    csv_path=out_dir/'student_grades.csv'
    csv_path.write_text(render_csv(students),encoding='utf-8-sig')
    print(f"[OK] 学生成绩 CSV 已导出 → {csv_path}")

    html_path=out_dir/'dashboard.html'
    html_path.write_text(render_html(meta,agg,students),encoding='utf-8')
    print(f"[OK] 可视化看板已构建 → {html_path}")

    json_summary={
        "key_meta": meta,
        "aggregates": {
            "class_size": agg.get("class_size"),
            "average":   agg.get("average"),
            "pass_rate": agg.get("pass_rate"),
            "tier_counts": agg.get("tier_counts",{}),
            "weak_kps":  agg.get("weak_kps",[]),
        },
        "students_total": len(students),
        "generated_at": datetime.now().isoformat(timespec='seconds'),
    }
    json_path=out_dir/'summary.json'
    json_path.write_text(json.dumps(json_summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"[OK] 结构化 JSON 摘要已写出 → {json_path}")


if __name__=='__main__':
    run_cli()
