---
name: schedule-conflict-detective
displayName: 课程表冲突检测与调课推荐
version: 1.0.0
description: 教务处 / 院系教学秘书学期初排课冲突检测器——输入排课 JSON 即可自动检测教师×教室×班级三维资源占用冲突并给出可执行的调课建议。
author: ht
trigger:
  - 检查课表冲突
  - 排课冲突检测
  - 帮我检查这学期课表有没有冲突
  - 分析这份课表的冲突并给调课建议
  - 调课建议
---

# Skill：课程表冲突检测与调课推荐

## 一、核心场景

- **目标角色**：教务处管理员、院系教学秘书、教学副院长助理
- **触发时机**：
    * 学期初教务系统导出整学期课表后批量体检；
    * 中途临时调课后核对是否引入新冲突；
    * 多院系联合排课时合并多份课表后的交叉检查。

## 二、能力定位

输入一份以 JSON 描述的整学期（或区间）课程安排，
对每两条记录在「同星期 × 同节次 × 同周次」三元组上做教师、教室、班级三维度重叠比对，
输出 Markdown 冲突报告；并对每个独立冲突给出当日可移动到的安全空闲节次建议
（候选时段需保证移动后不会产生新的三方资源碰撞）。

## 三、触发语句

- "帮我检查这学期课表有没有冲突"
- "分析这份课表的冲突并给调课建议 path/to/schedule.json"
- "排课冲突检测 examples/sample_with_conflicts.json"
- 自然语言中包含"课表""冲突""教室重复""老师撞课"等关键词均会命中

## 四、输入格式

JSON 根节点可为数组或对象 `{ "schedule": [...] }`。单条记录字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `course` 或 `name` | 是 | 课程名 |
| `teacher` | 是 | 任课教师姓名 |
| `room` | 是 | 上课教室编码 |
| `class` 或 `class_name` | 是 | 行政班名或选课群组标识 |
| `weekday` | 是 | 取值 `"1"`~`"7"`，兼容中文"周一"等写法 |
| `periods` 或 `period` | 是 | 节次列表 `[1,2]` 或单值 `3` 或字符串"1,2" |
| `weeks` 选其一 | 否 | 显式周次数组 `[1..16]` 或区间串 `"9-12"` |
| `week_start`+`week_end` 备用 | 否 | 当无 weeks 时使用 |

## 五、输出

1. Markdown 报告含四个章节：校验失败清单 / 冲突检测结果(分类统计+详细表格) /
   调课建议(可执行节次迁移方案)/ 高负荷预警；
2. 通过 `--json` 参数追加输出结构化结果，便于下游系统消费。

## 六、核心流程

```
load_schedule → parse_record(sanitize+validate)
              ↓
detect_pair(O(n²)) 三维资源共享判定
              ↓
按 (type,courseA,courseB,weekListStr,period) 去重聚合相邻周次
              ↓
find_free_slots 全维安全过滤(避免新冲突)
              ↓
render_markdown 输出四段式报告
```

复杂度 O(n²)，n=有效记录数；典型高校院系一学期约500-2000条记录可在2秒内完成。

## 七、依赖与限制

- 仅使用 Python 标准库 (argparse/json/sys/html/collections)，零外部依赖；
- 不调用任何内部 API、不存储任何敏感数据；
- 用户可控字段已做 HTML 实体转义及长度截断防注入；
- 当前不感知法定节假日和校历周次偏移，按纯公历处理；
- 单日最大可排查节次池固定为第 1-12 节；
- 教师/教室/班级任一字段为空时跳过对应维度的检测（无法判断是否相同）。

## 八、示例用法

```bash
# 无冲突样例快速验证
python3 scripts/schedule_analyze.py examples/sample_no_conflict.json

# 含真实冲突的样例验证完整流程
python3 scripts/schedule_analyze.py examples/sample_with_conflicts.json --json > report.json
head -50 report.json   # 查看 markdown 报告部分
tail -1 report.json    # 查看结构化 JSON 部分(可用于二次开发集成)

# 与现有教务系统对接示例:
# 导出 CSV -> jq 转 JSON -> 直接喂入本脚本即可生成开学前排课审计报告
```

## 九、不做范围(out-of-scope)

- 自动写入教务系统反向修改原始数据；
- 学生个人视角的课程时间合理性评估;
- 多校区跨校区通勤时长建模；
- 实验室设备预约管理（属于姊妹场景 skill 的范围）。󠅣󠅤󠄷󠄹󠄱󠅣󠄸󠄴󠄶󠅤󠄳󠄲󠅦󠅥󠅦󠄵󠅡󠄷󠄸󠅢󠄷󠅦󠅦󠄷󠄲󠄵󠅢󠅥󠅡󠅢󠅤󠄶
