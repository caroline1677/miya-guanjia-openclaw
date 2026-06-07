#!/usr/bin/env node
/**
 * 本地生活沙盒 API 服务器 (端口 5001)
 * 模拟动态餐厅排队状态、打车 ETA、天气，支持监控注册和告警查询
 *
 * 启动方式:
 *   node scripts/sandbox_server.js
 *   或后台运行:
 *   nohup node scripts/sandbox_server.js &
 *
 * 验证:
 *   curl http://localhost:5001/restaurant/海底捞福田/queue
 *   curl http://localhost:5001/taxi/estimate
 *   curl http://localhost:5001/weather
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 5001;
const ALERTS_DIR = path.join(__dirname, '..', 'alerts');

// 确保目录存在
if (!fs.existsSync(ALERTS_DIR)) fs.mkdirSync(ALERTS_DIR, { recursive: true });

// 餐厅基础配置
const RESTAURANTS = {
  '海底捞福田': { baseWait: 8, baseMin: 40, peakHours: [11, 12, 18, 19, 20] },
  '海底捞南山': { baseWait: 6, baseMin: 30, peakHours: [11, 12, 18, 19, 20] },
  '海底捞罗湖': { baseWait: 10, baseMin: 50, peakHours: [11, 12, 18, 19, 20, 21] },
};

function getDynamicStatus(restaurantName) {
  const config = RESTAURANTS[restaurantName];
  if (!config) {
    return { error: '餐厅不存在', available: Object.keys(RESTAURANTS) };
  }

  const now = new Date();
  const hour = now.getHours();
  const isPeak = config.peakHours.includes(hour);

  // 模拟动态变化：基于时间 + 随机波动
  const seed = (now.getTime() / 60000) | 0;
  const pseudoRandom = Math.sin(seed * 127.1 + seed * 311.7) * 0.5 + 0.5;

  let waiting = config.baseWait + Math.floor(pseudoRandom * (isPeak ? 12 : 6));
  waiting = Math.max(1, waiting);

  const estimatedMin = waiting * 5;
  const virtualTime = new Date(now.getTime() + estimatedMin * 60000);

  return {
    restaurant: restaurantName,
    waiting,
    estimated_min: estimatedMin,
    virtual_time: virtualTime.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    is_peak: isPeak,
    updated_at: now.toISOString()
  };
}

function getTaxiEstimate() {
  const now = new Date();
  const hour = now.getHours();
  const isPeak = [7, 8, 9, 17, 18, 19].includes(hour);
  const surge = isPeak ? (1.2 + Math.random() * 0.8) : 1.0;
  const etaMinutes = isPeak ? Math.floor(8 + Math.random() * 12) : Math.floor(3 + Math.random() * 7);

  return {
    eta_minutes: etaMinutes,
    surge: Math.round(surge * 100) / 100,
    condition: isPeak ? 'peak' : 'normal',
    updated_at: now.toISOString()
  };
}

function getWeather() {
  const conditions = ['晴', '多云', '阴', '小雨', '雷阵雨'];
  const now = new Date();
  const seed = (now.getTime() / 3600000) | 0;
  const idx = Math.abs(Math.sin(seed * 73.17) * conditions.length) | 0;
  const condition = conditions[idx];
  const temp = 22 + Math.floor(Math.abs(Math.sin(seed * 41.3) * 10));

  return {
    condition,
    temp_c: temp,
    humidity: 50 + Math.floor(Math.abs(Math.sin(seed * 29.7) * 30)),
    outdoor: ['晴', '多云'].includes(condition),
    updated_at: now.toISOString()
  };
}

function checkAlerts(restaurantName) {
  const status = getDynamicStatus(restaurantName);
  const alerts = [];

  const usersDir = path.join(__dirname, '..', 'users');
  if (fs.existsSync(usersDir)) {
    const users = fs.readdirSync(usersDir);
    for (const userId of users) {
      const tasksFile = path.join(usersDir, userId, 'tasks.json');
      if (fs.existsSync(tasksFile)) {
        const tasks = JSON.parse(fs.readFileSync(tasksFile, 'utf8'));
        const taskList = Array.isArray(tasks) ? tasks : Object.values(tasks);
        for (const task of taskList) {
          if (task.status === 'active' && task.params && task.params.restaurant === restaurantName && status.waiting <= task.params.threshold) {
            alerts.push({
              task_id: task.id,
              user_id: userId,
              restaurant: restaurantName,
              waiting: status.waiting,
              threshold: task.params.threshold,
              message: task.notify_message,
              triggered_at: new Date().toISOString()
            });

            task.status = 'fired';
            task.triggered_at = new Date().toISOString();
            fs.writeFileSync(tasksFile, JSON.stringify(tasks, null, 2));
          }
        }
      }
    }
  }

  return alerts;
}

// ── 路由分发 ──────────────────────────────────────────────────────────

function matchRoute(pathname, pattern) {
  const pParts = pathname.split('/').filter(Boolean);
  const rParts = pattern.split('/').filter(Boolean);
  if (pParts.length !== rParts.length) return null;
  const params = {};
  for (let i = 0; i < rParts.length; i++) {
    if (rParts[i].startsWith(':')) {
      params[rParts[i].slice(1)] = decodeURIComponent(pParts[i]);
    } else if (rParts[i] !== pParts[i]) {
      return null;
    }
  }
  return params;
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const pathname = url.pathname;

  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Access-Control-Allow-Origin', '*');

  // ── 业务脚本对齐路由 ────────────────────────────────────────────────

  // GET /restaurant/:name/queue  — 餐厅排队查询
  const queueParams = matchRoute(pathname, '/restaurant/:name/queue');
  if (queueParams) {
    const status = getDynamicStatus(queueParams.name);
    if (status.error) {
      res.statusCode = 404;
      res.end(JSON.stringify(status));
      return;
    }
    res.end(JSON.stringify(status));
    return;
  }

  // GET /taxi/estimate  — 打车 ETA（基础）
  if (pathname === '/taxi/estimate') {
    res.end(JSON.stringify(getTaxiEstimate()));
    return;
  }

  // POST /taxi/start  — 预估打车价格（含起终点、车型）
  if (pathname === '/taxi/start' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const origin = data.origin || '未知起点';
        const destination = data.destination || '未知终点';
        // 用高德坐标估算距离（简化：根据起终点名称哈希模拟距离）
        const hash = (origin + destination).split('').reduce((a, c) => a + c.charCodeAt(0), 0);
        const distKm = 5 + (hash % 40);       // 5-45 公里
        const durationMin = Math.floor(distKm * 1.5 + 5);  // 约 1.5 分钟/公里 + 起步
        const now = new Date();
        const hour = now.getHours();
        const isPeak = [7, 8, 9, 17, 18, 19].includes(hour);
        const surge = isPeak ? 1.3 : 1.0;

        const products = [
          { product_name: '特惠快车', total_price: Math.round(distKm * 2.5 * 0.7 * surge * 10) / 10 },
          { product_name: '快车',     total_price: Math.round(distKm * 2.5 * surge * 10) / 10 },
          { product_name: '专车',     total_price: Math.round(distKm * 5.5 * surge * 10) / 10 },
        ];

        res.end(JSON.stringify({
          origin, destination,
          distance_km: distKm,
          duration_min: durationMin,
          surge: Math.round(surge * 100) / 100,
          condition: isPeak ? 'peak' : 'normal',
          product_list: products,
          updated_at: now.toISOString()
        }));
      } catch (e) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: '请求体格式错误', detail: e.message }));
      }
    });
    return;
  }

  // POST /taxi/scenario  — 一键叫车（模拟下单+司机接单）
  if (pathname === '/taxi/scenario' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const origin = data.origin || '未知起点';
        const destination = data.destination || '未知终点';
        const productCategory = data.product_category || 1;
        const categoryMap = { 1: '快车', 201: '特惠快车', 8: '专车', 17: '豪华车' };
        const carType = categoryMap[productCategory] || '快车';

        const hash = (origin + destination).split('').reduce((a, c) => a + c.charCodeAt(0), 0);
        const distKm = 5 + (hash % 40);
        const now = new Date();
        const orderId = 'DIDI' + now.getFullYear() + String(Math.floor(Math.random() * 900000 + 100000));

        const driverNames = ['张师傅', '李师傅', '王师傅', '赵师傅', '刘师傅'];
        const driverName = driverNames[hash % driverNames.length];
        const carPlates = ['粤B·12345', '粤B·67890', '粤B·ABC12', '粤B·55555', '粤B·88888'];
        const carPlate = carPlates[hash % carPlates.length];
        const etaMin = 3 + (hash % 8);

        // 存储订单到内存（供 /taxi/order 查询）
        if (!global._taxiOrders) global._taxiOrders = {};
        global._taxiOrders[orderId] = {
          order_id: orderId,
          origin, destination,
          product_category: productCategory,
          car_type: carType,
          driver: { name: driverName, car_plate: carPlate, phone: '1380000' + String(hash % 10000).padStart(4, '0') },
          eta_min: etaMin,
          distance_km: distKm,
          status: 'matched',
          created_at: now.toISOString(),
          steps: [
            { time: now.toISOString(), status: 'created', message: '订单已创建' },
            { time: new Date(now.getTime() + 5000).toISOString(), status: 'matched', message: '司机已接单' },
            { time: new Date(now.getTime() + etaMin * 60000).toISOString(), status: 'arriving', message: '司机即将到达' },
          ]
        };

        res.end(JSON.stringify({
          order: {
            order_id: orderId,
            origin, destination,
            car_type: carType,
            driver: { name: driverName, car_plate: carPlate },
            eta_min: etaMin,
            distance_km: distKm,
            status: 'matched'
          }
        }));
      } catch (e) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: '请求体格式错误', detail: e.message }));
      }
    });
    return;
  }

  // GET /taxi/order  — 查询订单
  if (pathname === '/taxi/order') {
    const orderId = url.searchParams.get('order_id');
    if (orderId && global._taxiOrders && global._taxiOrders[orderId]) {
      res.end(JSON.stringify(global._taxiOrders[orderId]));
    } else if (!orderId && global._taxiOrders) {
      const orders = Object.values(global._taxiOrders);
      res.end(JSON.stringify({ orders, count: orders.length }));
    } else {
      res.end(JSON.stringify({ orders: [], count: 0, message: '暂无订单' }));
    }
    return;
  }

  // GET /taxi/driver  — 查询司机位置
  if (pathname === '/taxi/driver') {
    const orderId = url.searchParams.get('order_id');
    if (orderId && global._taxiOrders && global._taxiOrders[orderId]) {
      const order = global._taxiOrders[orderId];
      const now = new Date();
      // 模拟司机移动：随时间减少距离
      const elapsed = (now - new Date(order.created_at)) / 60000; // 分钟
      const progress = Math.min(elapsed / order.eta_min, 1);
      const remainingKm = Math.round(order.distance_km * (1 - progress) * 10) / 10;
      const remainingMin = Math.max(0, Math.round(order.eta_min * (1 - progress)));

      res.end(JSON.stringify({
        order_id: orderId,
        driver: order.driver,
        status: progress >= 1 ? 'arrived' : 'en_route',
        remaining_km: remainingKm,
        remaining_min: remainingMin,
        updated_at: now.toISOString()
      }));
    } else {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: '订单不存在', order_id: orderId }));
    }
    return;
  }

  // GET /weather  — 天气
  if (pathname === '/weather') {
    res.end(JSON.stringify(getWeather()));
    return;
  }

  // ── 监控/告警路由 ──────────────────────────────────────────────────

  // GET /api/alerts/pending?user_id=xxx
  if (pathname === '/api/alerts/pending') {
    const userId = url.searchParams.get('user_id');
    const pendingAlerts = [];

    const usersDir = path.join(__dirname, '..', 'users');
    if (fs.existsSync(usersDir)) {
      const users = fs.readdirSync(usersDir);
      for (const uid of users) {
        if (userId && uid !== userId) continue;
        const tasksFile = path.join(usersDir, uid, 'tasks.json');
        if (fs.existsSync(tasksFile)) {
          const tasks = JSON.parse(fs.readFileSync(tasksFile, 'utf8'));
          const taskList = Array.isArray(tasks) ? tasks : Object.values(tasks);
          for (const task of taskList) {
            if (task.status === 'active' && task.params) {
              const status = getDynamicStatus(task.params.restaurant);
              if (status.waiting && status.waiting <= task.params.threshold) {
                pendingAlerts.push({
                  task_id: task.id,
                  user_id: uid,
                  restaurant: task.params.restaurant,
                  waiting: status.waiting,
                  threshold: task.params.threshold,
                  message: task.notify_message,
                  estimated_min: status.estimated_min
                });
              }
            }
          }
        }
      }
    }

    res.end(JSON.stringify({ alerts: pendingAlerts, count: pendingAlerts.length }));
    return;
  }

  // GET /api/alerts/check?restaurant=海底捞福田
  if (pathname === '/api/alerts/check') {
    const restaurant = url.searchParams.get('restaurant');
    if (!restaurant) {
      res.statusCode = 400;
      res.end(JSON.stringify({ error: '缺少 restaurant 参数' }));
      return;
    }
    const alerts = checkAlerts(restaurant);
    res.end(JSON.stringify({ alerts, count: alerts.length }));
    return;
  }

  // ── 兼容旧路由（保留） ─────────────────────────────────────────────

  // GET /api/restaurant/status?name=海底捞福田
  if (pathname === '/api/restaurant/status') {
    const name = url.searchParams.get('name');
    if (!name) {
      res.statusCode = 400;
      res.end(JSON.stringify({ error: '缺少 name 参数' }));
      return;
    }
    const status = getDynamicStatus(name);
    res.end(JSON.stringify(status));
    return;
  }

  // GET /api/restaurant/list
  if (pathname === '/api/restaurant/list') {
    const list = Object.keys(RESTAURANTS).map(name => getDynamicStatus(name));
    res.end(JSON.stringify(list));
    return;
  }

  // ── 泛内容搜索（小红书/攻略模拟）──────────────────────────────────

  // GET /sandbox/social/search?keyword=...&tags=...&pet_friendly=true
  if (pathname === '/sandbox/social/search') {
    const keyword = url.searchParams.get('keyword') || '';
    const tags = url.searchParams.get('tags') || '';
    const petFriendly = url.searchParams.get('pet_friendly') === 'true';

    // 模拟搜索结果（基于关键词和标签过滤）
    const allPosts = [
      { post_id: 'p001', content: '南山科技园附近新开的墨西哥塔可店，Fajitas 绝赞，室外区域允许带猫。涉及实体店：[Taco Libre]', tags: ['Mexican', 'pet_friendly'] },
      { post_id: 'p002', content: '周末解压必去的十三香小龙虾，营业到凌晨，朋友聚会首选。涉及实体店：[辣胖子小龙虾]', tags: ['小龙虾', '夜宵'] },
      { post_id: 'p003', content: 'Señor Taco 墨西哥餐厅，Taco 种类丰富，莎莎酱是一绝，环境轻松。涉及实体店：[Señor Taco]', tags: ['Mexican'] },
      { post_id: 'p004', content: 'El Torito 墨西哥烤肉，适合肉食爱好者，分量十足，性价比高。涉及实体店：[El Torito]', tags: ['Mexican', '烤肉'] },
      { post_id: 'p005', content: '深圳湾附近的宠物友好咖啡厅，可以带猫，环境超棒。涉及实体店：[Paw Coffee]', tags: ['咖啡', 'pet_friendly'] },
      { post_id: 'p006', content: '科技园附近好吃的川菜馆，麻辣鲜香，价格合理。涉及实体店：[蜀味轩]', tags: ['川菜', '辣'] },
      { post_id: 'p007', content: '福田CBD的日料店，刺身新鲜，环境优雅。涉及实体店：[鮨一]', tags: ['日料'] },
      { post_id: 'p008', content: '罗湖老字号粤菜，早茶点心一绝。涉及实体店：[点都德]', tags: ['粤菜', '早茶'] },
    ];

    // 过滤
    let filtered = allPosts;
    if (keyword) {
      const kw = keyword.toLowerCase();
      filtered = filtered.filter(p => p.content.toLowerCase().includes(kw) || p.tags.some(t => t.toLowerCase().includes(kw)));
    }
    if (tags) {
      const tagList = tags.split(',').map(t => t.trim().toLowerCase());
      filtered = filtered.filter(p => p.tags.some(t => tagList.includes(t.toLowerCase())));
    }
    if (petFriendly) {
      filtered = filtered.filter(p => p.tags.includes('pet_friendly'));
    }

    // 提取 POI
    const extractedPois = [];
    for (const post of filtered) {
      const matches = post.content.match(/\[([^\]]+)\]/g);
      if (matches) {
        for (const m of matches) {
          const name = m.replace(/[\[\]]/g, '');
          if (!extractedPois.includes(name)) extractedPois.push(name);
        }
      }
    }

    res.end(JSON.stringify({
      results: filtered,
      extracted_pois: extractedPois,
      keyword,
      tags,
      pet_friendly: petFriendly,
      total: filtered.length
    }));
    return;
  }

  // 兜底
  res.statusCode = 404;
  res.end(JSON.stringify({ error: '未知接口', available: [
    'GET /restaurant/:name/queue',
    'GET /taxi/estimate',
    'POST /taxi/start',
    'POST /taxi/scenario',
    'GET /taxi/order',
    'GET /taxi/driver',
    'GET /weather',
    'GET /api/alerts/pending?user_id=...',
    'GET /api/alerts/check?restaurant=...',
    'GET /api/restaurant/status?name=...',
    'GET /api/restaurant/list',
    'GET /sandbox/social/search?keyword=...&tags=...&pet_friendly=...'
  ]}));
});

server.listen(PORT, () => {
  console.log(`[沙盒API] 本地生活沙盒已启动，端口 ${PORT}`);
  console.log(`[沙盒API] 监控餐厅: ${Object.keys(RESTAURANTS).join(', ')}`);
});

module.exports = { getDynamicStatus, getTaxiEstimate, getWeather, checkAlerts };
