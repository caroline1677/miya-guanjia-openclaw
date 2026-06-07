#!/usr/bin/env python3
"""把 SVG 转成 PNG。优先使用 sharp（Node.js），降级到 ImageMagick convert。"""

import json
import os
import subprocess
import sys


def convert_with_sharp(svg_path, png_path, width=1800, height=1200):
    """用 sharp (Node.js) 转换 SVG → PNG"""
    script = (
        "const sharp = require('sharp');\n"
        "const fs = require('fs');\n"
        f"const svgBuffer = fs.readFileSync('{svg_path}');\n"
        f"sharp(svgBuffer)\n"
        f"  .resize({width}, {height}, {{ fit: 'contain', background: {{ r: 255, g: 255, b: 255, alpha: 1 }} }})\n"
        "  .png()\n"
        f"  .toFile('{png_path}')\n"
        "  .then(() => console.log('OK'))\n"
        "  .catch(err => { console.error('ERROR:', err.message); process.exit(1); });\n"
    )
    tmp_js = "/tmp/_svg2png.js"
    with open(tmp_js, "w") as f:
        f.write(script)
    env = os.environ.copy()
    env["NODE_PATH"] = "/usr/local/lib/node_modules"
    try:
        r = subprocess.run(["node", tmp_js], capture_output=True, text=True, timeout=60, env=env)
        if r.returncode == 0 and os.path.exists(png_path):
            return True, None
        return False, r.stderr.strip() or r.stdout.strip()
    finally:
        if os.path.exists(tmp_js):
            os.remove(tmp_js)


def convert_with_imagemagick(svg_path, png_path, width=1800, height=1200):
    """用 ImageMagick convert 转换"""
    for cmd_name in ["magick", "convert"]:
        try:
            subprocess.run([cmd_name, "--version"], capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

        if cmd_name == "convert":
            cmd = ["convert", svg_path, "-resize", f"{width}x{height}",
                   "-background", "white", png_path]
        else:
            cmd = ["magick", svg_path, "-resize", f"{width}x{height}",
                   "-background", "white", png_path]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and os.path.exists(png_path):
                return True, None
            return False, r.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "timeout"
    return False, "ImageMagick not found"


def convert_svg_to_png(svg_path="route.svg", png_path="route.png", width=1800, height=1200):
    if not os.path.exists(svg_path):
        return {"ok": False, "error": f"{svg_path} not found"}

    # 优先 sharp
    ok, err = convert_with_sharp(svg_path, png_path, width, height)
    if ok:
        return {"ok": True, "output": png_path, "engine": "sharp",
                "width": width, "height": height}

    # 降级 ImageMagick
    ok, err = convert_with_imagemagick(svg_path, png_path, width, height)
    if ok:
        return {"ok": True, "output": png_path, "engine": "imagemagick",
                "width": width, "height": height}

    return {"ok": False, "error": f"sharp: {err}; ImageMagick also failed"}


def main():
    svg_path = sys.argv[1] if len(sys.argv) > 1 else "route.svg"
    png_path = sys.argv[2] if len(sys.argv) > 2 else "route.png"

    result = convert_svg_to_png(svg_path, png_path)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
