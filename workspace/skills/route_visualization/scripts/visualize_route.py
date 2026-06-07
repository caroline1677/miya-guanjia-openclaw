#!/usr/bin/env python3
"""一键生成路线图并上传飞书。

用法:
  python3 visualize_route.py route_plan.json

流程:
  1. render_route_svg.py → route.svg
  2. convert_svg_to_png.py → route.png
  3. upload_feishu_image.py → image_key

输出 JSON:
  {"ok": true, "image_key": "xxx", "png_path": "route.png"}
  {"ok": false, "error": "...", "fallback": "文字路线可用"}
"""

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_step(cmd, label):
    """运行子进程，返回 (ok, stdout_str, stderr_str)"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return False, r.stdout, r.stderr
        return True, r.stdout, ""
    except subprocess.TimeoutExpired:
        return False, "", f"{label} timed out"
    except Exception as e:
        return False, "", str(e)


def main():
    plan_path = sys.argv[1] if len(sys.argv) > 1 else "route_plan.json"
    work_dir = os.path.dirname(plan_path) or "."
    plan_path = os.path.abspath(plan_path)

    result = {"ok": False, "steps": {}}

    # Step 1: SVG
    svg_path = os.path.join(work_dir, "route.svg")
    ok, out, err = run_step(
        ["python3", os.path.join(SCRIPT_DIR, "render_route_svg.py"), plan_path, svg_path],
        "render_svg",
    )
    result["steps"]["svg"] = {"ok": ok, "output": svg_path if ok else err.strip()}
    if not ok:
        result["error"] = "SVG 生成失败"
        result["fallback"] = "文字路线可用"
        print(json.dumps(result, ensure_ascii=False))
        return

    # Step 2: PNG
    png_path = os.path.join(work_dir, "route.png")
    ok, out, err = run_step(
        ["python3", os.path.join(SCRIPT_DIR, "convert_svg_to_png.py"), svg_path, png_path],
        "convert_png",
    )
    result["steps"]["png"] = {"ok": ok, "output": png_path if ok else err.strip()}
    if not ok:
        result["error"] = "PNG 转换失败"
        result["fallback"] = "文字路线可用"
        print(json.dumps(result, ensure_ascii=False))
        return

    # Step 3: 上传飞书
    has_token = bool(os.environ.get("FEISHU_APP_ID") and os.environ.get("FEISHU_APP_SECRET"))
    if not has_token:
        result["steps"]["upload"] = {"ok": False, "skipped": True, "reason": "FEISHU_APP_ID/APP_SECRET 未配置"}
        result["ok"] = True
        result["png_path"] = png_path
        result["image_key"] = None
        result["note"] = "图片已生成但未上传（缺少飞书凭证），可手动发送 PNG"
        print(json.dumps(result, ensure_ascii=False))
        return

    ok, out, err = run_step(
        ["python3", os.path.join(SCRIPT_DIR, "upload_feishu_image.py"), png_path],
        "upload",
    )
    result["steps"]["upload"] = {"ok": ok, "output": out.strip()}

    if ok:
        try:
            upload_result = json.loads(out.strip())
            result["image_key"] = upload_result.get("image_key")
        except json.JSONDecodeError:
            result["image_key"] = None

    result["ok"] = True
    result["png_path"] = png_path
    if not result.get("image_key"):
        result["note"] = "上传可能未成功，请检查日志"

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
