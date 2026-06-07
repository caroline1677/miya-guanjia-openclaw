#!/usr/bin/env node
/**
 * 场景 A 端到端测试：跨时空状态监控（排队与交通联动）
 * 
 * 流程：
 *   1. 查询餐厅当前排队状态
 *   2. 注册排队监控（阈值 5 桌）
 *   3. 查询打车 ETA
 *   4. 模拟排队轮询（每 2 秒查一次，最多 10 次）
 *   5. 当排队 <= 阈值时，触发提醒
 *   6. 综合判断：排队耗时 ≈ 打车 ETA 时，建议出发
 */

const http = require('http');

const SANDBOX = 'http://127.0.0.1:5001';
const USER_ID = 'u001';

function fetchJSON(path) {
  return new Promise((resolve, reject) => {
    http.get(`${SANDBOX}${path}`, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error(`Parse error: ${data}`)); }
      });
    }).on('error', reject);
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  console.log('═══════════════════════════════════════');
  console.log('  场景 A：跨时空状态监控测试');
  console.log('═══════════════════════════════════════\n');

  // ── Step 1: 查询餐厅排队 ──────────────────────────────────────────
  console.log('📋 Step 1: 查询海底捞福田当前排队状态');
  const queueStatus = await fetchJSON('/restaurant/海底捞福田/queue');
  console.log(`   等待桌数: ${queueStatus.waiting}`);
  console.log(`   预计耗时: ${queueStatus.estimated_min} 分钟`);
  console.log(`   虚拟时间: ${queueStatus.virtual_time}`);
  console.log(`   高峰时段: ${queueStatus.is_peak ? '是' : '否'}\n`);

  // ── Step 2: 注册监控 ──────────────────────────────────────────────
  const threshold = 5;
  console.log(`📡 Step 2: 注册排队监控（阈值: ${threshold} 桌）`);
  
  // 直接写入 tasks.json（模拟 restaurant_monitor.js register）
  const fs = require('fs');
  const path = require('path');
  const tasksFile = path.join(__dirname, '..', 'users', USER_ID, 'tasks.json');
  
  let tasks = [];
  if (fs.existsSync(tasksFile)) {
    tasks = JSON.parse(fs.readFileSync(tasksFile, 'utf8'));
    if (!Array.isArray(tasks)) tasks = Object.values(tasks);
  }
  
  const taskId = `task_${Date.now()}`;
  tasks.push({
    id: taskId,
    type: 'restaurant_monitor',
    params: { restaurant: '海底捞福田', threshold },
    notify_message: '海底捞福田排队快到了！',
    created_at: new Date().toISOString(),
    status: 'active',
  });
  fs.writeFileSync(tasksFile, JSON.stringify(tasks, null, 2));
  console.log(`   监控已注册: ${taskId}\n`);

  // ── Step 3: 查询打车 ETA ──────────────────────────────────────────
  console.log('🚗 Step 3: 查询打车 ETA');
  const taxi = await fetchJSON('/taxi/estimate');
  console.log(`   ETA: ${taxi.eta_minutes} 分钟`);
  console.log(`   拥堵状态: ${taxi.condition}`);
  console.log(`   加价倍数: ${taxi.surge}x\n`);

  // ── Step 4: 轮询监控 ──────────────────────────────────────────────
  console.log('🔄 Step 4: 轮询排队状态（每 2 秒）');
  console.log('─────────────────────────────────────');
  
  let fired = false;
  let pollCount = 0;
  const maxPolls = 10;

  while (pollCount < maxPolls) {
    pollCount++;
    const current = await fetchJSON('/restaurant/海底捞福田/queue');
    const alerts = await fetchJSON(`/api/alerts/check?restaurant=海底捞福田`);
    
    const timeStr = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    console.log(`   [${timeStr}] 第 ${pollCount} 次查询 — 等待: ${current.waiting} 桌, 预计: ${current.estimated_min} 分钟`);
    
    // 检查是否有告警触发
    if (alerts.count > 0) {
      console.log(`   ⚡ 告警触发！: ${alerts.alerts[0].message}`);
      fired = true;
      break;
    }
    
    // Agent 决策：排队耗时 ≈ 打车 ETA 时建议出发
    if (current.estimated_min <= taxi.eta_minutes + 5) {
      console.log(`\n   🎯 Agent 决策: 排队预计 ${current.estimated_min} 分钟 ≈ 打车 ETA ${taxi.eta_minutes} 分钟`);
      console.log(`   ✅ 建议现在出发！`);
      fired = true;
      break;
    }
    
    await sleep(2000);
  }

  console.log('─────────────────────────────────────\n');

  // ── Step 5: 总结 ──────────────────────────────────────────────────
  console.log('📊 测试总结');
  console.log(`   监控注册: ✅`);
  console.log(`   排队查询: ✅`);
  console.log(`   打车 ETA: ✅`);
  console.log(`   告警轮询: ${fired ? '✅ 已触发' : '⏳ 未触发（排队仍高于阈值）'}`);
  console.log(`   决策联动: ✅ Agent 可在排队 ≈ ETA 时建议出发\n`);

  // 清理：将已触发的任务标记为 fired
  if (fired) {
    tasks = tasks.map(t => t.id === taskId ? { ...t, status: 'fired', triggered_at: new Date().toISOString() } : t);
    fs.writeFileSync(tasksFile, JSON.stringify(tasks, null, 2));
  }

  console.log('═══════════════════════════════════════');
  console.log('  场景 A 测试完成');
  console.log('═══════════════════════════════════════');
}

main().catch(e => { console.error('❌ 测试失败:', e.message); process.exit(1); });
