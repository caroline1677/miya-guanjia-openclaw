#!/usr/bin/env python3
import json
import re
import sys


def normalize_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[#【】\[\]（）()]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -:：,，。")


def extract_candidates(payload):
    raw_items = payload.get("items") or payload.get("posts") or payload.get("candidates") or []
    candidates = []

    for item in raw_items:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("poi") or item.get("name") or item.get("title") or item.get("content") or ""
        else:
            continue

        name = normalize_name(text)
        if name and name not in candidates:
            candidates.append(name)

    limit = int(payload.get("limit", 5))
    return candidates[:limit]


def main():
    payload = json.load(sys.stdin)
    result = {
        "candidates": extract_candidates(payload)
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()