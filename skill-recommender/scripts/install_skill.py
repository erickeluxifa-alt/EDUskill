#!/usr/bin/env python3
"""
下载并安装skill到默认skills目录。
"""
import sys
import os
import urllib.request
import urllib.error
import zipfile
import tempfile
import shutil
from pathlib import Path

def detect_skills_directory():
    """
    自动检测skills目录位置。
    新skill将安装到与skill-recommender相同的父目录（skills目录）。
    这样可以自动适配所有遵循标准目录结构的agent（Standard、OpenClaw或其他自定义agent）。

    目录结构假设:
    - ~/.xxx/skills/skill-recommender/scripts/install_skill.py
    - 向上3级得到skills目录
    """
    script_path = Path(__file__).resolve()

    # skill-recommender/scripts/install_skill.py -> skill-recommender -> skills
    # 向上两级到达skill-recommender目录，再向上一级到达skills目录
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
            # 去掉开头的点，首字母大写
            env_name = parent_dir[1:].capitalize()
        else:
            env_name = "Custom Agent"

    return skills_dir, env_name

DEFAULT_SKILLS_DIR, ENVIRONMENT_NAME = detect_skills_directory()

def download_skill(download_url, temp_file):
    """
    从指定URL下载skill的zip文件。

    参数:
        download_url (str): 下载URL
        temp_file (str): 保存下载文件的路径

    返回:
        bool: 成功返回True，失败返回False
    """
    try:
        print(f"正在从以下地址下载skill: {download_url}")
        with urllib.request.urlopen(download_url, timeout=30) as response:
            with open(temp_file, 'wb') as out_file:
                out_file.write(response.read())
        print(f"已下载到: {temp_file}")
        return True
    except urllib.error.URLError as e:
        print(f"下载skill失败: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"下载过程中发生未预期错误: {e}", file=sys.stderr)
        return False

def install_skill(zip_path, skill_name):
    """
    解压并安装skill到默认skills目录。

    参数:
        zip_path (str): skill zip文件的路径
        skill_name (str): skill的名称

    返回:
        bool: 成功返回True，失败返回False
    """
    install_dir = DEFAULT_SKILLS_DIR / skill_name

    try:
        # 如果skills目录不存在则创建
        DEFAULT_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        # 检查skill是否已存在
        if install_dir.exists():
            print(f"警告: Skill '{skill_name}' 已存在于 {install_dir}")
            print("正在删除现有skill...")
            shutil.rmtree(install_dir)

        # 解压zip文件
        print(f"正在安装skill到: {install_dir}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(DEFAULT_SKILLS_DIR)

        print(f"✅ Skill '{skill_name}' 安装成功!")
        return True

    except zipfile.BadZipFile as e:
        print(f"无效的zip文件: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"安装skill失败: {e}", file=sys.stderr)
        return False

def get_skill_info(skill_name):
    """
    读取并返回已安装skill的基本信息。

    参数:
        skill_name (str): skill的名称

    返回:
        dict: 包含名称和描述的skill信息
    """
    skill_md_path = DEFAULT_SKILLS_DIR / skill_name / "SKILL.md"

    try:
        with open(skill_md_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # 从YAML frontmatter中提取名称和描述
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    info = {'name': skill_name}

                    for line in frontmatter.strip().split('\n'):
                        if line.startswith('name:'):
                            info['name'] = line.split(':', 1)[1].strip().strip('"\'')
                        elif line.startswith('description:'):
                            info['description'] = line.split(':', 1)[1].strip().strip('"\'')

                    return info
    except Exception as e:
        print(f"警告: 无法读取skill信息: {e}", file=sys.stderr)

    return {'name': skill_name, 'description': 'N/A'}

def main():
    if len(sys.argv) != 3:
        print("用法: install_skill.py <skill_name> <download_url>", file=sys.stderr)
        sys.exit(1)

    skill_name = sys.argv[1]
    download_url = sys.argv[2]

    # 显示环境信息
    print(f"🔍 检测到当前环境: {ENVIRONMENT_NAME}")
    print(f"📂 Skill将安装到: {DEFAULT_SKILLS_DIR / skill_name}\n")

    # 创建临时文件用于下载
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
        temp_path = temp_file.name

    try:
        # 下载skill
        if not download_skill(download_url, temp_path):
            sys.exit(1)

        # 安装skill
        if not install_skill(temp_path, skill_name):
            sys.exit(1)

        # 获取并打印skill信息
        info = get_skill_info(skill_name)
        print(f"\n📦 Skill信息:")
        print(f"   环境: {ENVIRONMENT_NAME}")
        print(f"   名称: {info['name']}")
        print(f"   描述: {info.get('description', 'N/A')}")
        print(f"   位置: {DEFAULT_SKILLS_DIR / skill_name}")

    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    main()
