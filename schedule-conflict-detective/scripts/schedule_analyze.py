#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
course-schedule-conflict-detective / schedule_analyze.py

课程表冲突检测与调课推荐
- 输入：JSON 格式排课数据（每条记录含课程名/教师/教室/班级/周次/星期/节次）
- 处理：构建时段占用图，按 教师/教室/班级 三维检测冲突，
        对每个冲突尝试在同日相邻节次或本周其他空闲时段给出可执行调课建议。
- 输出：Markdown 冲突报告 + 可选 JSON 结构化结果（--json）

零依赖、纯标准库；用户可控字段已做 HTML 实体转义与长度截断防 XSS。

触发语句示例：
  帮我检查这学期课表有没有冲突
  分析这份课表的冲突并给调课建议 schedule.json
"""

import argparse
import json
import sys
import html
from collections import defaultdict


WEEKDAY_NAMES = {
    "1": "周一", "2": "周二", "3": "周三", "4": "周四",
    "5": "周五", "6": "周六", "7": "周日",
}
DEFAULT_PERIOD_POOL = list(range(1, 13))
MAX_FIELD_LEN = 200
TEACHER_DAILY_OVERLOAD = 8


def sanitize(value):
    if value is None:
        return ""
    s = str(value).strip()
    if len(s) > MAX_FIELD_LEN:
        s = s[:MAX_FIELD_LEN] + "...(truncated)"
    return html.escape(s)


def parse_record(raw, idx):
    """解析一条课程记录，关键字段缺失时抛 ValueError 由调用方收集为 invalid."""
    if not isinstance(raw, dict):
        raise ValueError(f"#{idx} 非对象类型")

    course = sanitize(raw.get("course") or raw.get("name"))
    teacher = sanitize(raw.get("teacher"))
    room = sanitize(raw.get("room"))
    class_name = sanitize(raw.get("class") or raw.get("class_name"))

    # 必填校验（教师、教室、班级均不能空——否则无法检测对应维度冲突）
    missing = []
    if not teacher:
        missing.append("teacher")
    if not room:
        missing.append("room")
    if not class_name:
        missing.append("class")
    if missing:
        raise ValueError("#%d 关键字段缺失: %s" % (idx,
                                                   ",".join(missing)))

    # ---- 周次解析 ----
    if raw.get("weeks"):
        if isinstance(raw["weeks"], list):
            try:
                weeks = sorted({int(w) for w in raw["weeks"]})
            except Exception:
                raise ValueError("#%d weeks 列表元素非整数" % idx)
            if not weeks:
                raise ValueError("#%d weeks 为空" % idx)
        elif isinstance(raw["weeks"], str) and "-" in raw["weeks"]:
            try:
                a, b = raw["weeks"].split("-", 1)
                weeks = list(range(int(a), int(b) + 1))
            except Exception:
                raise ValueError("#%d weeks 区间格式无效" % idx)
        else:
            raise ValueError("#%d weeks 格式无效" % idx)
    else:
        ws = int(raw.get("week_start", 0))
        we = int(raw.get("week_end", 0))
        if ws <= 0 or we < ws:
            raise ValueError("#%d 周次范围无效" % idx)
        weeks = list(range(ws, we + 1))

    # ---- 星期解析（兼容中文输入）----
    wd_raw = str(raw.get("weekday", "")).strip()
    cn_map = {"一": "1", "二": "2", "三": "3", "四": "4",
              "五": "5", "六": "6", "日": "7", "天": "7"}
    for k, v in cn_map.items():
        wd_raw = wd_raw.replace(k, v)
    digits_only = "".join(c for c in wd_raw if c.isdigit())
    weekday_key = digits_only[0] if digits_only else ""
    if int(weekday_key) > 7:
        raise ValueError("#%d weekday 取值应在 1-7" % idx)

    # ---- 节次解析 ----
    p_raw = raw.get("periods", raw.get("period"))
    periods_list = None
    if isinstance(p_raw, list):
        periods_list = sorted({int(x) for x in p_raw})
    elif p_raw not in (None, "", []):
        ps = str(p_raw).strip()
        parts = re_split_periods(ps)
        periods_list = sorted({int(p.strip())
                               for p in parts})
    else:
        raise ValueError("#%d periods 缺失" % idx)
    if not periods_list:
        raise ValueError("#%d periods 解析后为空" % idx)

    return {
        "id": idx,
        "course": course,
        "teacher": teacher,
        "room": room,
        "class": class_name,
        "weekday": str(weekday_key),
        "periods": periods_list,
        "weeks": weeks,
    }


def re_split_periods(s):
    out = [s]
    for sep in [",", ",", ";"]:
        new_out = []
        for chunk in out:
            new_out.extend(chunk.split(sep))
        out = new_out
    return [x for x in out if x]


def load_schedule(path_or_text):
    import os.path as op
    text_or_path = path_or_text
    data = None
    try:
        if op.exists(text_or_path):
            with open(text_or_path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(path_or_text)
    except Exception as e:
        raise SystemExit("[load_schedule] JSON 解析失败：%s" % e)

    src = data.get("schedule") if isinstance(data, dict) else data
    valid, invalid = [], []
    seen_ids_dupes = set()
    for i, r in enumerate(src, 1):
        rec_id_input = r.get("id")
        if rec_id_input is not None:
            rid_str = str(rec_id_input).strip()
            if rid_str in seen_ids_dupes:
                invalid.append({
                    "index": i,
                    "error":
                        sanitize(
                            "#%d id=%r 与前序重复" % (i, rid_str)),
                    "raw":
                        sanitize(json.dumps(r, ensure_ascii=False)),
                })
                continue
            seen_ids_dupes.add(rid_str)
        try:
            rec = parse_record(r, i)
            valid.append(rec)
        except Exception as ex:
            invalid.append({"index": i,
                            "error": sanitize(str(ex)),
                            "raw":
                                sanitize(json.dumps(r,
                                                    ensure_ascii=False))})
    return valid, invalid


def _format_weeks_range(week_int_list):
    """把整数周次列表压缩成可读字符串，如 [1,2,3,5,6] -> '1-3,5-6'."""
    ws_sorted = sorted(set(int(w) for w in week_int_list))
    out_parts = []
    i_start = None
    prev_w = None
    for w_curr in ws_sorted + [None]:
        if i_start is None:
            i_start = w_curr
            prev_w = w_curr
            continue
        if w_curr is not None and w_curr == prev_w + 1:
            prev_w = w_curr
            continue
        # 断档或结尾——结算一段
        seg_end_val = prev_w
        if i_start == seg_end_val:
            out_parts.append("%d" % i_start)
        else:
            out_parts.append("%d-%d" % (i_start, seg_end_val))
        if w_curr is None:
            break
        i_start = w_curr
        prev_w = w_curr
    return ",".join(out_parts)


def detect_pair(ra, rb):
    """检测两条记录是否在同一时段(weekday+period+week)上占用相同资源。
       返回冲突列表（可能为空）。"""
    # 不同星期不可能同时段冲突——直接返回空
    if ra["weekday"] != rb["weekday"]:
        return []

    shared_pers = set(ra["periods"]) & set(rb["periods"])
    shared_weeks = set(ra["weeks"]) & set(rb["weeks"])
    if not shared_pers or not shared_weeks:
        return []

    type_labels_list = []
    sample_teacher = ""
    sample_room = ""
    sample_class_ = ""

    if ra["teacher"] and ra["teacher"] == rb["teacher"]:
        type_labels_list.append("教师冲突")
        sample_teacher = ra["teacher"]

    if ra["room"] and ra["room"] == rb["room"]:
        type_labels_list.append("教室冲突")
        sample_room = ra["room"]

    if ra["class"] and ra["class"] == rb["class"]:
        type_labels_list.append("班级冲突")
        sample_class_ = ra["class"]

    if not type_labels_list:
        return []

    type_labels_str = "+".join(type_labels_list)
    shared_weeks_str = _format_weeks_range(shared_weeks)
    pair_conflicts = []
    # 按 period 聚合（同对课同一时段多周压缩为一条记录，避免重复行）
    for sp in sorted(shared_pers):
        pair_conflicts.append({
            "type": type_labels_str,
            "a": ra["id"],
            "b": rb["id"],
            "courseA": ra["course"],
            "courseB": rb["course"],
            "teacher": sample_teacher,
            "room": sample_room,
            "class": sample_class_,
            "weekdayKey":
                WEEKDAY_NAMES[str(ra["weekday"])],
            "weekdayNum": ra["weekday"],
            "period": sp,
            "weekListStr": shared_weeks_str,
            "_sharedWeeksRaw":
                sorted(shared_weeks),
        })
    return pair_conflicts


def find_free_slots(conflict_slot, sessions_lookup_values):
    """为冲突中的课程 B 找出可移动到的安全空闲节次。

    安全定义：候选时段在当日没有任何其他会话同时占用课程 B 的教师、
    教室、班级中任何一项。返回最多 5 个候选，按距原节次的距离排序。
    """
    wd_num = conflict_slot["weekdayNum"]
    target_b_id = conflict_slot.get("b")

    # 取得被调课方（记录 B）的完整信息
    sess_b_obj = None
    for s_other in sessions_lookup_values:
        if s_other.get("id") == target_b_id:
            sess_b_obj = s_other
            break

    if sess_b_obj is not None:
        # 完整三资源检查：候选节次不能让 B 的任一关键资源与他人重叠，
        # 同时排除掉自身原本就占用的节次。
        bad_periods_set = set(sess_b_obj["periods"])
        for s_other in sessions_lookup_values:
            if s_other is sess_b_obj:
                continue
            if s_other["weekday"] != wd_num:
                continue
            share_teach = bool(
                s_other["teacher"]) and \
                s_other["teacher"] == sess_b_obj["teacher"]
            share_rm = bool(s_other["room"]) and \
                s_other["room"] == sess_b_obj["room"]
            share_cls = bool(s_other["class"]) and \
                s_other["class"] == sess_b_obj["class"]
            if not (share_teach or share_rm or share_cls):
                continue
            bad_periods_set.update(s_other["periods"])

        free_pool_today = [p for p in DEFAULT_PERIOD_POOL
                           if p not in bad_periods_set]
        rationale_prefix = "全维安全(教师/教室/班级)"
    else:
        # 兜底退化版本：仅按教室维度过滤
        pers_in_use_at_same_room_that_day = set()
        target_room_val = conflict_slot["room"]
        for sess in sessions_lookup_values:
            if sess["weekday"] != wd_num or \
               sess["room"] != target_room_val:
                continue
            pers_in_use_at_same_room_that_day.update(sess[
                "periods"])
        free_pool_today = [
            p for p in DEFAULT_PERIOD_POOL
            if p not in pers_in_use_at_same_room_that_day]
        rationale_prefix = "仅教室维度"

    candidates_sorted_by_proximity_to_conf_per = sorted(
        [{"move_to_day":
              WEEKDAY_NAMES[str(wd_num)],
          "move_to_period": fp,
          "rationale":
              "%s 在%s 第%d节 空闲"
              % (rationale_prefix,
                 WEEKDAY_NAMES[str(wd_num)], fp),
         } for fp in free_pool_today],
        key=lambda x: abs(x["move_to_period"] -
                          int(conflict_slot["period"])))[:5]

    return candidates_sorted_by_proximity_to_conf_per


def render_markdown(report_payload):
    """渲染最终 Markdown 报告。每个 list 元素自带结尾换行。"""
    out = []
    out.append("# 课程表冲突检测报告\n\n")
    summary_dict = report_payload["summary"]
    out.append("> 共 %d 条有效 | 无效 %d 条 | 冲突 %d 条\n"
               % (summary_dict["total_records"],
                  summary_dict["invalid_count"],
                  summary_dict["unique_conflicts"]))
    out.append("\n**生成时间**: 自动生成（教育场景 Skills）\n")

    invalid_n = report_payload["summary"]["invalid_count"]
    if invalid_n:
        out.append("\n## 一. 校验失败清单 (%d)\n\n" % invalid_n)
        out.append("| 序号 | 错误信息 |\n")
        out.append("|------|----------|\n")
        for inv_rec in report_payload["invalid_records"]:
            out.append("| #%s | `%s` |\n" % (inv_rec["index"],
                                            inv_rec["error"]))
        out.append("\n")
    else:
        out.append("\n## 一. 输入校验 ✅ 全部通过\n")

    conflicts_unique = report_payload["_conflicts_unique_ordered"]
    conf_count = len(conflicts_unique)
    type_counts = defaultdict(int)
    for uc in conflicts_unique:
        type_counts[uc["type"]] += 1

    if conf_count == 0:
        out.append("\n## 二. 冲突检测结果 ✅\n未检测出任何资源占用冲突。\n")
        out.append("> 三维资源图分析完成：教师×教室×班级 全部无重叠占用\n")
    else:
        breakdown_line = ", ".join("`%s=%d`" % (k, v)
                                   for k, v in
                                   sorted(type_counts.items()))
        out.append(
            "\n## 二. 冲突检测结果 ⚠️ 发现 **%d** 条独立冲突\n\n"
            "**分类统计**: %s\n" % (conf_count, breakdown_line))

        out.append("\n### 详细清单\n\n")
        col_headers = ("| 类型 | 课程A↔课程B | 教师 | "
                       "教室 | 班级 | 时间段 | 周次 |\n")
        sep_line = (
            "|------|---------------|------|------|------|--------|------|\n")
        out.append(col_headers)
        out.append(sep_line)

        for uc_item in conflicts_unique:
            time_str = "%s 第%d节" % (uc_item["weekdayKey"],
                                      uc_item["period"])
            row = "| `%s` | %s ↔ %s | %s | %s | %s | %s | %s |\n" % (
                html.escape(uc_item["type"]),
                uc_item["courseA"],
                uc_item["courseB"],
                uc_item["teacher"],
                uc_item["room"],
                uc_item["class"],
                time_str,
                html.escape(uc_item.get("weekListStr", "?")))
            out.append(row)
        out.append("\n*相同课程对同一时段的多周合并为一行*\n")

        lookup_vals = list(report_payload["_sessions_lookup"].values())

        out.append("\n## 三. 调课建议\n")
        any_suggestion_emitted = False
        for sugg_idx, uc_item in enumerate(conflicts_unique, 1):
            slots_found = find_free_slots(uc_item, lookup_vals)
            # 过滤掉与原时段相同的建议(避免推荐原地不动)
            slots_found = [s for s in slots_found
                           if s["move_to_period"]
                           != uc_item["period"]]
            if not slots_found:
                continue
            first_slot = slots_found[0]
            extra_slots_text = ", ".join([
                "%s第%d节" % (x["move_to_day"],
                             x["move_to_period"])
                for x in slots_found[1:]])
            suggest_text = ("%d. **[%s]** 将「%s」从%s 第%d节 调整到 **%s 第%d节**\n   *理由*: %s; 其他备选(%d): %s\n") % (
                                sugg_idx,
                                html.escape(uc_item["type"]),
                                uc_item["courseB"],
                                WEEKDAY_NAMES[str(int(uc_item[
                                    "weekdayNum"]))],
                                uc_item["period"],
                                first_slot["move_to_day"],
                                first_slot["move_to_period"],
                                first_slot["rationale"],
                                max(len(slots_found)-1, 0),
                                extra_slots_text or "(none)")
            out.append(suggest_text + "\n")
            any_suggestion_emitted = True
        if not any_suggestion_emitted:
            out.append("- 当前目标教室当日已满载或无可用空闲节次，建议教务人工介入调整教室或时间。\n")

    over_teachers = report_payload["warnings"]["overloaded_teachers"]
    if over_teachers:
        out.append("\n## 四. 高负荷预警 🔔 单人单日连排 ≥%d 节\n\n"
                   % TEACHER_DAILY_OVERLOAD)
        out.append("| 教师 | 时间 | 节数 |\n")
        out.append("|------|------|------|\n")
        for ot_warn in over_teachers:
            out.append("| %s | %s | %d |\n" %
                       (ot_warn["teacher"], ot_warn["when"],
                        ot_warn["count"]))

    out.append("\n---\n*由「课程表冲突检测 Skill」自动生成 · 零依赖纯标准库实现 · 支持 Markdown 报告输出与 --json 双模式交付*\n")
    return "".join(out)


def run(file_path_arg, want_json_arg=False):
    records_valid, records_invalid = load_schedule(file_path_arg)
    n_total_recs = len(records_valid) + len(records_invalid)

    conflicts_pairwise_flat = []
    nv = len(records_valid)
    for i in range(nv):
        ra = records_valid[i]
        for j in range(i+1, nv):
            rb = records_valid[j]
            pairs = detect_pair(ra, rb)
            if pairs:
                conflicts_pairwise_flat.extend(pairs)

    deduped_order_seen = {}
    deduped_list_ordered = []
    for cf in conflicts_pairwise_flat:
        # detect_pair 已经按 (period, weeks-range) 聚合，无需再拆周
        keystr = "%s|%s|%s|%s|%s|%s|p%d" % (
            cf["type"], cf["a"], cf["b"],
            cf["courseA"], cf["courseB"],
            cf.get("weekListStr", ""),
            cf["period"])
        if keystr in deduped_order_seen:
            continue
        deduped_order_seen[keystr] = True
        deduped_list_ordered.append(cf)

    teacher_load_counter = defaultdict(int)
    for rr in records_valid:
        for pp_used in rr["periods"]:
            teacher_load_counter[(rr["teacher"], rr["weekday"])] += 1
    overloaded_teachers_final = [
        {"teacher": tname,
         "when": WEEKDAY_NAMES[wk_num],
         "count": cnt}
        for (tname, wk_num), cnt in teacher_load_counter.items()
        if cnt >= TEACHER_DAILY_OVERLOAD]

    sessions_lookup_internal = {rid_hash: rec_v
                                 for rid_hash, rec_v
                                 in [("S_%03d" % r["id"], r)
                                     for r in records_valid]}
    payload_assembly_complete_payload = dict(
        summary={
            "total_records": len(records_valid),
            "invalid_count": len(records_invalid),
            "total_inputs_scanned": n_total_recs,
            "unique_conflicts": len(deduped_list_ordered),
        },
        invalid_records=records_invalid,
        conflicts=[{kk: vv for kk, vv in cc.items()
                    if not kk.startswith("_")}
                   for cc in deduped_list_ordered],
        warnings={
            "overloaded_teachers": overloaded_teachers_final,
        },
        _sessions_lookup=sessions_lookup_internal,
        _unique_keys_ordered=list(deduped_order_seen.keys()),
        _conflicts_unique_ordered=[
            {kk: vv for kk, vv in cc.items()
             if not kk.startswith("_")}
            for cc in deduped_list_ordered],
    )

    md_text_rendered = render_markdown(payload_assembly_complete_payload)

    output_obj_public_view = {
        k: v for k, v in
        payload_assembly_complete_payload.items()
        if not k.startswith("_")
    }
    output_obj_public_view["markdown_report"] = md_text_rendered

    sys.stdout.write(md_text_rendered)
    if want_json_arg:
        sys.stdout.write("---JSON---\n")
        print(json.dumps(output_obj_public_view,
                         ensure_ascii=False))


if __name__ == "__main__":
    ap_obj = argparse.ArgumentParser(description="课程表冲突检测主程序")
    ap_obj.add_argument("schedule_file", nargs="?",
                        help="排课 JSON 文件路径")
    ap_obj.add_argument("--json", action="store_true",
                        help="追加打印结果 JSON")
    parsed_args_namespace = ap_obj.parse_args()
    fp_default_first_positional = parsed_args_namespace.schedule_file or ""
    if not fp_default_first_positional:
        raise SystemExit("用法: python analyze.py <schedule.json> [--json]")
    run(fp_default_first_positional,
        want_json_arg=parsed_args_namespace.json)
