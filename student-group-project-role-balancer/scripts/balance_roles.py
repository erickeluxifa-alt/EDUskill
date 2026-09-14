#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def fail(message):
    raise ValueError(message)


def load(path):
    if path == '-':
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding='utf-8'))


def validate(data):
    if not isinstance(data, dict):
        fail('输入必须是 JSON 对象')
    project = data.get('project')
    roles = data.get('roles')
    students = data.get('students')
    if not isinstance(project, dict) or not isinstance(roles, list) or not isinstance(students, list):
        fail('project、roles、students 均为必填字段')
    group_count = project.get('group_count')
    group_size = project.get('group_size')
    if not isinstance(group_count, int) or group_count <= 0 or not isinstance(group_size, int) or group_size <= 0:
        fail('group_count 和 group_size 必须为正整数')
    if len(students) != group_count * group_size:
        fail('学生人数必须等于 group_count × group_size')
    role_ids = []
    capacity_total = 0
    for role in roles:
        if not isinstance(role, dict) or not role.get('id') or not role.get('name'):
            fail('每个角色必须包含非空 id 和 name')
        if role['id'] in role_ids:
            fail('角色 ID 重复: ' + role['id'])
        capacity = role.get('capacity')
        if not isinstance(capacity, int) or capacity <= 0:
            fail('角色 capacity 必须为正整数: ' + role['id'])
        role_ids.append(role['id'])
        capacity_total += capacity
    if capacity_total != group_size:
        fail('角色容量总和必须等于 group_size')
    student_ids = []
    for student in students:
        if not isinstance(student, dict) or not student.get('id'):
            fail('每个学生必须包含非空 id')
        if student['id'] in student_ids:
            fail('学生 ID 重复: ' + student['id'])
        student_ids.append(student['id'])
        for key in ('skills', 'preferred_roles'):
            if key in student and not isinstance(student[key], list):
                fail(key + ' 必须是数组: ' + student['id'])
        unknown = set(student.get('preferred_roles', [])) - set(role_ids)
        if unknown:
            fail('存在未知角色偏好: ' + ','.join(sorted(unknown)))
    return project, roles, students, data.get('rules') or {}


def score(student, role, assigned):
    skills = set(student.get('skills', []))
    required = set(role.get('skills', []))
    match = len(skills & required)
    preferred = 1 if role['id'] in student.get('preferred_roles', []) else 0
    same_skill = sum(bool(skills & set(item.get('skills', []))) for item in assigned)
    return (match * 100 + preferred * 20 - same_skill, -len(assigned), student['id'])


def build(data):
    project, roles, students, rules = validate(data)
    students = sorted(students, key=lambda x: x['id'])
    groups = [[] for _ in range(project['group_count'])]
    # Round-robin placement balances group sizes and keeps the result deterministic.
    for index, student in enumerate(students):
        groups[index % len(groups)].append({'student': student, 'role': None})

    role_map = {role['id']: role for role in roles}
    plans = []
    warnings = []
    max_same = rules.get('max_same_skill_in_group', 2)
    for group_index, members in enumerate(groups, 1):
        assigned = []
        remaining = {role['id']: role['capacity'] for role in roles}
        for member in sorted(members, key=lambda item: item['student']['id']):
            choices = [role for role in roles if remaining[role['id']] > 0]
            choices.sort(key=lambda role: score(member['student'], role, assigned), reverse=True)
            role = choices[0]
            remaining[role['id']] -= 1
            member['role'] = role['id']
            assigned.append(member['student'])
        skill_counts = {}
        for member in members:
            for skill in member['student'].get('skills', []):
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
        group_warnings = []
        for skill, count in sorted(skill_counts.items()):
            if count > max_same:
                group_warnings.append(f'技能 {skill} 在本组出现 {count} 次，超过建议上限 {max_same}')
        missing = [role['name'] for role in roles if not any(m['role'] == role['id'] for m in members)]
        if missing:
            group_warnings.append('角色覆盖缺口: ' + '、'.join(missing))
        if group_warnings:
            warnings.extend([f'第{group_index}组：{item}' for item in group_warnings])
        plans.append({'group': f'G{group_index:02d}', 'members': [
            {'student_id': m['student']['id'], 'student_name': m['student'].get('name', ''),
             'role_id': m['role'], 'role_name': role_map[m['role']]['name'],
             'preferred': m['role'] in m['student'].get('preferred_roles', []),
             'skill_match': bool(set(m['student'].get('skills', [])) & set(role_map[m['role']].get('skills', [])))}
            for m in sorted(members, key=lambda item: item['student']['id'])
        ], 'warnings': group_warnings})
    status = 'REVIEW_REQUIRED' if plans else 'ERROR'
    return {'status': status, 'project': project, 'groups': plans, 'warnings': warnings,
            'summary': {'group_count': len(plans), 'student_count': len(students), 'warning_count': len(warnings)}}


def markdown(result):
    lines = [f"# {result['project'].get('name', '项目')}：小组角色分配预览", '', f"状态：`{result['status']}`", '',
             '## 分组方案', '']
    for group in result['groups']:
        lines += [f"### {group['group']}", '', '| 学生 | 角色 | 偏好满足 | 能力匹配 |', '|---|---|---|---|']
        for member in group['members']:
            lines.append(f"| {member['student_name']} ({member['student_id']}) | {member['role_name']} | {'是' if member['preferred'] else '否'} | {'是' if member['skill_match'] else '否'} |")
        if group['warnings']:
            lines += ['', '问题提示：'] + [f'- {warning}' for warning in group['warnings']]
        lines.append('')
    lines += ['## 人工确认', '', '- 确认学生分组与角色意愿。', '- 确认特殊支持、协作关系和项目安全要求。', '- 必要时调整后重新运行。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input')
    parser.add_argument('--out-dir', default='output')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--strict', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        if args.demo:
            data = json.loads((Path(__file__).parents[1] / 'examples' / 'sample_input.json').read_text(encoding='utf-8'))
        elif args.input:
            data = load(args.input)
        else:
            fail('请提供 --demo 或 --input')
        result = build(data)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            out = Path(args.out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / 'role_plan.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            (out / 'role_plan.md').write_text(markdown(result), encoding='utf-8')
            print(json.dumps({'output': str(out), 'status': result['status'], 'summary': result['summary']}, ensure_ascii=False))
        if args.strict and result['warnings']:
            return 2
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = {'status': 'ERROR', 'error': str(exc)}
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
