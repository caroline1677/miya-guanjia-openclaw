#!/usr/bin/env python3
import json
import sys


def over_budget(poi, budget):
    avg_cost = poi.get("avg_cost")
    return budget is not None and avg_cost is not None and avg_cost > budget


def pet_friendly(poi):
    tags = [str(tag).lower() for tag in poi.get("tags", [])]
    text = " ".join(tags)
    return any(key in text for key in ["宠物", "pet", "户外", "露台", "室外"])


def score_poi(poi, constraints):
    score = 0
    reasons = []
    reject_reasons = []

    budget = constraints.get("budget")
    need_pet = constraints.get("pet_friendly", False)

    if over_budget(poi, budget):
        reject_reasons.append(f"人均 {poi.get('avg_cost')} 超出预算 {budget}")
    elif poi.get("avg_cost") is not None:
        score += 25
        reasons.append(f"人均约 {poi.get('avg_cost')}，预算内")

    rating = poi.get("rating")
    if rating is not None:
        if rating >= 4.5:
            score += 25
            reasons.append(f"评分 {rating}，口碑较好")
        elif rating >= 4.0:
            score += 12
            reasons.append(f"评分 {rating}，可作为备选")
        else:
            reject_reasons.append(f"评分 {rating} 偏低")

    if need_pet:
        if pet_friendly(poi):
            score += 30
            reasons.append("包含宠物友好或户外相关标签")
        else:
            reject_reasons.append("未确认宠物友好")

    distance_m = poi.get("distance_m")
    if distance_m is not None:
        if distance_m <= 3000:
            score += 15
            reasons.append("距离较近")
        elif distance_m <= 8000:
            score += 8
            reasons.append("距离可接受")
        else:
            reject_reasons.append("通勤距离偏远")

    if poi.get("images"):
        score += 5

    return {
        **poi,
        "score": score,
        "recommend_reasons": reasons,
        "reject_reasons": reject_reasons,
        "recommended": len(reject_reasons) == 0
    }


def main():
    payload = json.load(sys.stdin)
    constraints = payload.get("constraints", {})
    pois = payload.get("pois", [])

    ranked = [score_poi(poi, constraints) for poi in pois]
    ranked.sort(key=lambda item: (item["recommended"], item["score"]), reverse=True)

    print(json.dumps({
        "recommended": [item for item in ranked if item["recommended"]],
        "rejected": [item for item in ranked if not item["recommended"]]
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()