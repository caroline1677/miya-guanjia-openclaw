#!/usr/bin/env python3
"""Generic AMap POI search for OpenClaw skills.

No mock fallback: failures are returned as structured JSON errors.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://restapi.amap.com/v3"
CATEGORY_TYPES = {
    "restaurant": "050000",
    "food": "050000",
    "hotel": "100000",
    "lodging": "100000",
    "scenic": "110000",
    "attraction": "110000",
    "park": "110000",
    "shopping": "060000",
    "mall": "060000",
    "cinema": "080000",
    "entertainment": "080000",
    "transport": "150000",
    "station": "150000",
    "life": "070000",
    "all": "",
}


def load_env():
    candidates = [
        Path.home() / ".openclaw" / ".env",
        Path("/root/.openclaw/.env"),
        Path("/home/ubuntu/.openclaw/.env"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def fail(message, **extra):
    payload = {"ok": False, "source": "amap", "error": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1


def request(path, params):
    key = os.environ.get("AMAP_KEY")
    if not key:
        raise RuntimeError("AMAP_KEY is not configured")
    params = {k: v for k, v in params.items() if v not in (None, "")}
    params["key"] = key
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-amap-poi/1.0"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") != "1":
        raise RuntimeError(data.get("info") or data.get("infocode") or "AMap API error")
    return data


def normalize_types(category, explicit_types):
    if explicit_types is not None:
        return explicit_types
    return CATEGORY_TYPES.get((category or "all").lower(), "")


def normalize_poi(poi):
    ext = poi.get("biz_ext") or {}
    photos = poi.get("photos") or []
    distance = poi.get("distance")
    try:
        if isinstance(distance, list):
            distance = None
        else:
            distance = int(distance) if distance not in (None, "") else None
    except (TypeError, ValueError):
        distance = None
    return {
        "id": poi.get("id"),
        "name": poi.get("name"),
        "address": poi.get("address"),
        "location": poi.get("location"),
        "type": poi.get("type"),
        "typecode": poi.get("typecode"),
        "cityname": poi.get("cityname"),
        "adname": poi.get("adname"),
        "tel": poi.get("tel"),
        "distance_m": distance,
        "rating": ext.get("rating") if isinstance(ext, dict) else None,
        "cost": ext.get("cost") if isinstance(ext, dict) else None,
        "open_time": ext.get("open_time") if isinstance(ext, dict) else None,
        "photos": [p.get("url") for p in photos if isinstance(p, dict) and p.get("url")][:3],
    }


def safe_count(raw_count, fallback):
    try:
        if isinstance(raw_count, list):
            return fallback
        return int(raw_count)
    except (TypeError, ValueError):
        return fallback


def make_payload(action, args, data, types):
    pois = [normalize_poi(p) for p in data.get("pois", [])]
    return {
        "ok": True,
        "source": "amap",
        "action": action,
        "query": {
            "keywords": args.keywords,
            "category": args.category,
            "types": types,
            "city": args.city,
            "citylimit": args.citylimit,
            "location": getattr(args, "location", None),
            "radius": getattr(args, "radius", None),
            "limit": args.limit,
        },
        "count": safe_count(data.get("count"), len(pois)),
        "pois": pois,
    }


def search_text(args):
    types = normalize_types(args.category, args.types)
    data = request("/place/text", {
        "keywords": args.keywords,
        "types": types,
        "city": args.city,
        "citylimit": "true" if args.citylimit else "false",
        "offset": args.limit,
        "page": args.page,
        "extensions": args.extensions,
        "output": "json",
    })
    return make_payload("search", args, data, types)


def search_around(args):
    types = normalize_types(args.category, args.types)
    if not args.location:
        raise RuntimeError("--location is required for around search")
    data = request("/place/around", {
        "keywords": args.keywords,
        "types": types,
        "location": args.location,
        "radius": args.radius,
        "city": args.city,
        "sortrule": args.sortrule,
        "offset": args.limit,
        "page": args.page,
        "extensions": args.extensions,
        "output": "json",
    })
    return make_payload("around", args, data, types)


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Generic AMap POI search")
    sub = parser.add_subparsers(dest="action", required=True)

    def add_common(p):
        p.add_argument("--keywords", required=True, help="Search keyword, e.g. hotel/seafood/Shenzhen North Station")
        p.add_argument("--category", default="all", help="restaurant/hotel/scenic/shopping/cinema/transport/life/all")
        p.add_argument("--types", default=None, help="AMap type code override, e.g. 050000")
        p.add_argument("--city", default="深圳")
        p.add_argument("--limit", type=int, default=10)
        p.add_argument("--page", type=int, default=1)
        p.add_argument("--extensions", choices=["base", "all"], default="all")
        p.add_argument("--citylimit", action=argparse.BooleanOptionalAction, default=True)

    p_search = sub.add_parser("search")
    add_common(p_search)

    p_resolve = sub.add_parser("resolve")
    add_common(p_resolve)
    p_resolve.set_defaults(limit=5, extensions="base")

    p_around = sub.add_parser("around")
    add_common(p_around)
    p_around.add_argument("--location", required=True, help="lng,lat")
    p_around.add_argument("--radius", type=int, default=5000)
    p_around.add_argument("--sortrule", choices=["distance", "weight"], default="distance")

    args = parser.parse_args()
    try:
        if args.action in ("search", "resolve"):
            payload = search_text(args)
            payload["action"] = args.action
            if args.action == "resolve":
                payload["poi"] = payload["pois"][0] if payload["pois"] else None
        elif args.action == "around":
            payload = search_around(args)
        else:
            return fail(f"unsupported action: {args.action}")
    except Exception as exc:
        return fail(str(exc), action=args.action, query=vars(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
