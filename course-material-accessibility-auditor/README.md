# Course Material Accessibility Auditor v1.0.0

## 核心场景
教师、教研员或课程资源管理员在发布课程讲义、任务单、公告和网页文本前，快速发现常见无障碍与可读性问题，得到可复核整改清单。

- 教育行业属性：课程资源发布前质量保障。
- 可复用范围：高校、职教、K12、企业培训的文本型课程材料。
- 核心增益：把标题、图片、链接、表格、可读性和隐私检查固化为离线 SOP。

## 触发示例
- “帮我检查这份课程讲义的无障碍问题”
- “课程公告发布前做一下可读性审核”
- “检查图片 alt、链接文字和标题层级”

## 输入
UTF-8 JSON，顶层字段：
- `title`：材料标题，字符串。
- `language`：可选，如 `zh-CN`。
- `sections`：数组；每项含 `heading`、`level`、`paragraphs`。
- `images`：可选数组；含 `id`、`alt`，装饰图可设 `decorative: true`。
- `links`：可选数组；含 `text`、`url`。
- `tables`：可选数组；含 `caption`、`headers`、`rows`。

## 运行
```bash
python3 scripts/audit_material.py examples/sample_material.json --out /tmp/material-audit
```
脚本零第三方依赖。输出 `audit.json` 和 `report.md`。

## 输出与确认
报告按阻断/高/中/低优先级列出证据和建议，并给出“人工确认后再发布”状态。工具不会修改源文件、不会写入 LMS/SIS、不会发送通知，因此无需撤销；删除输出目录即可清理本次结果。

## 限制
- 仅审计结构化文本与元数据，不解析 PDF、Word、PPT 或真实网页视觉布局。
- 过长句/段落阈值是启发式规则，不等于语言质量结论。
- 不检测颜色对比、键盘操作、字幕质量或屏幕阅读器实际体验。
- 不构成 WCAG 或任何法规的合规认证。

## 交付物料
`SKILL.md`、`README.md`、`scripts/audit_material.py`、`examples/`、`tests/`、`docs/test-report.md`。
