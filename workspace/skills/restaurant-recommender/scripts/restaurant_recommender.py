#!/usr/bin/env python3
"""
餐厅推荐脚本 — 综合小红书笔记搜索 + 高德地图 POI 数据，为用户生成餐厅推荐。

依赖：
  - xhs CLI (xiaohongshu-cli) 已安装且已认证
  - AMAP_KEY 环境变量（高德地图 Web API Key）
  - Python 3.10+

用法：
  python3 restaurant_recommender.py --user-id <userId> --location <位置> [--area <区域>] [--keywords <关键词>] [--top-n 8] [--budget-max 200]

示例：
  python3 restaurant_recommender.py --user-id u001 --location "后海地铁站" --area "南山区" --keywords "美食 探店" --top-n 8
  python3 restaurant_recommender.py --user-id u001 --location "深圳湾万象城" --top-n 5 --budget-max 150

输出：JSON，包含推荐餐厅列表（融合小红书 + 高德数据）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

# ─── 配置 ───────────────────────────────────────────────────────────────

AMAP_KEY = os.environ.get("AMAP_KEY", "")
if not AMAP_KEY:
    # 尝试从 .env 文件读取
    env_path = os.path.expanduser("~/.openclaw/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("AMAP_KEY="):
                    AMAP_KEY = line.split("=", 1)[1]
                    break

if not AMAP_KEY:
    print("ERROR: AMAP_KEY not found. Set it in ~/.openclaw/.env", file=sys.stderr)
    sys.exit(1)

EDITH_HOST = "https://edith.xiaohongshu.com"
AMAP_TEXT_API = "https://restapi.amap.com/v3/place/text"
AMAP_AROUND_API = "https://restapi.amap.com/v3/place/around"

# ─── 小红书模块 ──────────────────────────────────────────────────────────

def xhs_search(query: str, sort: str = "popular", limit: int = 20) -> list:
    """通过 xhs Python 库搜索笔记，返回笔记列表"""
    try:
        sys.path.insert(0, os.path.expanduser("~/.openclaw/skills/jackwener-xiaohongshu-cli"))
        from xhs_cli.client import XhsClient

        cookies_path = os.path.expanduser("~/.xiaohongshu-cli/cookies.json")
        if not os.path.exists(cookies_path):
            print("[WARN] xhs cookies not found, run: xhs login", file=sys.stderr)
            return []
        with open(cookies_path) as f:
            cookies = json.load(f)

        client = XhsClient(cookies=cookies)
        result = client.search_notes(query, page=1, sort=sort)
        if result and isinstance(result, dict):
            return result.get("items", [])
        return []
    except Exception as e:
        err_msg = str(e)
        if "Captcha" in err_msg or "verification" in err_msg.lower():
            print("[WARN] xhs captcha triggered — ask user to verify in browser, then retry", file=sys.stderr)
        else:
            print(f"[WARN] xhs search failed: {e}", file=sys.stderr)
        return []


def xhs_read_note(note_id: str, xsec_token: str) -> str:
    """通过 xhs CLI 读取笔记正文，返回 desc 文本"""
    try:
        result = subprocess.run(
            ["xhs", "read", note_id, "--json"],
            capture_output=True, text=True, timeout=25
        )
        if result.returncode != 0:
            return ""
        data = json.loads(result.stdout)
        if not data.get("ok"):
            return ""
        note_card = data.get("data", {}).get("note_card", {})
        return note_card.get("desc", "") or ""
    except Exception as e:
        print(f"[WARN] xhs read failed for {note_id}: {e}", file=sys.stderr)
        return ""


def xhs_read_note_python(note_id: str, xsec_token: str) -> str:
    """通过 xhs Python 库读取笔记正文（绕过 CLI 超时问题）"""
    try:
        sys.path.insert(0, os.path.expanduser("~/.openclaw/skills/jackwener-xiaohongshu-cli"))
        from xhs_cli.client import XhsClient

        cookies_path = os.path.expanduser("~/.xiaohongshu-cli/cookies.json")
        if not os.path.exists(cookies_path):
            return ""
        with open(cookies_path) as f:
            cookies = json.load(f)

        client = XhsClient(cookies=cookies)
        result = client.get_note_by_id(note_id, xsec_token=xsec_token)
        if result and isinstance(result, dict):
            items = result.get("items", [])
            if items:
                note_card = items[0].get("note_card", {})
                return note_card.get("desc", "") or ""
        return ""
    except Exception as e:
        err_msg = str(e)
        if "Captcha" in err_msg or "verification" in err_msg.lower():
            print(f"[WARN] xhs captcha for {note_id} — cooling down", file=sys.stderr)
            time.sleep(5)
        else:
            print(f"[WARN] xhs read (python) failed for {note_id}: {e}", file=sys.stderr)
        return ""


def extract_restaurants_from_text(text: str) -> list:
    """从笔记正文中提取餐厅名（过滤非店名文本）"""
    restaurants = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        # 过滤空行和标签行
        if not line or line.startswith("#") or len(line) < 4:
            continue
        # 去掉 emoji 和特殊符号
        clean = re.sub(r'[^\w\s\u4e00-\u9fff\-·]', '', line).strip()
        # 过滤太短或太长的（>20字符的描述性句子大概率不是店名）
        if not (4 <= len(clean) <= 20):
            continue
        # 必须含中文
        if not re.search(r'[\u4e00-\u9fff]', clean):
            continue
        # 过滤明显是描述/句子而非店名的
        # 包含以下关键词的通常是描述性文本，跳过
        skip_markers = ["深圳", "地点", "话题", "人均", "推荐", "地址", "营业",
                        "地铁", "步行", "分钟", "好吃", "踩雷", "收藏",
                        "分享", "以上", "感谢", "图", "地址", "打卡"]
        if any(m in clean for m in skip_markers):
            continue
        # 过滤纯数字+中文混合（如"10000384537"）
        if re.match(r'^[\d\u4e00-\u9fff]+$', clean) and len(clean) > 10:
            continue
        restaurants.append(clean)
    return restaurants


def filter_nanshan_notes(notes: list, area: str = "南山") -> list:
    """过滤出包含南山区关键词的笔记"""
    filtered = []
    area_keywords = ["南山", "蛇口", "后海", "海岸城", "深圳湾", "南头", "西丽", "华侨城", "科技园"]
    for note in notes:
        nc = note.get("note_card", {})
        title = nc.get("display_title", "")
        if any(kw in title for kw in area_keywords):
            filtered.append(note)
    return filtered

# ─── 高德模块 ────────────────────────────────────────────────────────────

def amap_text_search(keyword: str, city: str = "深圳", limit: int = 5) -> list:
    """高德文本搜索 POI"""
    params = urllib.parse.urlencode({
        "key": AMAP_KEY,
        "keywords": keyword,
        "city": city,
        "limit": limit,
        "output": "json",
    })
    url = f"{AMAP_TEXT_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "restaurant-recommender/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "1":
                return data.get("pois", [])
    except Exception as e:
        print(f"[WARN] amap text search failed for '{keyword}': {e}", file=sys.stderr)
    time.sleep(1.5)  # 高德 QPS 限制
    return []


def amap_around_search(location: str, radius: int = 2000, limit: int = 20) -> list:
    """高德周边搜索"""
    params = urllib.parse.urlencode({
        "key": AMAP_KEY,
        "location": location,
        "radius": radius,
        "types": "050000",  # 餐饮服务
        "limit": limit,
        "output": "json",
    })
    url = f"{AMAP_AROUND_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "restaurant-recommender/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "1":
                return data.get("pois", [])
    except Exception as e:
        print(f"[WARN] amap around search failed: {e}", file=sys.stderr)
    time.sleep(1.5)
    return []


def enrich_restaurant(name: str, city: str = "深圳南山") -> dict:
    """用高德数据丰富餐厅信息"""
    results = amap_text_search(name, city=city, limit=3)
    if not results:
        return {}

    # 找最匹配的
    best = None
    for r in results:
        if name in r.get("name", "") or r.get("name", "") in name:
            best = r
            break
    if not best and results:
        best = results[0]

    if not best:
        return {}

    ext = best.get("biz_ext", {})
    return {
        "name": best.get("name", name),
        "address": best.get("address", ""),
        "type": best.get("type", ""),
        "per_capita": ext.get("cost", ""),
        "rating": ext.get("rating", ""),
        "open_time": ext.get("open_time", ""),
        "tel": best.get("tel", ""),
        "location": best.get("location", ""),
        "distance_text": best.get("distance", ""),
    }

# ─── 推荐引擎 ────────────────────────────────────────────────────────────

def score_restaurant(restaurant: dict, user_prefs: dict) -> int:
    """根据用户偏好给餐厅打分"""
    score = 0
    name = restaurant.get("name", "")
    address = restaurant.get("address", "")
    per_capita = float(restaurant.get("per_capita", 0) or 0)

    # 价格匹配
    budget_max = user_prefs.get("budget_max", 200)
    if per_capita and per_capita <= budget_max:
        score += 10
    elif per_capita and per_capita <= budget_max * 1.5:
        score += 5

    # 评分加成
    rating = float(restaurant.get("rating", 0) or 0)
    score += int(rating * 2)

    # 辣味偏好
    if user_prefs.get("spicy", False):
        spicy_keywords = ["火锅", "川菜", "湘菜", "重庆", "麻辣", "辣", "鱼蛙", "酸汤", "贵州"]
        if any(kw in name for kw in spicy_keywords):
            score += 15

    # 海鲜偏好
    if user_prefs.get("seafood", False):
        seafood_keywords = ["海鲜", "鱼", "虾", "蟹", "蛙", "火锅"]
        if any(kw in name for kw in seafood_keywords):
            score += 10

    # 小红书出现次数加成
    mention_count = restaurant.get("mention_count", 1)
    score += min(mention_count * 3, 15)

    return score


def generate_recommendations(
    user_id: str,
    location: str,
    area: str = "南山区",
    keywords: str = "美食 探店",
    top_n: int = 8,
    budget_max: int = 200,
) -> dict:
    """主流程：搜索小红书 → 提取餐厅 → 高德丰富 → 推荐排序"""

    # Step 1: 搜索小红书笔记
    print(f"[1/4] 搜索小红书: {area} {keywords}", file=sys.stderr)
    query = f"{area} {keywords}"
    all_notes = []
    for sort in ["popular", "general"]:
        notes = xhs_search(query, sort=sort, limit=20)
        all_notes.extend(notes)
        time.sleep(2)

    # 去重
    seen_ids = set()
    unique_notes = []
    for n in all_notes:
        nid = n.get("id", "")
        if nid not in seen_ids:
            seen_ids.add(nid)
            unique_notes.append(n)

    # 过滤南山区相关
    nanshan_notes = filter_nanshan_notes(unique_notes, area)
    print(f"  找到 {len(unique_notes)} 篇笔记，其中 {len(nanshan_notes)} 篇与{area}相关", file=sys.stderr)

    if not nanshan_notes:
        nanshan_notes = unique_notes  # 降级：使用全部

    # Step 2: 读取笔记正文，提取餐厅
    print(f"[2/4] 读取笔记正文...", file=sys.stderr)
    all_restaurants = {}  # name -> {mention_count, sources}

    for i, note in enumerate(nanshan_notes[:15]):  # 最多读15篇
        nc = note.get("note_card", {})
        nid = note.get("id", "")
        xsec = note.get("xsec_token", "")
        title = nc.get("display_title", "")

        # 优先用 Python 库读取（更稳定）
        desc = xhs_read_note_python(nid, xsec)
        if not desc:
            desc = xhs_read_note(nid, xsec)

        if desc:
            restaurants = extract_restaurants_from_text(desc)
            for r in restaurants:
                if r not in all_restaurants:
                    all_restaurants[r] = {"mention_count": 1, "sources": [title]}
                else:
                    all_restaurants[r]["mention_count"] += 1
                    all_restaurants[r]["sources"].append(title)

        print(f"  [{i+1}/{min(len(nanshan_notes), 15)}] {title} → {len(restaurants)} 个餐厅", file=sys.stderr)
        time.sleep(2)

    print(f"  共提取 {len(all_restaurants)} 个餐厅", file=sys.stderr)

    # Step 3: 去重 + 用高德数据丰富（限制查询数量避免超时）
    print(f"[3/4] 高德 POI 查询...", file=sys.stderr)

    # 去重：有些餐厅名只差一两个字（如"嘉华小吃"和"嘉华小吃蛇口店"），合并为一家
    merged = {}
    for name, info in all_restaurants.items():
        # 用前6字符作为去重 key
        key = name[:6]
        if key in merged:
            merged[key]["mention_count"] += info["mention_count"]
            merged[key]["sources"] = (merged[key]["sources"] + info["sources"])[:5]
        else:
            merged[key] = {"name": name, **info}

    enriched = []
    # 按 mention_count 排序，优先查热门餐厅
    sorted_restaurants = sorted(merged.values(), key=lambda x: x["mention_count"], reverse=True)
    for info in sorted_restaurants[:25]:  # 最多查25家
        name = info["name"]
        amap_data = enrich_restaurant(name)
        if amap_data:
            entry = {
                **amap_data,
                "mention_count": info["mention_count"],
                "xhs_sources": info["sources"][:3],
            }
            enriched.append(entry)
            print(f"  ✅ {name} → 人均{amap_data.get('per_capita', 'N/A')} 评分{amap_data.get('rating', 'N/A')}", file=sys.stderr)
        else:
            # 高德查不到，保留小红书数据
            enriched.append({
                "name": name,
                "address": "",
                "type": "",
                "per_capita": "",
                "rating": "",
                "open_time": "",
                "tel": "",
                "mention_count": info["mention_count"],
                "xhs_sources": info["sources"][:3],
            })
            print(f"  ⚠️ {name} → 高德无数据", file=sys.stderr)
        time.sleep(1.5)

    # 剩余餐厅不查高德，直接加入
    for info in sorted_restaurants[25:]:
        enriched.append({
            "name": info["name"],
            "address": "",
            "type": "",
            "per_capita": "",
            "rating": "",
            "open_time": "",
            "tel": "",
            "mention_count": info["mention_count"],
            "xhs_sources": info["sources"][:3],
        })

    # Step 4: 打分排序
    print(f"[4/4] 生成推荐...", file=sys.stderr)
    user_prefs = {
        "budget_max": budget_max,
        "spicy": True,  # 默认嗜辣
        "seafood": True,  # 默认海鲜
    }

    for r in enriched:
        r["score"] = score_restaurant(r, user_prefs)

    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)

    # 格式化输出
    top_recommendations = enriched[:top_n]

    result = {
        "query": {
            "location": location,
            "area": area,
            "keywords": keywords,
            "top_n": top_n,
            "budget_max": budget_max,
        },
        "stats": {
            "xhs_notes_found": len(unique_notes),
            "xhs_notes_read": min(len(nanshan_notes), 15),
            "restaurants_extracted": len(all_restaurants),
            "restaurants_with_amap": sum(1 for r in enriched if r.get("per_capita")),
        },
        "recommendations": top_recommendations,
    }

    return result


# ─── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="餐厅推荐 — 小红书 + 高德融合推荐")
    parser.add_argument("--user-id", required=True, help="用户 ID")
    parser.add_argument("--location", required=True, help="用户当前位置（如 '后海地铁站'）")
    parser.add_argument("--area", default="南山区", help="搜索区域（默认：南山区）")
    parser.add_argument("--keywords", default="美食 探店", help="搜索关键词")
    parser.add_argument("--top-n", type=int, default=8, help="返回推荐数量（默认：8）")
    parser.add_argument("--budget-max", type=int, default=200, help="最大人均预算（默认：200）")
    parser.add_argument("--user-spicy", action="store_true", default=True, help="用户嗜辣（默认：True）")
    parser.add_argument("--user-seafood", action="store_true", default=True, help="用户喜欢海鲜（默认：True）")
    parser.add_argument("--json", action="store_true", default=True, help="JSON 输出")

    args = parser.parse_args()

    result = generate_recommendations(
        user_id=args.user_id,
        location=args.location,
        area=args.area,
        keywords=args.keywords,
        top_n=args.top_n,
        budget_max=args.budget_max,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
