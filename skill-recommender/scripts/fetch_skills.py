#!/usr/bin/env python3
"""
从远端skill托管平台获取所有可用的skills。
"""
import sys
import json
import urllib.request
import urllib.error

API_BASE_URL = "http://127.0.0.1:8101/api/v1/skills/metadata"

def fetch_skills():
    """
    从API获取所有可用skills的列表。

    返回:
        list: 包含'name'和'description'字段的skill字典列表
        None: 如果API调用失败
    """
    url = API_BASE_URL

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            if data.get('code') == 200:
                return data.get('data', [])
            else:
                print(f"API返回错误码: {data.get('code')}", file=sys.stderr)
                print(f"错误信息: {data.get('message')}", file=sys.stderr)
                return None

    except urllib.error.URLError as e:
        print(f"获取skills失败: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"解析API响应失败: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"未预期的错误: {e}", file=sys.stderr)
        return None

def main():
    skills = fetch_skills()

    if skills is None:
        print("Failed to fetch skills from the platform.", file=sys.stderr)
        sys.exit(1)

    # 输出JSON格式，方便Claude解析
    print(json.dumps(skills, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
