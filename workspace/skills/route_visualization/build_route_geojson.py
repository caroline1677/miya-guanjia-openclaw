#!/usr/bin/env python3
import json
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
    return [float(lng), float(lat)]


def main():
    payload = json.load(sys.stdin)
    features = []

    for point in payload.get("points", []):
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": parse_location(point["location"])
            },
            "properties": {
                "id": point.get("id"),
                "name": point.get("name"),
                "type": point.get("type", "stop")
            }
        })

    for segment in payload.get("segments", []):
        mode = segment.get("mode", "unknown")
        polyline = segment.get("polyline") or []

        if len(polyline) < 2:
            continue

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [parse_location(item) for item in polyline]
            },
            "properties": {
                "from": segment.get("from"),
                "to": segment.get("to"),
                "mode": mode,
                "color": MODE_COLORS.get(mode, MODE_COLORS["unknown"]),
                "duration_min": segment.get("duration_min"),
                "distance_km": segment.get("distance_km")
            }
        })

    print(json.dumps({
        "type": "FeatureCollection",
        "name": payload.get("title", "route"),
        "features": features
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()