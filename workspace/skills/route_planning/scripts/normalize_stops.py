#!/usr/bin/env python3
import json
import sys


def normalize_stop(item):
    if isinstance(item, str):
        return {"name": item}
    return item


def main():
    payload = json.load(sys.stdin)
    preferences = payload.get("preferences", {})

    result = {
        "title": payload.get("title", "多目的地路线规划"),
        "city": payload.get("city"),
        "origin": payload.get("origin"),
        "destination": payload.get("destination"),
        "stops": [normalize_stop(item) for item in payload.get("stops", [])],
        "departure_time": payload.get("departure_time"),
        "allow_reorder": bool(payload.get("allow_reorder", False)),
        "return_to_origin": bool(payload.get("return_to_origin", False)),
        "preferences": {
            "fastest": preferences.get("fastest", False),
            "cheapest": preferences.get("cheapest", False),
            "less_walking": preferences.get("less_walking", True),
            "pet_friendly": preferences.get("pet_friendly", False),
            "self_driving": preferences.get("self_driving", False),
            "rain_sensitive": preferences.get("rain_sensitive", True)
        },
        "visualization": {
            "enabled": payload.get("visualization", {}).get("enabled", True),
            "outputs": payload.get("visualization", {}).get("outputs", ["svg", "html"])
        }
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()