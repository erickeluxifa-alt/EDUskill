#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
html_render.py —— exam-followup-reviewer 的自包含可视化报告渲染模块。
输出单文件 HTML：无外部依赖（无 CDN/JS 框架）、桌面/移动自适应、可打印存档。
"""
from followup_reviewer import esc, strip_ctrl, pct


def _band_color(band):
    return {
        "优秀": "#1a7f37", "良好": "#2da44e", "中等": "#d29922",
        "待提升": "#cf222e", "需重点改进": "#b62324",
        "已掌握": "#1a7f37", "掌握一般": "#9a6700", "薄弱": "#cf222e", "严重薄弱": "#82071e",
        "数据不足": "#888",
    }.get(band, "#555")


def _bar(p, wide=False):
    """纯 CSS 进度条。"""
    if p is None:
        return '<span class="na">N/A</span>'
    p = float(p)
    w = max(2, min(100, p * 100))
    color = "#1a7f37" if p >= 0.8 else ("#9a6700" if p >= 0.6 else "#cf222e")
    return ('<div class="bar%s"><div class="barfill" style="width:%.1f%%;background:%s"></div>'
            '<span class="bartxt">%.1f%%</span></div>' % (" wide" if wide else "", w, color, p * 100))


def render_report(recs, profs, kps, merged, quads, helps, q_review):
    css = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#f3f5f7;color:#222;line-height:1.6}
.wrap{max-width:1080px;margin:0 auto;padding:16px}
.header{background:linear-gradient(135deg,#0f4c81,#185a9d);color:#fff;border-radius:14px;padding:22px 26px;margin-bottom:18px}
.header h1{font-size:22px;margin-bottom:6px}
.header .sub{opacity:.9;font-size:13px}
.kpis{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:18px}
.kpi{flex:1 1 160px;background:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.kpi .num{font-size:26px;font-weight:700}
.kpi .num small{font-size:13px;font-weight:400;color:#777}
.kpi .lab{font-size:12px;color:#777}
.card{background:#fff;border-radius:12px;padding:16px 18px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card h2{font-size:16px;margin-bottom:12px;border-left:4px solid #0f4c81;padding-left:8px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 8px;border-bottom:1px solid #eef1f4;text-align:left;white-space:nowrap}
th{background:#f6f8fa;color:#444}
td.wrap-cell{white-space:normal;min-width:160px}
.tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;color:#fff}
.badge{font-weight:700}
.tips li{margin:6px 0}
.bar{position:relative;min-width:90px;background:#eef1f4;border-radius:8px;height:18px;overflow:hidden}
.bar.wide{min-width:140px}
.barfill{position:absolute;left:0;top:0;bottom:0;border-radius:8px;opacity:.85}
.bartxt{position:relative;z-index:1;padding-left:6px;font-size:11px;color:#333;line-height:18px}
.na{color:#999}
.note{font-size:12px;color:#777;margin-top:8px}
.footer{text-align:center;color:#999;font-size:12px;padding:14px 0 30px}
@media print{body{background:#fff}.card,.kpi{box-shadow:none;border:1px solid #ddd}}
@media(max-width:640px){.wrap{padding:8px}.header h1{font-size:18px}
table{font-size:12px}th,td{padding:5px 4px}.kpis{gap:8px}}
"""

    def kpi(num, lab, sub=""):
        return ('<div class="kpi"><div class="num">%s<span class="lab">%s</span></div>'
                '<div class="lab">%s</div></div>' % (num, sub, lab))

    # ---- 头部 ----
    p0 = profs[0]
    h = []
    h.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>考后教学复盘报告</title><style>%s</style></head><body><div class="wrap">' % css)
    h.append('<div class="header"><h1>考后教学复盘报告</h1>'
             '<div class="sub">%s ｜ %s ｜ 生成 %s</div></div>' % (
                 esc(p0["exam"] or "考试"), esc(p0["course"] or ""), esc(recs[0]["meta"].get("date") or "")))

    # ---- KPI 卡片 ----
    kpis = []
    for p in profs[:4]:
        kpis.append(kpi(p["band"], p["class_name"] + " 画像",
                        "综合分 %.2f / 满分 1.00" % p["score"] if p["score"] is not None else ""))
    h.append('<div class="kpis">' + "".join(kpis) + "</div>")

    # ---- 一、班级画像 ----
    h.append('<div class="card"><h2>班级整体画像</h2><table><thead><tr>')
    for c in ["班级", "人数", "均分", "及格率", "优秀率", "低分率", "得分率", "信度α", "画像"]:
        h.append("<th>%s</th>" % c)
    h.append("</tr></thead><tbody>")
    for p in profs:
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s%%</td><td>%s%%</td><td>%s%%</td>"
                 "<td>%s%%</td><td>%s</td><td><span class='tag' style='background:%s'>%s</span></td></tr>" % (
                     esc(p["class_name"]), p["n"], p["mean"], p["pass"], p["excel"], p["low"],
                     p["p_overall"], ("%.2f" % p["alpha"]) if p["alpha"] is not None else "-",
                     _band_color(p["band"]), p["band"]))
    h.append("</tbody></table></div>")

    # ---- 二、知识点 ----
    h.append('<div class="card"><h2>知识点掌握度（按平均得分率降序）</h2><table><thead><tr>'
             '<th>知识点</th><th>平均得分率</th><th>掌握度</th><th>归因</th></tr></thead><tbody>')
    if merged:
        for k in merged:
            h.append("<tr><td class='wrap-cell'>%s</td><td>%s</td><td><span class='tag' style='background:%s'>%s</span></td>"
                     "<td>%s</td></tr>" % (esc(k["kp"]), _bar(k["p"]), _band_color(k["band"]), k["band"],
                                          "共性薄弱" if k["common"] else "班内情况"))
    else:
        h.append('<tr><td colspan="4">无知识点数据</td></tr>')
    h.append("</tbody></table></div>")

    # ---- 三、命题质量 ----
    h.append('<div class="card"><h2>命题质量与回流建议</h2>')
    if q_review:
        h.append("<table><thead><tr><th>班级</th><th>题号</th><th>知识点</th><th>得分率</th><th>区分度</th><th>判定</th></tr></thead><tbody>")
        for q in q_review:
            col = "#b62324" if q["quad"] == "双低·疑议题" else "#9a6700"
            h.append("<tr><td>%s</td><td>%s</td><td class='wrap-cell'>%s</td><td>%s</td><td>%s</td>"
                     "<td><span class='tag' style='background:%s'>%s</span></td></tr>" % (
                         esc(q.get("class") or ""), esc(q["id"]), esc(q["kp"]),
                         (str(pct(q["p"])) + "%") if q["p"] is not None else "-",
                         q["d"] if q["d"] is not None else "-", col, q["quad"]))
        h.append("</tbody></table>")
        h.append('<div class="note">双低·疑议题需备课组复核题目歧义/超纲；高区分·拉分题是复习提分杠杆；'
                 '回流建议已写入 blueprint_feedback.json 供下一轮命题参考。</div>')
    else:
        h.append('<div class="note">本卷未出现需要干预的问题题（题目区分度均正常）。</div>')
    h.append("</div>")

    # ---- 四、帮扶清单 ----
    total_help = sum(len(x) for x in helps)
    h.append('<div class="card"><h2>学生帮扶清单（%d 人）</h2>' % total_help)
    if total_help:
        for p, rows in zip(profs, helps):
            if not rows:
                continue
            h.append("<h3 style='font-size:14px;margin:10px 0 6px'>%s</h3>" % esc(p["class_name"]))
            h.append("<table><thead><tr><th>学号</th><th>姓名</th><th>总分</th><th>百分位</th><th>标记</th></tr></thead><tbody>")
            for r in rows:
                h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s%%</td><td>%s</td></tr>" % (
                    esc(r["sid"]), esc(r["name"]), r["total"], r["percentile"], esc(r["flags"])))
            h.append("</tbody></table>")
        h.append('<div class="note">帮扶建议：按标记优先跟进，每周 1 次过关练习并同步家长。名单可导出 help_list.csv。</div>')
    else:
        h.append('<div class="note">analysis.students 未提供学生明细或无学生落在帮扶区间，'
                 '可先运行 exam-score-analyzer --scores 生成 students 数据。</div>')
    h.append("</div>")

    h.append('<div class="footer">由 exam-followup-reviewer v1.0.0 生成 ｜ 规则模板建议，需结合教师专业判断</div>')
    h.append("</div></body></html>")
    return "".join(h)


def _bar(p):
    if p is None:
        return '<span class="na">N/A</span>'
    p = float(p)
    w = max(2, min(100, p * 100))
    color = "#1a7f37" if p >= 0.8 else ("#9a6700" if p >= 0.6 else "#cf222e")
    return ('<div class="bar" style="display:inline-block"><div class="barfill" style="width:%.1f%%;background:%s">'
            '</div><span class="bartxt">%.1f%%</span></div>' % (w, color, p * 100))