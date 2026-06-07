#!/usr/bin/env node

// ── 加载 .env ──────────────────────────────────────────────────────────
(function loadEnv() {
  const fs = require("fs");
  const path = require("path");
  const envPath = path.resolve(__dirname, "..", ".env");
  try {
    const raw = fs.readFileSync(envPath, "utf8");
    for (const line of raw.split("\n")) {
      const m = line.match(/^\s*([^#=]+)\s*=\s*(.+)/);
      if (m) process.env[m[1].trim()] = m[2].trim();
    }
  } catch (_) {}
})();

/**
 * OpenClaw Tool: 泛内容与攻略检索 (social_guide.js)
 * 具备真实搜索 API + 双链路 Mock 自适应与异常兜底保护
 *
 * 真实搜索配置（可选）:
 *   SEARCH_API_KEY=your-key                 — 搜索 API Key
 *   SEARCH_API_ENDPOINT=https://api.search.com/v1/search  — 自定义端点
 *   未配置时自动降级到 mock-server → 硬编码兜底
 *
 * 使用方式:
 *   node scripts/social_guide.js search --keywords "周末 探店" --tag-filters "Mexican,小龙虾"
 */

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];
  const params = {};

  for (let i = 1; i < args.length; i++) {
    if (args[i].startsWith('--')) {
      const key = args[i].substring(2);
      const val = args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : true;
      params[key] = val;
      if (val !== true) i++;
    }
  }

  if (command !== 'search') {
    console.error(JSON.stringify({ error: "Invalid command. Usage: node social_guide.js search [options]" }));
    process.exit(1);
  }

  const keywords = params['keywords'] || '';
  const tagFilters = params['tag-filters'] || '';
  const requirePetFriendly = params['require-pet-friendly'] || false;

  // ── 第1层：真实搜索 API ──────────────────────────────────────────────
  const searchApiKey = process.env.SEARCH_API_KEY;
  const searchApiEndpoint = process.env.SEARCH_API_ENDPOINT;

  if (searchApiKey && searchApiEndpoint) {
    try {
      const results = await searchSocialFromAPI(searchApiEndpoint, searchApiKey, keywords, tagFilters, requirePetFriendly);
      console.log(JSON.stringify(results));
      return;
    } catch (apiErr) {
      // 真实搜索 API 失败，静默降级
    }
  }

  // ── 第2层：Mock Server 双链路 ────────────────────────────────────────
  const queryParams = new URLSearchParams();
  if (keywords) queryParams.append('keyword', keywords);
  if (tagFilters) queryParams.append('tags', tagFilters);
  if (requirePetFriendly) queryParams.append('pet_friendly', requirePetFriendly);

  const urlA = `http://172.17.0.1:5001/sandbox/social/search?${queryParams.toString()}`;
  const urlB = `http://127.0.0.1:5001/sandbox/social/search?${queryParams.toString()}`;

  async function fetchWithTimeout(urlStr) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(urlStr, { method: 'GET', signal: controller.signal });
    clearTimeout(id);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  try {
    console.log(JSON.stringify(await fetchWithTimeout(urlA)));
    return;
  } catch (errA) {
    try {
      console.log(JSON.stringify(await fetchWithTimeout(urlB)));
      return;
    } catch (errB) {
      // 第3层：硬编码兜底
      const fallbackData = {
        results: [
          { post_id: "fb01", content: "南山科技园附近新开的墨西哥塔可店，Fajitas 绝赞，室外区域允许带猫。涉及实体店：[Taco Libre]" },
          { post_id: "fb02", content: "周末解压必去的十三香小龙虾，营业到凌晨，朋友聚会首选。涉及实体店：[辣胖子小龙虾]" },
          { post_id: "fb03", content: "Señor Taco 墨西哥餐厅，Taco 种类丰富，莎莎酱是一绝，环境轻松。涉及实体店：[Señor Taco]" },
          { post_id: "fb04", content: "El Torito 墨西哥烤肉，适合肉食爱好者，分量十足，性价比高。涉及实体店：[El Torito]" }
        ],
        extracted_pois: ["Taco Libre", "辣胖子小龙虾", "Señor Taco", "El Torito"],
        _fallback: true
      };
      console.log(JSON.stringify(fallbackData));
    }
  }
}

/**
 * 调用真实搜索 API 获取攻略数据
 * 适配标准 RESTful 搜索接口（GET /search?q=...&tags=...）
 * 返回格式与 mock 链路保持一致: { results, extracted_pois }
 */
async function searchSocialFromAPI(endpoint, apiKey, keywords, tagFilters, requirePetFriendly) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        api_key: apiKey,
        query: `${keywords} ${tagFilters || ''} ${requirePetFriendly ? 'pet friendly' : ''}`.trim(),
        search_depth: 'basic',
        max_results: 10,
        include_raw_content: false
      }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();

    // 尝试从通用搜索响应中提取结构化数据
    // 适配多种可能的响应格式
    const rawResults = data.results || data.data || data.items || [];
    const results = rawResults.map((item, idx) => ({
      post_id: item.id || item.post_id || `search_${idx}`,
      content: item.content || item.snippet || item.description || item.title || JSON.stringify(item)
    }));

    // 从内容中提取可能的店铺名（简单启发式：[...] 内的文本）
    const extracted_pois = [];
    for (const r of results) {
      const matches = r.content.match(/\[([^\]]+)\]/g);
      if (matches) {
        for (const m of matches) {
          const name = m.replace(/[\[\]]/g, '');
          if (!extracted_pois.includes(name)) extracted_pois.push(name);
        }
      }
    }

    return { results, extracted_pois, source: 'real_search_api' };
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

main();
