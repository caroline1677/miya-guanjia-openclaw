#!/usr/bin/env bash
# discover_activities.sh — 活动候选发现脚本
# 用法: bash discover_activities.sh --city 深圳 --area 南山区 --interests "美食,看展,密室" --duration half_day --pet-friendly true
# 输出: JSON 格式的候选活动列表

set -euo pipefail

# 默认参数
CITY="深圳"
AREA=""
INTERESTS=""
DURATION="half_day"
PET_FRIENDLY="true"
OUTPUT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --city) CITY="$2"; shift 2;;
    --area) AREA="$2"; shift 2;;
    --interests) INTERESTS="$2"; shift 2;;
    --duration) DURATION="$2"; shift 2;;
    --pet-friendly) PET_FRIENDLY="$2"; shift 2;;
    --output) OUTPUT_FILE="$2"; shift 2;;
    *) echo "Unknown option: $1"; exit 1;;
  esac
done

# 构建搜索关键词
SEARCH_TERMS=()
IFS=',' read -ra INTEREST_ARRAY <<< "$INTERESTS"
for interest in "${INTEREST_ARRAY[@]}"; do
  interest=$(echo "$interest" | xargs)  # trim
  if [[ -n "$AREA" ]]; then
    SEARCH_TERMS+=("${CITY}${AREA}${interest}推荐")
  fi
  SEARCH_TERMS+=("${CITY}${interest}推荐")
  SEARCH_TERMS+=("${CITY}${interest}攻略")
done

# 去重
UNIQUE_TERMS=($(echo "${SEARCH_TERMS[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))

echo "{"
echo "  \"search_terms\": ["
for i in "${!UNIQUE_TERMS[@]}"; do
  COMMA=""
  if [[ $i -lt $((${#UNIQUE_TERMS[@]}-1)) ]]; then COMMA=","; fi
  echo "    \"${UNIQUE_TERMS[$i]}\"$COMMA"
done
echo "  ],"
echo "  \"filters\": {"
echo "    \"city\": \"$CITY\","
echo "    \"area\": \"$AREA\","
echo "    \"duration\": \"$DURATION\","
echo "    \"pet_friendly\": $PET_FRIENDLY"
echo "  },"
echo "  \"note\": \"Use xhs search with these terms, then verify candidates with amap POI search.\""
echo "}"
