#!/usr/bin/env python3
import json
import math
import sys


MODE_COLORS = {
    "walking": "#2EAD4A",
    "walk": "#2EAD4A",
    "transit": "#2F6FED",
    "subway": "#2F6FED",
    "bus": "#2F6FED",
    "taxi": "#F59E0B",
    "driving": "#EF4444",
    "car": "#EF4444",
    "unknown": "#6B7280"
}


def parse_location(value):
    lng, lat = value.split(",")
    return float(lng), float(lat)


def project(points, width=900, height=560, padding=70):
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]

    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)

    if max_lng == min_lng:
        max_lng += 0.001
    if max_lat == min_lat:
        max_lat += 0.001

    def convert(location):
        lng, lat = location
        x = padding + (lng - min_lng) / (max_lng - min_lng) * (width - padding * 2)
        y = height - padding - (lat - min_lat) / (max_lat - min_lat) * (height - padding * 2)
        return round(x, 2), round(y, 2)

    return convert


def escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    payload = json.load(sys.stdin)
    width = int(payload.get("width", 900))
    height = int(payload.get("height", 560))

    route_points = []

    for point in payload.get("points", []):
        route_points.append(parse_location(point["location"]))

    for segment in payload.get("segments", []):
        for item in segment.get("polyline", []):
            route_points.append(parse_location(item))

    if not route_points:
        raise RuntimeError("No coordinates found")

    convert = project(route_points, width, height)

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    svg.append('<rect width="100%" height="100%" fill="#F8FAFC"/>')
    svg.append(f'<text x="32" y="42" font-size="24" font-family="Arial, sans-serif" font-weight="700" fill="#111827">{escape(payload.get("title", "路线图"))}</text>')

    for segment in payload.get("segments", []):
        polyline = segment.get("polyline")
        if not polyline:
            from_point = next((p for p in payload["points"] if p["name"] == segment.get("from")), None)
            to_point = next((p for p in payload["points"] if p["name"] == segment.get("to")), None)
            if from_point and to_point:
                polyline = [from_point["location"], to_point["location"]]
            else:
                continue

        coords = [convert(parse_location(item)) for item in polyline]
        path = " ".join([f"{x},{y}" for x, y in coords])
        mode = segment.get("mode", "unknown")
        color = MODE_COLORS.get(mode, MODE_COLORS["unknown"])

        svg.append(
            f'<polyline points="{path}" fill="none" stroke="{color}" '
            f'stroke-width="5" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>'
        )

        mid = coords[len(coords) // 2]
        label = f'{segment.get("duration_min", "?")}min / {segment.get("distance_km", "?")}km'
        svg.append(f'<text x="{mid[0] + 8}" y="{mid[1] - 8}" font-size="13" font-family="Arial" fill="#374151">{escape(label)}</text>')

    for point in payload.get("points", []):
        x, y = convert(parse_location(point["location"]))
        idx = point.get("id", "")
        name = point.get("name", "")

        svg.append(f'<circle cx="{x}" cy="{y}" r="15" fill="#111827"/>')
        svg.append(f'<text x="{x}" y="{y + 5}" text-anchor="middle" font-size="13" font-family="Arial" font-weight="700" fill="#FFFFFF">{escape(idx)}</text>')
        svg.append(f'<text x="{x + 20}" y="{y + 5}" font-size="14" font-family="Arial" fill="#111827">{escape(name)}</text>')

    legend_y = height - 30
    legend = [
        ("步行", "#2EAD4A"),
        ("公交/地铁", "#2F6FED"),
        ("打车", "#F59E0B"),
        ("开车", "#EF4444")
    ]

    x = 32
    for label, color in legend:
        svg.append(f'<line x1="{x}" y1="{legend_y}" x2="{x + 28}" y2="{legend_y}" stroke="{color}" stroke-width="5" stroke-linecap="round"/>')
        svg.append(f'<text x="{x + 36}" y="{legend_y + 5}" font-size="13" font-family="Arial" fill="#374151">{label}</text>')
        x += 120

    svg.append('</svg>')

    output_path = payload.get("output", "route.svg")
    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(svg))

    print(json.dumps({
        "status": "success",
        "output": output_path,
        "embed_markdown": f"![路线图]({output_path})",
        "note": "该 SVG 可直接嵌入 Markdown；如缺少真实 polyline，则为路线示意图。"
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()