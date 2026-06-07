#!/usr/bin/env python3
"""通过飞书图片上传 API 上传 PNG，获得 image_key。

用法:
  python3 upload_feishu_image.py <png_path>

需要环境变量:
  FEISHU_APP_ID
  FEISHU_APP_SECRET

流程:
  1. 获取 tenant_access_token
  2. 上传图片获取 image_key
"""

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request


def get_env(key):
    val = os.environ.get(key)
    if not val:
        print(json.dumps({"ok": False, "error": f"Missing env: {key}"}), file=sys.stderr)
        sys.exit(1)
    return val


def curl_post(url, data=None, headers=None, timeout=30):
    """简单的 POST 请求封装"""
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def curl_upload(url, file_path, headers=None, timeout=60):
    """multipart/form-data 文件上传"""
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    file_name = os.path.basename(file_path)

    with open(file_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{file_name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    headers = headers or {}
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    headers["Content-Length"] = str(len(body))

    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_tenant_token(app_id, app_secret):
    """获取 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    result = curl_post(url, data=data, headers={"Content-Type": "application/json"})
    if result.get("code") != 0:
        return None, result.get("msg", "unknown error")
    return result.get("tenant_access_token"), None


def upload_image(token, png_path):
    """上传图片到飞书，返回 image_key"""
    url = "https://open.feishu.cn/open-apis/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    result = curl_upload(url, png_path, headers=headers)
    if result.get("code") != 0:
        return None, result.get("msg", "upload failed")
    image_key = result.get("data", {}).get("image_key")
    return image_key, None


def main():
    png_path = sys.argv[1] if len(sys.argv) > 1 else "route.png"

    if not os.path.exists(png_path):
        print(json.dumps({"ok": False, "error": f"{png_path} not found"}))
        return

    app_id = get_env("FEISHU_APP_ID")
    app_secret = get_env("FEISHU_APP_SECRET")

    # 获取 token
    token, err = get_tenant_token(app_id, app_secret)
    if err:
        print(json.dumps({"ok": False, "error": f"get_token failed: {err}"}))
        return

    # 上传图片
    image_key, err = upload_image(token, png_path)
    if err:
        print(json.dumps({"ok": False, "error": f"upload failed: {err}"}))
        return

    print(json.dumps({"ok": True, "image_key": image_key}))


if __name__ == "__main__":
    main()
