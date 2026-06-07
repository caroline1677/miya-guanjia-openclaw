#!/usr/bin/env python3
import json
import sys


MODE_LABELS = {
    "walking": "步行",
    "walk": "步行",
    "transit": "公交/地铁",
    "subway": "地铁",
    "bus": "公交",
    "taxi": "打车",
    "driving": "开车",
    "car": "开车",
    "unknown": "待确认"
}


def escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    payload = json.load(sys.stdin)
    title = payload.get("title", "路线规划")
    svg_path = payload.get("svg_path", "route.svg")
    output_path = payload.get("output", "route.html")

    points_html = []
    for point in payload.get("points", []):
        points_html.append(f"""
        <div class="point">
          <div class="badge">{escape(point.get("id", ""))}</div>
          <div>
            <div class="point-name">{escape(point.get("name", ""))}</div>
            <div class="point-location">{escape(point.get("location", ""))}</div>
          </div>
        </div>
        """)

    segments_html = []
    for segment in payload.get("segments", []):
        mode = MODE_LABELS.get(segment.get("mode", "unknown"), "待确认")
        segments_html.append(f"""
        <div class="segment">
          <div class="segment-main">
            <strong>{escape(segment.get("from", ""))}</strong>
            <span>→</span>
            <strong>{escape(segment.get("to", ""))}</strong>
          </div>
          <div class="segment-meta">
            <span>{escape(mode)}</span>
            <span>{escape(segment.get("duration_min", "?"))} 分钟</span>
            <span>{escape(segment.get("distance_km", "?"))} km</span>
          </div>
        </div>
        """)

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f8fafc;
      color: #111827;
    }}
    .container {{
      max-width: 960px;
      margin: 32px auto;
      padding: 0 20px;
    }}
    .card {{
      background: white;
      border-radius: 20px;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
      overflow: hidden;
      border: 1px solid #e5e7eb;
    }}
    .header {{
      padding: 24px 28px;
      border-bottom: 1px solid #e5e7eb;
    }}
    h1 {{
      margin: 0;
      font-size: 26px;
    }}
    .map {{
      padding: 20px;
      background: #f9fafb;
    }}
    .map img {{
      width: 100%;
      border-radius: 14px;
      border: 1px solid #e5e7eb;
      background: white;
    }}
    .content {{
      display: grid;
      grid-template-columns: 1fr 1.2fr;
      gap: 24px;
      padding: 24px;
    }}
    .point, .segment {{
      padding: 14px;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      margin-bottom: 12px;
      background: #ffffff;
    }}
    .point {{
      display: flex;
      gap: 12px;
      align-items: center;
    }}
    .badge {{
      width: 30px;
      height: 30px;
      border-radius: 999px;
      background: #111827;
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
    }}
    .point-name {{
      font-weight: 700;
    }}
    .point-location, .segment-meta {{
      color: #6b7280;
      font-size: 13px;
      margin-top: 4px;
    }}
    .segment-main {{
      display: flex;
      gap: 8px;
      align-items: center;
      font-size: 15px;
    }}
    .segment-meta {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    @media (max-width: 760px) {{
      .content {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="header">
        <h1>{escape(title)}</h1>
      </div>
      <div class="map">
        <img src="{escape(svg_path)}" alt="路线图" />
      </div>
      <div class="content">
        <section>
          <h2>地点顺序</h2>
          {''.join(points_html)}
        </section>
        <section>
          <h2>交通分段</h2>
          {''.join(segments_html)}
        </section>
      </div>
    </div>
  </div>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(html)

    print(json.dumps({
        "status": "success",
        "output": output_path,
        "embed_html": f'<iframe src="{output_path}" width="100%" height="720"></iframe>'
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()