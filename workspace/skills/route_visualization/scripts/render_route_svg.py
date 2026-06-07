#!/usr/bin/env python3
"""读取 route_plan.json，生成 route.svg。纯 Python 字符串生成 SVG，不依赖 cairosvg/PIL/浏览器。"""

import json
import math
import os
import sys

# 交通方式 → 颜色
MODE_COLORS = {
    "walking": "#4CAF50",    # 绿色
    "transit": "#2196F3",    # 蓝色
    "taxi":   "#FF9800",    # 橙色
    "driving": "#F44336",   # 红色
    "unknown":  "#9E9E9E",  # 灰色
}

# 交通方式 → 虚线样式（步行用虚线）
MODE_DASH = {
    "walking": "8,4",
    "transit": "none",
    "taxi":   "none",
    "driving": "none",
    "unknown":  "4,4",
}


def parse_lnglat(loc):
    """'114.0,22.5' → (lng, lat)"""
    parts = loc.split(",")
    return float(parts[0]), float(parts[1])


def collect_all_coords(route_plan):
    """从 route_plan 收集所有坐标，用于计算 viewBox"""
    coords = []
    for seg in route_plan.get("segments", []):
        for p in seg.get("polyline", []):
            coords.append(parse_lnglat(p))
    for pt in route_plan.get("points", []):
        loc = pt.get("location", "")
        if loc:
            coords.append(parse_lnglat(loc))
    return coords


def compute_viewbox(coords, padding_pct=0.12):
    """计算 SVG viewBox，留边距"""
    if not coords:
        return 0, 0, 1000, 1000
    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)

    # 处理单点情况
    if min_lng == max_lng:
        min_lng -= 0.01
        max_lng += 0.01
    if min_lat == max_lat:
        min_lat -= 0.01
        max_lat += 0.01

    pad_x = (max_lng - min_lng) * padding_pct
    pad_y = (max_lat - min_lat) * padding_pct

    x = min_lng - pad_x
    y = max_lat + pad_y  # SVG y 轴向下，纬度上 = y 小
    w = (max_lng - min_lng) + 2 * pad_x
    h = (max_lat - min_lat) + 2 * pad_y

    return x, y, w, h


def project(lng, lat, vbx, vby, vbw, vbh, svg_w, svg_h):
    """经纬度 → SVG 坐标"""
    sx = (lng - vbx) / vbw * svg_w
    sy = (vby - lat) / vbh * svg_h  # y 轴翻转
    return sx, sy


def build_svg(route_plan, output_path="route.svg"):
    """生成 SVG 文件"""
    coords = collect_all_coords(route_plan)
    vbx, vby, vbw, vbh = compute_viewbox(coords)

    SVG_W = 900
    SVG_H = 600

    points = route_plan.get("points", [])
    segments = route_plan.get("segments", [])
    title = route_plan.get("title", "路线规划")

    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'viewBox="0 0 {SVG_W} {SVG_H}" '
                 f'width="{SVG_W}" height="{SVG_H}" '
                 f'style="background:#f8f9fa;font-family:DejaVu Sans,sans-serif;">')

    # 标题
    lines.append(f'  <text x="{SVG_W//2}" y="30" text-anchor="middle" '
                 f'font-size="18" font-weight="bold" fill="#333">{title}</text>')

    # ── 绘制路线段 ──
    legend_items = []
    for seg in segments:
        mode = seg.get("mode", "unknown")
        color = MODE_COLORS.get(mode, MODE_COLORS["unknown"])
        dash = MODE_DASH.get(mode, "none")
        polyline = seg.get("polyline", [])

        if len(polyline) < 2:
            continue

        # 构建 path d
        pts = [parse_lnglat(p) for p in polyline]
        svg_pts = [project(lng, lat, vbx, vby, vbw, vbh, SVG_W, SVG_H) for lng, lat in pts]
        d_parts = []
        for i, (sx, sy) in enumerate(svg_pts):
            cmd = "M" if i == 0 else "L"
            d_parts.append(f"{cmd}{sx:.1f},{sy:.1f}")
        d = " ".join(d_parts)

        dash_attr = f'stroke-dasharray="{dash}"' if dash != "none" else ""
        lines.append(f'  <path d="{d}" fill="none" stroke="{color}" '
                     f'stroke-width="4" stroke-linecap="round" stroke-linejoin="round" '
                     f'{dash_attr}/>')

        # 记录图例
        label = seg.get("mode_label", mode)
        legend_items.append((label, color, dash))

    # ── 绘制地点标记 ──
    for pt in points:
        loc = pt.get("location", "")
        if not loc:
            continue
        lng, lat = parse_lnglat(loc)
        sx, sy = project(lng, lat, vbx, vby, vbw, vbh, SVG_W, SVG_H)
        pt_type = pt.get("type", "stop")
        pt_id = pt.get("id", "?")
        pt_name = pt.get("name", "")

        # 外圈
        fill = "#F44336" if pt_type in ("origin", "destination") else "#FFFFFF"
        stroke = "#333"
        r = 10 if pt_type in ("origin", "destination") else 8

        lines.append(f'  <circle cx="{sx:.1f}" cy="{sy:.1f}" r="{r}" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        lines.append(f'  <text x="{sx:.1f}" y="{sy + 4:.1f}" text-anchor="middle" '
                     f'font-size="10" font-weight="bold" '
                     f'fill="{"#FFF" if fill == "#F44336" else "#333"}">{pt_id}</text>')

        # 名称标签（在节点上方）
        max_label_len = 12
        display_name = pt_name[:max_label_len] + ("…" if len(pt_name) > max_label_len else "")
        lines.append(f'  <text x="{sx:.1f}" y="{sy - 16:.1f}" text-anchor="middle" '
                     f'font-size="11" fill="#333" font-weight="500">{display_name}</text>')

    # ── 图例 ──
    # 去重
    seen = set()
    unique_legend = []
    for label, color, dash in legend_items:
        if label not in seen:
            seen.add(label)
            unique_legend.append((label, color, dash))

    legend_x = SVG_W - 170
    legend_y = 60
    lines.append(f'  <rect x="{legend_x - 10}" y="{legend_y - 15}" '
                 f'width="165" height="{len(unique_legend) * 25 + 20}" '
                 f'rx="6" fill="white" stroke="#ddd" stroke-width="1" opacity="0.9"/>')
    lines.append(f'  <text x="{legend_x}" y="{legend_y}" font-size="12" '
                 f'font-weight="bold" fill="#555">交通方式</text>')

    for i, (label, color, dash) in enumerate(unique_legend):
        ly = legend_y + 20 + i * 25
        dash_attr = f'stroke-dasharray="{dash}"' if dash != "none" else ""
        lines.append(f'  <line x1="{legend_x}" y1="{ly - 4}" '
                     f'x2="{legend_x + 25}" y2="{ly - 4}" '
                     f'stroke="{color}" stroke-width="3" {dash_attr}/>')
        lines.append(f'  <text x="{legend_x + 32}" y="{ly}" font-size="12" '
                     f'fill="#555" dominant-baseline="middle">{label}</text>')

    # ── 摘要信息 ──
    summary = route_plan.get("summary", {})
    total_time = summary.get("total_transit_time_min", "?")
    total_dist = summary.get("total_distance_km", "?")
    info_y = SVG_H - 30
    lines.append(f'  <text x="{SVG_W//2}" y="{info_y}" text-anchor="middle" '
                 f'font-size="13" fill="#666">'
                 f'全程约 {total_time} 分钟 · {total_dist} 公里</text>')

    lines.append('</svg>')

    svg_content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    return output_path


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else "route_plan.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "route.svg"

    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        route_plan = json.load(f)

    result = build_svg(route_plan, output_path)
    print(json.dumps({"ok": True, "output": result}))


if __name__ == "__main__":
    main()
