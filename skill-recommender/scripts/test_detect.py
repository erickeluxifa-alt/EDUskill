#!/usr/bin/env python3
"""
测试环境检测功能
用法: python3 scripts/test_detect.py
"""
import sys
from pathlib import Path

def detect_skills_directory():
    """
    自动检测skills目录位置。
    新skill将安装到与skill-recommender相同的父目录（skills目录）。
    """
    script_path = Path(__file__).resolve()
    
    print(f"📍 脚本位置: {script_path}")
    print(f"   父目录(-1): {script_path.parent}")
    print(f"   父目录(-2): {script_path.parent.parent}")
    print(f"   父目录(-3): {script_path.parent.parent.parent}")
    print()

    # 向上3级得到skills目录
    skills_dir = script_path.parent.parent.parent

    # 智能检测环境名称
    if '.openclaw' in skills_dir.parts:
        env_name = "OpenClaw"
    elif '.claude' in skills_dir.parts:
        env_name = "Standard"
    else:
        # 通用环境：查找skills目录的父目录名称
        parent_dir = skills_dir.parent.name
        if parent_dir.startswith('.'):
            env_name = parent_dir[1:].capitalize()
        else:
            env_name = "Custom Agent"

    return skills_dir, env_name

def main():
    print("=" * 60)
    print("🔍 Skill Recommender 环境检测测试")
    print("=" * 60)
    print()
    
    skills_dir, env_name = detect_skills_directory()
    
    print("✅ 检测结果:")
    print(f"   环境名称: {env_name}")
    print(f"   Skills目录: {skills_dir}")
    print(f"   Skills目录存在: {'是' if skills_dir.exists() else '否'}")
    print()
    
    # 示例：新skill会安装到哪里
    example_skill = "new-skill-example"
    install_path = skills_dir / example_skill
    print(f"💡 示例: 新skill '{example_skill}' 将安装到:")
    print(f"   {install_path}")
    print()
    
    # 列出当前skills目录下已有的skills
    if skills_dir.exists():
        print("📦 当前已安装的skills:")
        skills = [d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        if skills:
            for skill in sorted(skills):
                print(f"   - {skill}")
        else:
            print("   (无)")
    
    print()
    print("=" * 60)

if __name__ == "__main__":
    main()
