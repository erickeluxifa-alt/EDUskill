#!/usr/bin/env python3
"""
人才培养方案版本对比分析器
输入：两份方案的解析结果(JSON)
输出：结构化差异报告（新增/删除/修改/数值变动）
"""

import sys
import json
import re
import difflib
from typing import Any


def normalize_text(text: str) -> str:
    """规范化文本，去除多余空白"""
    return re.sub(r'\s+', ' ', text.strip())


def compute_text_diff(text_a: str, text_b: str) -> list:
    """
    计算两段文本的差异，返回结构化 diff 列表
    每项: {"type": "equal/insert/delete/replace", "old": "...", "new": "..."}
    """
    lines_a = [l.strip() for l in text_a.split('\n') if l.strip()]
    lines_b = [l.strip() for l in text_b.split('\n') if l.strip()]

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    diffs = []

    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        if opcode == 'equal':
            continue
        elif opcode == 'insert':
            diffs.append({
                "type": "insert",
                "old": "",
                "new": "\n".join(lines_b[b0:b1]),
                "description": f"新增 {b1-b0} 行内容",
            })
        elif opcode == 'delete':
            diffs.append({
                "type": "delete",
                "old": "\n".join(lines_a[a0:a1]),
                "new": "",
                "description": f"删除 {a1-a0} 行内容",
            })
        elif opcode == 'replace':
            diffs.append({
                "type": "replace",
                "old": "\n".join(lines_a[a0:a1]),
                "new": "\n".join(lines_b[b0:b1]),
                "description": f"修改内容（{a1-a0}行 → {b1-b0}行）",
            })

    return diffs


def match_sections(sections_a: list, sections_b: list) -> list:
    """
    匹配两版本的章节，返回对应关系列表
    每项: {"title_a": ..., "title_b": ..., "section_a": ..., "section_b": ..., "match_type": "exact/fuzzy/only_a/only_b"}
    """
    matched = []
    used_b = set()

    # 精确匹配（标题完全一致）
    for sa in sections_a:
        found = False
        for i, sb in enumerate(sections_b):
            if i in used_b:
                continue
            if normalize_text(sa["title"]) == normalize_text(sb["title"]):
                matched.append({
                    "title_a": sa["title"],
                    "title_b": sb["title"],
                    "section_a": sa,
                    "section_b": sb,
                    "match_type": "exact",
                })
                used_b.add(i)
                found = True
                break
        if not found:
            # 模糊匹配（标题相似度 > 60%）
            best_ratio = 0
            best_idx = -1
            for i, sb in enumerate(sections_b):
                if i in used_b:
                    continue
                ratio = difflib.SequenceMatcher(None, sa["title"], sb["title"]).ratio()
                if ratio > 0.6 and ratio > best_ratio:
                    best_ratio = ratio
                    best_idx = i
            if best_idx >= 0:
                sb = sections_b[best_idx]
                matched.append({
                    "title_a": sa["title"],
                    "title_b": sb["title"],
                    "section_a": sa,
                    "section_b": sb,
                    "match_type": "fuzzy",
                })
                used_b.add(best_idx)
            else:
                matched.append({
                    "title_a": sa["title"],
                    "title_b": None,
                    "section_a": sa,
                    "section_b": None,
                    "match_type": "only_a",
                })

    # 版本B中未匹配的章节（新增章节）
    for i, sb in enumerate(sections_b):
        if i not in used_b:
            matched.append({
                "title_a": None,
                "title_b": sb["title"],
                "section_a": None,
                "section_b": sb,
                "match_type": "only_b",
            })

    return matched


def extract_numbers(text: str) -> dict:
    """从文本中提取所有数字及其上下文"""
    pattern = r'(\d+\.?\d*)\s*([个门节学分时%年月周天]|学分|学时|学期|门课|节课)?'
    numbers = {}
    for m in re.finditer(pattern, text):
        key = f"数值_{m.start()}"
        numbers[key] = {
            "value": m.group(1),
            "unit": m.group(2) or "",
            "context": text[max(0, m.start()-10):m.end()+10],
        }
    return numbers


def compare_key_data(kd_a: dict, kd_b: dict) -> list:
    """对比两版本的关键数值字段"""
    field_names = {
        "major_name": "专业名称",
        "major_code": "专业代码",
        "degree_length": "学制年限",
        "degree_type": "学位类型",
        "total_credits": "总学分",
        "total_hours": "总学时",
        "required_ratio": "必修课比例",
        "elective_ratio": "选修课比例",
        "practice_ratio": "实践教学比例",
    }

    changes = []
    all_keys = set(list(kd_a.keys()) + list(kd_b.keys()))

    for key in all_keys:
        if key not in field_names:
            continue
        val_a = kd_a.get(key, "（未识别）")
        val_b = kd_b.get(key, "（未识别）")
        if normalize_text(str(val_a)) != normalize_text(str(val_b)):
            changes.append({
                "field": field_names[key],
                "old_value": val_a,
                "new_value": val_b,
                "change_type": "数值变动" if any(c.isdigit() for c in str(val_a) + str(val_b)) else "文字变动",
            })

    return changes


def diff_plans(plan_a: dict, plan_b: dict) -> dict:
    """
    主对比函数
    返回完整差异报告
    """
    sections_a = plan_a.get("sections", [])
    sections_b = plan_b.get("sections", [])
    kd_a = plan_a.get("key_data", {})
    kd_b = plan_b.get("key_data", {})

    # 1. 关键数据对比
    key_data_changes = compare_key_data(kd_a, kd_b)

    # 2. 章节匹配
    section_matches = match_sections(sections_a, sections_b)

    # 3. 逐章节差异分析
    section_diffs = []
    for match in section_matches:
        match_type = match["match_type"]
        sa = match["section_a"]
        sb = match["section_b"]

        if match_type == "only_a":
            section_diffs.append({
                "title": match["title_a"],
                "change_type": "deleted",
                "change_label": "🗑️ 删除章节",
                "old_title": match["title_a"],
                "new_title": None,
                "content_diffs": [],
                "summary": f"旧版中存在此章节「{match['title_a']}」，新版已删除",
            })

        elif match_type == "only_b":
            section_diffs.append({
                "title": match["title_b"],
                "change_type": "added",
                "change_label": "✅ 新增章节",
                "old_title": None,
                "new_title": match["title_b"],
                "content_diffs": [],
                "summary": f"新版新增章节「{match['title_b']}」",
            })

        elif match_type in ("exact", "fuzzy"):
            content_a = sa.get("content", "")
            content_b = sb.get("content", "")

            # 检查标题变化
            title_changed = match_type == "fuzzy" and match["title_a"] != match["title_b"]

            # 内容差异
            if normalize_text(content_a) == normalize_text(content_b):
                if not title_changed:
                    continue  # 无变化，跳过
                content_diffs = []
            else:
                content_diffs = compute_text_diff(content_a, content_b)

            if content_diffs or title_changed:
                change_label = "✏️ 标题修改" if title_changed and not content_diffs else "📝 内容修改"
                if title_changed and content_diffs:
                    change_label = "✏️ 标题+内容修改"

                # 计算相似度
                ratio = difflib.SequenceMatcher(None, content_a, content_b).ratio()
                similarity = f"{ratio:.0%}"

                section_diffs.append({
                    "title": match["title_b"] or match["title_a"],
                    "change_type": "modified",
                    "change_label": change_label,
                    "old_title": match["title_a"],
                    "new_title": match["title_b"],
                    "title_changed": title_changed,
                    "content_similarity": similarity,
                    "content_diffs": content_diffs,
                    "summary": f"内容相似度 {similarity}，共 {len(content_diffs)} 处变动",
                })

    # 4. 统计
    stats = {
        "total_changes": len(section_diffs) + len(key_data_changes),
        "sections_added": sum(1 for d in section_diffs if d["change_type"] == "added"),
        "sections_deleted": sum(1 for d in section_diffs if d["change_type"] == "deleted"),
        "sections_modified": sum(1 for d in section_diffs if d["change_type"] == "modified"),
        "key_data_changes": len(key_data_changes),
    }

    return {
        "stats": stats,
        "key_data_changes": key_data_changes,
        "section_diffs": section_diffs,
    }


def format_diff_report(diff_result: dict, plan_a: dict, plan_b: dict) -> str:
    """格式化输出差异报告（Markdown）"""
    stats = diff_result["stats"]
    key_changes = diff_result["key_data_changes"]
    section_diffs = diff_result["section_diffs"]

    kd_a = plan_a.get("key_data", {})
    kd_b = plan_b.get("key_data", {})

    lines = [
        "# 人才培养方案版本对比报告",
        "",
        "## 方案信息",
        f"| 项目 | 旧版（版本A） | 新版（版本B） |",
        f"|------|-------------|-------------|",
        f"| 专业名称 | {kd_a.get('major_name', '未识别')} | {kd_b.get('major_name', '未识别')} |",
        f"| 专业代码 | {kd_a.get('major_code', '未识别')} | {kd_b.get('major_code', '未识别')} |",
        f"| 总学分 | {kd_a.get('total_credits', '未识别')} | {kd_b.get('total_credits', '未识别')} |",
        "",
        "## 变更摘要",
        f"| 变更类型 | 数量 |",
        f"|---------|------|",
        f"| 关键数据变动 | {stats['key_data_changes']} 项 |",
        f"| 新增章节 | {stats['sections_added']} 个 |",
        f"| 删除章节 | {stats['sections_deleted']} 个 |",
        f"| 修改章节 | {stats['sections_modified']} 个 |",
        f"| **合计变更** | **{stats['total_changes']} 处** |",
        "",
    ]

    if stats["total_changes"] == 0:
        lines.append("✅ 两份方案内容完全一致，未发现任何修改痕迹。")
        return "\n".join(lines)

    # 关键数据变动
    if key_changes:
        lines.append("## 关键数据变动")
        lines.append("")
        lines.append("| 字段 | 旧版 | 新版 | 变动类型 |")
        lines.append("|------|------|------|---------|")
        for chg in key_changes:
            lines.append(f"| {chg['field']} | {chg['old_value']} | {chg['new_value']} | {chg['change_type']} |")
        lines.append("")

    # 章节差异详情
    if section_diffs:
        lines.append("## 章节变更详情")
        lines.append("")

        for diff in section_diffs:
            lines.append(f"### {diff['change_label']}：{diff['title']}")

            if diff["change_type"] == "added":
                lines.append(f"> 新增章节，旧版中不存在")

            elif diff["change_type"] == "deleted":
                lines.append(f"> 旧版章节已删除，新版中不存在")

            elif diff["change_type"] == "modified":
                if diff.get("title_changed"):
                    lines.append(f"- **标题变化**：`{diff['old_title']}` → `{diff['new_title']}`")
                lines.append(f"- **内容相似度**：{diff.get('content_similarity', 'N/A')}")
                lines.append(f"- **变动摘要**：{diff['summary']}")

                content_diffs = diff.get("content_diffs", [])
                if content_diffs:
                    lines.append("")
                    lines.append("**具体变动：**")
                    lines.append("")
                    for i, cdiff in enumerate(content_diffs[:10], 1):  # 最多展示10处
                        dtype = cdiff["type"]
                        if dtype == "delete":
                            lines.append(f"{i}. 🗑️ **删除**：`{cdiff['old'][:100]}{'...' if len(cdiff['old']) > 100 else ''}`")
                        elif dtype == "insert":
                            lines.append(f"{i}. ➕ **新增**：`{cdiff['new'][:100]}{'...' if len(cdiff['new']) > 100 else ''}`")
                        elif dtype == "replace":
                            lines.append(f"{i}. ✏️ **修改**：")
                            lines.append(f"   - 旧：`{cdiff['old'][:80]}{'...' if len(cdiff['old']) > 80 else ''}`")
                            lines.append(f"   - 新：`{cdiff['new'][:80]}{'...' if len(cdiff['new']) > 80 else ''}`")

                    if len(content_diffs) > 10:
                        lines.append(f"  *（还有 {len(content_diffs) - 10} 处变动未展示）*")

            lines.append("")

    lines.append("---")
    lines.append("*本报告通过文本差异算法自动生成，建议结合原文核实。*")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "用法: diff_plans.py <plan_a_json> <plan_b_json>"}, ensure_ascii=False))
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        plan_a = json.load(f)
    with open(sys.argv[2], "r", encoding="utf-8") as f:
        plan_b = json.load(f)

    diff_result = diff_plans(plan_a, plan_b)
    report_md = format_diff_report(diff_result, plan_a, plan_b)

    output = {
        "diff_result": diff_result,
        "report_markdown": report_md,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
