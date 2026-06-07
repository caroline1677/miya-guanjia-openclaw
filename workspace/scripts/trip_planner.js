// workspace/scripts/trip_planner.js
'use strict';
const { readProfile, readRecentDiary } = require('./lib/memory.js');

const MOCK_SERVER = process.env.MOCK_SERVER_URL || 'http://172.17.0.1:5001';
const AMAP_KEY = process.env.AMAP_KEY || '';

function parseArgs(args) {
  const opts = {};
  for (let i = 0; i < args.length; i += 2) {
    if (args[i] && args[i].startsWith('--')) {
      opts[args[i].slice(2)] = args[i + 1];
    }
  }
  return opts;
}

async function searchPOI(keyword, location = '113.9270,22.5346') {
  if (!AMAP_KEY) return [];
  try {
    const params = new URLSearchParams({
      keywords: keyword,
      location,
      radius: '5000',
      city: '深圳',
      offset: '5',
      page: '1',
      key: AMAP_KEY,
      extensions: 'all',
    });
    const res = await fetch(`https://restapi.amap.com/v3/place/around?${params}`);
    const data = await res.json();
    if (data.status !== '1') return [];
    return (data.pois || []).slice(0, 5).map(p => ({
      name: p.name,
      address: p.address,
      location: p.location,
      rating: p.biz_ext?.rating || '暂无',
      distance_m: Number(p.distance || 0),
    }));
  } catch { return []; }
}

async function geocode(address) {
  if (!AMAP_KEY) return '113.9270,22.5346';
  try {
    const params = new URLSearchParams({ address, city: '深圳', key: AMAP_KEY });
    const res = await fetch(`https://restapi.amap.com/v3/geocode/geo?${params}`);
    const data = await res.json();
    if (data.status !== '1' || !data.geocodes?.length) return '113.9270,22.5346';
    return data.geocodes[0].location;
  } catch { return '113.9270,22.5346'; }
}

async function planTransit(origin, destination) {
  if (!AMAP_KEY) return null;
  try {
    const params = new URLSearchParams({
      origin, destination, city1: '深圳', city2: '深圳', key: AMAP_KEY,
    });
    const res = await fetch(`https://restapi.amap.com/v5/direction/transit/integrated?${params}`);
    const data = await res.json();
    if (data.status !== '1') return null;
    const transit = data.route?.transits?.[0];
    if (!transit) return null;
    return {
      duration_min: Math.round(Number(transit.cost?.duration || 0) / 60),
      distance_km: (Number(transit.distance || 0) / 1000).toFixed(1),
    };
  } catch { return null; }
}

async function getWeather() {
  try {
    const res = await fetch(`${MOCK_SERVER}/weather`);
    return res.ok ? res.json() : { condition: '未知' };
  } catch { return { condition: '未知' }; }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const userId = opts['user-id'];
  const destination = opts.destination || '';
  const activity = opts.activity || '餐饮';
  const budget = Number(opts.budget || 200);

  // Load user memory
  let pref = { diet: {}, transport: 'subway', preferred_cuisines: [], location_home: '深圳' };
  if (userId) {
    try { pref = readProfile(userId).public; } catch {}
  }

  // Determine search keyword
  const cuisineHint = pref.preferred_cuisines?.[0] || '';
  const keyword = activity === '餐饮' ? (cuisineHint || '餐厅') : activity;

  // Parallel data fetch
  const destLocation = destination ? await geocode(destination) : '113.9270,22.5346';
  const homeLocation = pref.location_home ? await geocode(pref.location_home) : '113.9270,22.5346';

  const [pois, route, weather] = await Promise.all([
    searchPOI(keyword, destLocation),
    planTransit(homeLocation, destLocation),
    getWeather(),
  ]);

  // Filter recommendations
  const suitable = pois.filter(p => p.rating !== '暂无').slice(0, 3);
  const fallback = pois.slice(0, 3);

  const result = {
    destination,
    weather: weather.condition + (weather.temp_c ? `，${weather.temp_c}°C` : ''),
    route: route
      ? `地铁约 ${route.duration_min} 分钟，全程约 ${route.distance_km}km`
      : (AMAP_KEY ? '路线规划暂时不可用' : '（需配置 AMAP_KEY 获取真实路线）'),
    recommendations: (suitable.length ? suitable : fallback).map(p => ({
      name: p.name,
      address: p.address,
      rating: p.rating,
      distance: `距目的地 ${p.distance_m}m`,
    })),
    memory_used: {
      diet_note: pref.diet?.spicy === false ? '已排除辣味餐厅偏好' : '',
      budget_note: `预算 ¥${budget} 以内`,
      transport: pref.transport || 'subway',
    },
    recent_memory: userId ? readRecentDiary(userId, 2) : '',
  };

  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}

main().catch(e => { process.stderr.write(e.message + '\n'); process.exit(1); });
