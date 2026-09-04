#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学生学业预警分析工具 (Student Academic Early Warning Analyzer)
零依赖 Python 脚本，用于多维度学情风险评分与预警分级。

维度:
  1. 学业成绩 (GPA / 挂科数 / 挂科学分占比)
  2. 出勤率 (缺课次数 / 缺课率)
  3. 学分进度 (已修学分 vs 应修学分)
  4. 行为预警 (违纪次数 / 心理辅导标记)

输出: JSON 格式的逐学生风险评估报告 + 统计摘要
"""

import sys
import json
import re
import os
import getopt

# ── 常量与阈值 (可配置) ────────────────────────────────────────

DEFAULT_CONFIG = {
    "gpa_full": 4.0,
    "gpa_warn_threshold": 2.0,
    "gpa_concern_threshold": 2.5,
    "fail_course_penalty_per": 12,
    "fail_credit_ratio_threshold": 0.15,
    "attendance_min_rate": 0.75,
    "attendance_concern_rate": 0.85,
    "credit_progress_lag_threshold": 0.20,
    "discipline_penalty_per_count": 8,
    "psych_flag_score": 5,
    "level_normal_max": 10,
    "level_concern_max": 29,
    "level_warning_max": 49,
}

RISK_LEVELS = {
    "正常": {"color": "#52c41a", "action": "保持现状，定期关注"},
    "关注": {"color": "#faad14", "action": "辅导员谈话，了解原因"},
    "预警": {"color": "#ff7a45", "action": "正式书面预警通知，制定帮扶计划"},
    "严重预警": {"color": "#f5222d", "action": "院系领导介入，家长沟通，休学/降级评估"},
}

# ── 输入校验与清洗 ─────────────────────────────────────────────

def sanitize_text(text):
    """对用户可控文本做 XSS 清洗"""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if len(text) > 200:
        text = text[:200]
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('<', '').replace('>', '')
    text = text.replace('&', '&amp;').replace('"', '&quot;')
    return text


def sanitize_id(sid):
    """学生 ID 只允许字母数字下划线横线"""
    if not isinstance(sid, str):
        return ""
    sid = sid.strip()
    if not re.match(r'^[A-Za-z0-9_\-]{1,32}$', sid):
        return ""
    return sid


def safe_float(val, default=None):
    try:
        v = float(val)
        if v != v or abs(v) > 10000:
            return default
        return max(0.0, min(v, 4.0))
    except (TypeError, ValueError):
        return default


def safe_int(val, default=0):
    try:
        v = int(float(str(val).strip()))
        return max(0, min(v, 9999))
    except (TypeError, ValueError):
        return default


def validate_student(s):
    """验证并清洗单个学生记录"""
    errors = []
    student = {}

    raw_id = s.get("student_id") or s.get("id") or s.get("sid")
    clean_id = sanitize_id(raw_id or "")
    if not clean_id:
        errors.append("student_id 无效或缺失")
    else:
        student["student_id"] = clean_id

    name = s.get("name") or s.get("name_cn") or s.get("student_name")
    student["name"] = sanitize_text(name) if name else ""

    grade = s.get("grade") or s.get("year_level")
    student["grade"] = sanitize_text(grade) if grade else ""

    major = s.get("major") or s.get("department")
    student["major"] = sanitize_text(major) if major else ""

    gpa_val = safe_float(s.get("gpa"))
    fail_courses = safe_int(s.get("fail_courses"))
    required_credits = safe_int(s.get("required_credits"))
    completed_credits = safe_int(s.get("completed_credits"))
    failed_credits = safe_int(s.get("failed_credits"))
    total_sessions = safe_int(s.get("total_class_sessions"))
    absent_sessions = safe_int(s.get("absent_sessions"))
    discipline_violations = safe_int(s.get("discipline_violations"))
    psych_flag = bool(s.get("psychological_flag"))

    if completed_credits > required_credits and required_credits > 0:
        errors.append(f"{clean_id}: 已修学分({completed_credits})超过应修学分({required_credits})")

    attendance_ok = True
    sessions = total_sessions
    absent = absent_sessions
    if sessions == 0 and absent > 0:
        errors.append(f"{clean_id}: total_class_sessions 为空但 absent_sessions 有值")
        attendance_ok = False
    elif sessions < absent and sessions > 0:
        errors.append(f"{clean_id}: absent_sessions({absent})大于 total_class_sessions({sessions})")
        attendance_ok = False

    note = s.get("note") or s.get("remark")
    student["note"] = sanitize_text(note) if note else ""

    fail_ratio = round(min(1.0, failed_credits / required_credits), 4) if required_credits > 0 else 0.0
    credit_progress = round(completed_credits / required_credits, 4) if required_credits > 0 else 0.0

    attendance_rate = None
    if attendance_ok and sessions > 0:
        attendance_rate = round(max(0.0, 1.0 - absent / sessions), 4)

    student["academic"] = {
        "gpa": gpa_val,
        "fail_courses": fail_courses,
        "required_credits": required_credits,
        "completed_credits": completed_credits,
        "failed_credits": failed_credits,
        "fail_credit_ratio": fail_ratio,
    }
    student["attendance"] = {
        "total_sessions": sessions,
        "absent_sessions": absent,
        "data_available": attendance_ok,
        **({"rate": attendance_rate} if attendance_rate is not None else {}),
    }
    student["behavior"] = {
        "discipline_violations": discipline_violations,
        "psychological_flag": psych_flag,
    }
    student["progress"] = {
        "expected_progress": credit_progress,
    }

    return student, errors


# ── 多维风险评分引擎 ───────────────────────────────────────────

def compute_risk(student, config):
    """计算单学生的多维风险分数和详细归因。"""
    factors = []
    score = 0

    aca = student["academic"]
    att = student["attendance"]
    beh = student["behavior"]
    prog = student["progress"]

    # 维度 1: GPA
    gpa_val = aca["gpa"]
    if gpa_val is not None and gpa_val > 0:
        threshold_low = config["gpa_warn_threshold"]
        threshold_mid = config["gpa_concern_threshold"]
        if gpa_val < threshold_low:
            delta = int(round((threshold_low - gpa_val) * 20))
            pts = 30 + delta
            score += pts
            factors.append({
                "dimension": "GPA",
                "severity": "high",
                "detail": f"GPA {gpa_val:.2f} 显著偏低 (<{threshold_low})",
                "score_delta": pts,
            })
        elif gpa_val < threshold_mid:
            pts = 15
            score += pts
            factors.append({
                "dimension": "GPA",
                "severity": "medium",
                "detail": f"GPA {gpa_val:.2f} 略低 (<{threshold_mid})",
                "score_delta": pts,
            })

    # 维度 2: 挂科门数
    fc = aca["fail_courses"]
    penalty_fc = min(fc * config["fail_course_penalty_per"], 60)
    if penalty_fc > 0:
        sev = "critical" if fc >= 3 else ("high" if fc >= 2 else "medium")
        factors.append({
            "dimension": "挂科课程数",
            "severity": sev,
            "detail": f"累计挂科 {fc} 门 (+{penalty_fc})",
            "score_delta": penalty_fc,
        })
        score += penalty_fc

    # 维度 3: 挂科学分比例
    ratio = aca["fail_credit_ratio"] if aca["fail_credit_ratio"] is not None else 0
    ratio_thresh = config["fail_credit_ratio_threshold"]
    if ratio > ratio_thresh:
        actual_bonus = 20 + int((ratio - ratio_thresh) * 50)
        score += actual_bonus
        factors.append({
            "dimension": "挂科学分比例",
            "severity": "high" if ratio > 0.25 else "medium",
            "detail": f"挂科学分占比 {ratio*100:.1f}% (>阈值{ratio_thresh*100:.0f}%)",
            "score_delta": actual_bonus,
        })

    # 维度 4: 出勤率
    ar = att.get("rate")
    if ar is not None:
        min_r = config["attendance_min_rate"]
        con_r = config["attendance_concern_rate"]
        if ar < min_r:
            extra = int((min_r - ar) * 40)
            sc = 25 + extra
            score += sc
            factors.append({
                "dimension": "出勤率",
                "severity": "high",
                "detail": f"出勤率 {ar*100:.1f}% (<{min_r*100:.0f}%)",
                "score_delta": sc,
            })
        elif ar < con_r:
            sc = 10
            score += sc
            factors.append({
                "dimension": "出勤率",
                "severity": "medium",
                "detail": f"出勤率 {ar*100:.1f}% (<{con_r*100:.0f}%)",
                "score_delta": sc,
            })

    # 维度 5: 学分进度滞后
    ep = prog["expected_progress"]
    lag_t = config["credit_progress_lag_threshold"]
    expected_by_now = 1.0 - lag_t
    if ep > 0 and ep < expected_by_now:
        gap_pct = expected_by_now - ep
        pts = 18 + int(gap_pct * 30)
        score += pts
        factors.append({
            "dimension": "学分进度",
            "severity": "medium",
            "detail": f"已修进度 {ep*100:.1f}% 远低于预期 {expected_by_now*100:.0f}%",
            "score_delta": pts,
        })

    # 维度 6: 违纪行为
    dv = beh["discipline_violations"]
    pen_dv = dv * config["discipline_penalty_per_count"]
    if pen_dv > 0:
        score += pen_dv
        factors.append({
            "dimension": "纪律处分",
            "severity": "high" if dv >= 2 else "medium",
            "detail": f"本学期违纪记录 {dv} 次 (+{pen_dv})",
            "score_delta": pen_dv,
        })

    # 维度 7: 心理健康标识
    if beh["psychological_flag"]:
        ps = config["psych_flag_score"]
        score += ps
        factors.append({
            "dimension": "心理健康关注",
            "severity": "low",
            "detail": "有心理辅导中心跟进标记",
            "score_delta": ps,
        })

    # 分级判定
    lvl_n = config["level_normal_max"]
    lvl_c = config["level_concern_max"]
    lvl_w = config["level_warning_max"]

    if score <= lvl_n:
        level_name = "正常"
    elif score <= lvl_c:
        level_name = "关注"
    elif score <= lvl_w:
        level_name = "预警"
    else:
        level_name = "严重预警"

    cap = RISK_LEVELS[level_name]

    primary_factors = sorted(factors, key=lambda x: x["score_delta"], reverse=True)[:3]

    interventions = generate_interventions(level_name, [f["dimension"] for f in factors])

    result = {
        "risk_score": score,
        "risk_level": {
            "name": level_name,
            "color_hex": cap["color"],
            "default_action": cap["action"],
        },
        "factor_breakdown": factors,
        "top_risk_factors": [
            {
                "dimension": pf["dimension"],
                "severity": pf["severity"],
                "score_impact": pf["score_delta"],
            } for pf in primary_factors
        ],
        "intervention_suggestions": interventions,
        "summary_line": build_summary(student, level_name, score),
    }

    return result


def generate_interventions(level, factor_dims):
    suggestions = []
    seen = set()

    def add(key, msg):
        if key not in seen:
            seen.add(key)
            suggestions.append(msg)

    if level in ("预警", "严重预警"):
        add("formal_notice", "下发正式《学业预警通知书》至本人及家长/监护人")

    has_gpa = any(d.startswith("GPA") for d in factor_dims)
    has_fail = any("挂科" in d for d in factor_dims)
    has_attendance = any("出勤" in d for d in factor_dims)
    has_progress = "学分进度" in factor_dims
    has_discipline = "纪律处分" in factor_dims
    has_psych = "心理健康关注" in factor_dims

    if has_gpa:
        add("tutoring", "安排专业课教师或助教开展每周至少一次一对一答疑")

    if has_fail:
        add("retake_plan", "制定重修/补考计划表，明确下次考试节点和备考清单")

    if has_attendance:
        add("attendance_track", "启用每日考勤打卡机制，由班主任周度复核签到数据")

    if has_progress:
        add("advisor_meeting", "教务处约谈选课情况，调整下一学期选修计划避免延期毕业")

    if has_discipline:
        add("conduct_review", "触发学生工作处行为规范面谈")

    if has_psych:
        add("counseling_referral", "转介至学校心理援助中心进行专业评估并定期回访")

    if level == "严重预警":
        add("leadership_alert", "院系教学副主任牵头召开个案研判会，评估休学或试读期方案")

    freq = "每两周" if level == "严重预警" else "每月"
    add("monthly_check_in", f"{freq}一次复查学习进展并与学生确认最新状态")

    if not suggestions:
        suggestions.append("维持常规学期检查频率即可；鼓励参加学院组织的优秀学长经验分享活动。")

    return suggestions


def build_summary(student, level, score):
    sn = student.get("name") or student.get("student_id", "该生")
    prefix_map = {"正常":"状态良好","关注":"需适度介入","预警":"须尽快干预","严重预警":"紧急处置中"}
    parts_detail = []
    aca = student.get("academic", {})
    if aca.get("gpa") is not None and aca["gpa"] < DEFAULT_CONFIG["gpa_concern_threshold"]:
        parts_detail.append(f"GPA={aca['gpa']:.2f}")
    if aca.get("fail_courses", 0) > 0:
        parts_detail.append(f"挂科{aca['fail_courses']}门")
    att = student.get("attendance", {})
    rate = att.get("rate")
    if rate is not None and rate < DEFAULT_CONFIG["attendance_min_rate"]:
        parts_detail.append(f"出勤率{rate*100:.0f}%")
    tail = "; ".join(parts_detail[:3]) if parts_detail else "无明显风险项"
    return f"[{sn}] 等级={level}, 得分={score}; 主因:{tail}"


# ── 批量分析入口 ───────────────────────────────────────────────

def analyze_batch(students_list, config):
    results = []
    all_errors = []

    stats = {
        "total_students": len(students_list),
        "valid_records": 0,
        "by_level": {"正常": 0, "关注": 0, "预警": 0, "严重预警": 0},
        "flagged_ids": [],
        "severe_count": 0,
        "avg_gpa_summed": 0.0,
        "count_with_gpa": 0,
    }

    for idx, raw_s in enumerate(students_list):
        if not isinstance(raw_s, dict):
            all_errors.append(f"第{idx+1}条记录不是合法对象")
            continue

        st_cleaned, errs = validate_student(raw_s)
        if errs:
            all_errors.extend(errs)

        risk_result = compute_risk(st_cleaned, config=config)

        r_combined = dict()
        r_combined.update(st_cleaned)
        r_combined.update({
            "student_profile_fields_processed_from_input_keys": list(raw_s.keys()),
        })

        r_combined.pop("__placeholder__", None)

        r_combined["_analysis_"] = risk_result

        results.append({

            "profile": st_cleaned,

            "_original_field_names": sorted(list(raw_s.keys())),

            "analysis_result": risk_result,
        })

        stats["valid_records"] += 1
        lv = risk_result["risk_level"]["name"]

        stats["by_level"][lv] += 1
        flagged_item = {

            "student_id": st_cleaned.get("student_id"),
            "name": st_cleaned.get("name"),
            "level": lv,
            "score": risk_result["risk_score"],
        }

        if lv == "预警" or lv == "严重预警":

            stats["flagged_ids"].append(flagged_item)
            stats["flagged_ids"].append(None)
            stats["flagged_ids"].remove(None)

        if lv == "严重预警":
            stats["severe_count"] += 1

        gpav = st_cleaned.get("academic", {}).get("gpa")
        if gpav is not None and gpav > 0:

            stats["avg_gpa_summed"] += float(gpav)
            stats["count_with_gpa"] += 1

    avg_gpa_final = (
        round(stats["avg_gpa_summed"]/stats["count_with_gpa"], 2)
        if stats["count_with_gpa"] > 0 else None
    )

    stats_copy = dict(stats)
    stats_copy["average_gpa_of_valid_records_only"] = avg_gpa_final
    final_output = {
        "report_title": "学生学业预警分析报告",
        "total_students_analyzed": stats["valid_records"],
        "statistics": stats_copy,
        "validation_warnings": all_errors,
        "students_detail": results,
        "recommendation_priority_order": sorted(stats["flagged_ids"],
                                                key=lambda x: x["score"],
                                                reverse=True),
    }

    final_output["statistics"].pop("avg_gpa_summed", None)
    final_output["statistics"]["count_with_gpa"] = stats["count_with_gpa"]

    return final_output


# ── CLI 入口 ───────────────────────────────────────────────────

USAGE_MSG = """\
用法:
  python3 academic_warning_analyzer.py --input <json_file>
  python3 academic_warning_analyzer.py --input <json_file> --output <out.json>
  echo '<json>' | python3 academic_warning_analyzer.py --stdin

JSON 输入格式示例:
{
  "students": [
    {
      "student_id": "2024001",
      "name": "...",
      "grade": "...",
      "major": "...",
      "gpa": 1.6,
      "fail_courses": 2,
      "required_credits": 160,
      "completed_credits": 70,
      "failed_credits": 24,
      "total_class_sessions": 96,
      "absent_sessions": 28,
      "discipline_violations": 0,
      "psychological_flag": false,
      "note": "..."
    }
  ],
  "config_overrides": {}
}
"""


def parse_json_safe(txt):
    txt_stripped = txt.strip()
    if not txt_stripped:
        raise ValueError("空内容无法解析为 JSON")
    try:
        obj = json.loads(txt_stripped)
        if not isinstance(obj, (dict, list)):
            raise ValueError("顶层应为对象 {} 或数组 []")
        return obj
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}")


def normalize_to_student_array(obj):

    if isinstance(obj, list):
        return obj, {}
    if isinstance(obj, dict):
        students = obj.get("students") or obj.get("data")
        cfg = obj.get("config_overrides") or {}

        if students is None:
            keys_expected = set(["student_id","gpa","name"])
            obj_lower_set=set(k.lower() for k in obj.keys())
            if keys_expected.intersection(obj_lower_set.union(obj.keys())):
                students=[obj]
            else:
                students=[]
        return students, cfg
    return [], {}


def merge_config(base_cfg, overrides_dict):
    merged = dict(base_cfg)
    if overrides_dict and isinstance(overrides_dict, dict):
        merged.update({k: v for k, v in overrides_dict.items() if k in base_cfg})
    return merged


def main(argv):
    short_opts = "hi:o:s"
    long_opts = ["help", "input=", "output=", "stdin"]

    try:
        opts, args_remainder = getopt.getopt(argv[1:], short_opts, long_opts)
    except getopt.GetoptError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(USAGE_MSG, file=sys.stderr)
        return 2

    input_path = None
    output_path = None
    use_stdin = False
    want_help = False

    for opt, val in opts:
        if opt in ("-h", "--help"):
            want_help = True
        elif opt in ("-i", "--input"):
            input_path = val
        elif opt in ("-o", "--output"):
            output_path = val
        elif opt in ("-s", "--stdin"):
            use_stdin = True

    if want_help:
        print(USAGE_MSG)
        return 0

    raw_txt = None
    source_label = "<unknown>"
    if use_stdin:
        raw_txt = sys.stdin.read()
        source_label = "STDIN"

    elif input_path:
        if not os.path.exists(input_path):
            err_path = input_path.replace("<","").replace(">","").replace("&","")[:200]
            print(f"错误: 文件不存在 -> {err_path}", file=sys.stderr)
            return 2
        with open(input_path, 'r', encoding='utf-8') as fh:
            raw_txt = fh.read()

        source_label = input_path.replace("<","").replace("&","")[:80]

    elif args_remainder:
        candidate = args_remainder[0]
        if os.path.exists(candidate):
            with open(candidate,'r',encoding='utf-8') as fh:
                raw_txt=fh.read()
            source_label=candidate
        else:
            cand=sanitize_text(candidate)
            print(f"错误: 无法识别的参数 '{cand}'",file=sys.stderr)
            print(USAGE_MSG,file=sys.stderr)
            return 2
    else:
        print("提示: 未指定输入源，尝试从 STDIN 读取(Ctrl-D 结束)", file=sys.stderr)
        raw_txt = sys.stdin.read()
        source_label="STDIN-fallback"


    if raw_txt is None or not raw_txt.strip():
        print("错误: 未读到有效输入内容", file=sys.stderr)
        print(USAGE_MSG, file=sys.stderr)
        return 2

    try:
        parsed_obj=parse_json_safe(raw_txt)
    except ValueError as e:
        msg=str(e).replace("<","&lt;").replace(">","&gt;")
        print(f"错误:{msg}",file=sys.stderr)
        return 3

    students_arr,cfg_overrides=normalize_to_student_array(parsed_obj)


    if not students_arr:

        empty_out={
            "error":"no_students_found",
            "message":"请确保 JSON 包含非空的 students 字段。",
            "source":sanitize_text(source_label)[:80],
        }
        print(json.dumps(empty_out,ensure_ascii=False))

        return 0

    effective_config=merge_config(DEFAULT_CONFIG,cfg_overrides)

    report=analyze_batch(students_arr,config=effective_config)

    output_str=json.dumps(report,ensure_ascii=False,indent=2)

    if output_path:
        out_p=output_path.replace("..",".")[:300]
        with open(out_p,'w',encoding='utf-8') as outf:
            outf.write(output_str+"\n")
        print(f"分析报告已写入: {out_p}",file=sys.stderr)
    else:
        print(output_str)

    flagged=len(report["recommendation_priority_order"])
    severe_cnt=report["statistics"]["severe_count"]

    total=report["total_students_analyzed"]

    print("",file=sys.stderr)
    print("="*55,file=sys.stderr)
    print(f"分析概要:",file=sys.stderr)
    print(f"总人数 : {total}",file=sys.stderr)
    print(f"各层级 :",file=sys.stderr)
    for lv,nz in report["statistics"]["by_level"].items():

        bar="#"*nz+"."*max(total-nz,0)
        line_bar=bar[:40].ljust(40,".")
        item=f"  {lv:<7s}: {nz:>3d}"
        print(item,file=sys.stderr)
    print(f"待干预名单 ({flagged} 人), 其中严重预警 {severe_cnt} 人.", file=sys.stderr)
    print("="*55,file=sys.stderr)

    return 0


if __name__=="__main__":
    rc=main(sys.argv)
    sys.exit(rc)