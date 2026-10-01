#!/usr/bin/env python3
"""
获取指定skill的下载链接。
"""
import sys
import json
import urllib.request
import urllib.error

API_BASE_URL = "http://127.0.0.1:8101/api/v1/skills/package"

def get_download_url(skill_name):
    """
    获取指定skill的下载URL。

    参数:
        skill_name (str): skill的名称

    返回:
        str: 下载URL
        None: 如果API调用失败
    """
    url = f"{API_BASE_URL}?skillIdentifier={skill_name}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            if data.get('code') == 200:
                return data.get('data', {}).get('downloadUrl')
            else:
                print(f"API返回错误码: {data.get('code')}", file=sys.stderr)
                print(f"错误信息: {data.get('message')}", file=sys.stderr)
                return None

    except urllib.error.URLError as e:
        print(f"获取下载链接失败: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"解析API响应失败: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"未预期的错误: {e}", file=sys.stderr)
        return None

def main():
    if len(sys.argv) != 2:
        print("用法: get_download_url.py <skill_name>", file=sys.stderr)
        sys.exit(1)

    skill_name = sys.argv[1]
    download_url = get_download_url(skill_name)

    if download_url is None:
        print(f"获取skill下载链接失败: {skill_name}", file=sys.stderr)
        sys.exit(1)

    print(download_url)

if __name__ == "__main__":
    main()
