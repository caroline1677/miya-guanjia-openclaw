// workspace/scripts/monitor_poller.js
'use strict';
/**
 * 后台排队监控轮询器（含打车联动）
 *
 * 每 30 秒查询一次排队状态。
 * 当 position <= threshold 时：
 *   1. 调用 /notification/queue 生成 LLM 通知文案
 *   2. 查询打车 ETA（从用户位置到餐厅）
 *   3. 时间匹配：剩余等待时间 ≈ 打车 ETA + 缓冲 → 建议叫车
 *   4. 将通知写入 HEARTBEAT.md（OpenClaw 自动推送给用户）
 *
 * 用法：
 *   node monitor_poller.js \
 *     --user-id ou_xxx --restaurant "海底捞福田" \
 *     --queue-number B004 --threshold 5 --table-type-cn "中桌" \
 *     --restaurant-addr "福田区xxx路xxx号" --user-loc "南山区xxx"
 *
 * 环境变量：
 *   MOCK_SERVER_URL — LM 后端地址（默认 http://mock-server:5001）
 *   POLL_INTERVAL    — 轮询间隔秒数（默认 30）
 *   HEARTBEAT_FILE   — HEARTBEAT.md 路径
 */

const fs = require('fs');
const path = require('path');
const { readProfile } = require('./lib/memory.js');

const MOCK_SERVER = process.env.MOCK_SERVER_URL || 'http://mock-server:5001';
const POLL_INTERVAL = Number(process.env.POLL_INTERVAL || 30);
const WORKSPACE = process.env.WORKSPACE_PATH || path.resolve(__dirname, '..');
const HEARTBEAT_FILE = process.env.HEARTBEAT_FILE || path.join(WORKSPACE, 'HEARTBEAT.md');

// 每桌平均等待时间（分钟）—— 用于估算剩余等待
const AVG_TABLE_TIME = {
  '小桌': 8,
  '中桌': 12,
  '大桌': 20,
};

// 叫车缓冲时间（分钟）—— 到车后走到店 + 余量
const TAXI_BUFFER_MIN = 4;

// ─── API calls ────────────────────────────────────────────────────────────

async function checkNumber(restaurant, queueNumber) {
  const res = await fetch(
    `${MOCK_SERVER}/restaurant/${encodeURIComponent(restaurant)}/queue/${encodeURIComponent(queueNumber)}`
  );
  if (!res.ok) throw new Error(`Status check error ${res.status}: ${await res.text()}`);
  return res.json();
}

async function generateNotification({ restaurant, queueNumber, tableTypeCn, position, estimatedMin, eventMessage }) {
  const body = {
    restaurant,
    queue_number: queueNumber,
    table_type_cn: tableTypeCn,
    position,
    estimated_min: estimatedMin,
    ...(eventMessage && { event_message: eventMessage }),
  };
  const res = await fetch(
    `${MOCK_SERVER}/notification/queue`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
  if (!res.ok) throw new Error(`Notification error ${res.status}: ${await res.text()}`);
  return res.json();
}

// ─── Taxi ETA query (via mcporter + DiDi MCP) ─────────────────────────────

async function getTaxiETA(fromName, toName) {
  const DIDI_MCP_KEY = process.env.DIDI_MCP_KEY;
  if (!DIDI_MCP_KEY) return null;

  const MCP_URL = `https://mcp.didichuxing.com/mcp-servers?key=${DIDI_MCP_KEY}`;
  const args = JSON.stringify({
    from_name: fromName,
    from_lat: '',
    from_lng: '',
    to_name: toName,
    to_lat: '',
    to_lng: '',
  });

  try {
    const { execSync } = require('child_process');
    const output = execSync(
      `mcporter call "${MCP_URL}" taxi_estimate --args '${args}'`,
      { timeout: 15, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const data = JSON.parse(output);
    if (data && data.data) {
      // 取最快车型的 ETA
      const estimates = Array.isArray(data.data) ? data.data : [data.data];
      const fastest = estimates.reduce((min, e) => {
        const eta = e.eta_minutes || e.eta || 999;
        return eta < min ? eta : min;
      }, 999);
      return fastest;
    }
    return null;
  } catch (e) {
    return null;
  }
}

// ─── Time matching decision ────────────────────────────────────────────────

function shouldCallTaxi(position, tableTypeCn, taxiETA) {
  if (taxiETA == null) return { call: false, reason: 'no_taxi_data' };

  const avgPerTable = AVG_TABLE_TIME[tableTypeCn] || 12;
  const remainingWait = position * avgPerTable; // 预计剩余等待（分钟）
  const totalTransit = taxiETA + TAXI_BUFFER_MIN; // 打车 + 缓冲

  return {
    call: totalTransit >= remainingWait - 2, // 允许 2 分钟误差
    remaining_wait: remainingWait,
    taxi_eta: taxiETA,
    total_transit: totalTransit,
    diff: remainingWait - totalTransit,
  };
}

// ─── Heartbeat write ──────────────────────────────────────────────────────

function writeHeartbeat(message) {
  const content = `# HEARTBEAT.md\n\n<!-- 排队监控通知 -->\n${message}\n`;
  fs.writeFileSync(HEARTBEAT_FILE, content, 'utf-8');
}

function clearHeartbeat() {
  const content = '# HEARTBEAT.md\n\n# 无待处理通知\n';
  fs.writeFileSync(HEARTBEAT_FILE, content, 'utf-8');
}

// ─── CLI parser ────────────────────────────────────────────────────────────

function parseArgs(args) {
  const opts = {};
  for (let i = 0; i < args.length; i += 2) {
    if (args[i] && args[i].startsWith('--')) opts[args[i].slice(2)] = args[i + 1];
  }
  return opts;
}

// ─── Main ──────────────────────────────────────────────────────────────────

async function main() {
  const argv = process.argv.slice(2);
  const opts = parseArgs(argv);

  const required = ['user-id', 'restaurant', 'queue-number', 'threshold'];
  const missing = required.filter(k => !opts[k]);
  if (missing.length) {
    process.stderr.write(`缺少参数: --${missing.join(', --')}\n`);
    process.stderr.write(
      'Usage: monitor_poller.js \\\n' +
      '  --user-id <id> --restaurant <name> --queue-number <qn> --threshold <n> \\\n' +
      '  [--table-type-cn <cn>] [--restaurant-addr <addr>] [--user-loc <loc>]\n'
    );
    process.exit(1);
  }

  const userId = opts['user-id'];
  const restaurant = opts.restaurant;
  const queueNumber = opts['queue-number'];
  const threshold = Number(opts.threshold);
  const tableTypeCn = opts['table-type-cn'] || '中桌';
  const restaurantAddr = opts['restaurant-addr'] || '';
  const userLoc = opts['user-loc'] || '';

  // 读取用户记忆获取位置偏好
  let resolvedUserLoc = userLoc;
  if (!resolvedUserLoc) {
    try {
      const profile = readProfile(userId);
      resolvedUserLoc = profile.public?.location_home || '';
    } catch (e) {}
  }

  process.stdout.write(JSON.stringify({
    ok: true,
    action: 'polling_started',
    restaurant,
    queue_number: queueNumber,
    threshold,
    interval_sec: POLL_INTERVAL,
    taxi_call_enabled: !!process.env.DIDI_MCP_KEY,
  }) + '\n');

  let tickCount = 0;
  let notified = false; // 避免重复通知

  while (true) {
    tickCount++;
    try {
      const data = await checkNumber(restaurant, queueNumber);

      // 后端正常返回无 ok 字段，只有 status/position 等
      // 错误返回: {"ok":false,"error":"..."}
      if (data.error) {
        process.stdout.write(JSON.stringify({ ok: false, error: data.error, action: 'retry' }) + '\n');
        await sleep(POLL_INTERVAL * 1000);
        continue;
      }

      const status = data.status || 'unknown';
      const position = data.position != null ? data.position : data.waiting_ahead;
      const estimatedMin = data.estimated_min;
      const eventMessage = data.current_event;

      // 已入座
      if (status === 'seated' || position === 0) {
        const msg = `🎉 你在 ${restaurant} 已入座！`;
        writeHeartbeat(msg);
        process.stdout.write(JSON.stringify({ ok: true, status: 'seated', action: 'done', message: msg }) + '\n');
        break;
      }

      // 过号
      if (status === 'expired') {
        const msg = `⚠️ 你的 ${restaurant} 号码 ${queueNumber} 已过号了，需要重新取号吗？`;
        writeHeartbeat(msg);
        process.stdout.write(JSON.stringify({ ok: true, status: 'expired', action: 'done', message: msg }) + '\n');
        break;
      }

      // 已取消
      if (status === 'cancelled') {
        const msg = `已取消 ${restaurant} 的排队`;
        clearHeartbeat();
        process.stdout.write(JSON.stringify({ ok: true, status: 'cancelled', action: 'done', message: msg }) + '\n');
        break;
      }

      // 到达阈值 → 生成通知 + 打车联动
      if (position <= threshold && !notified) {
        notified = true;
        process.stdout.write(JSON.stringify({
          ok: true, status, position, estimated_min: estimatedMin,
          action: 'threshold_reached', tick: tickCount,
        }) + '\n');

        // 1. 调 LLM 生成通知
        let notifyMsg;
        try {
          const notif = await generateNotification({
            restaurant, queueNumber, tableTypeCn, position, estimatedMin, eventMessage,
          });
          notifyMsg = notif.message || `${restaurant} 快到你啦！前面还有 ${position} 桌。`;
        } catch (e) {
          notifyMsg = `🔔 ${restaurant} 快到你啦！前面还有 ${position} 桌${estimatedMin ? `，预计 ${estimatedMin} 分钟` : ''}。`;
          process.stdout.write(JSON.stringify({ ok: false, notify_error: e.message }) + '\n');
        }

        // 2. 打车联动决策
        let taxiInfo = '';
        if (resolvedUserLoc && restaurantAddr) {
          const taxiETA = await getTaxiETA(resolvedUserLoc, restaurantAddr);
          if (taxiETA != null) {
            const decision = shouldCallTaxi(position, tableTypeCn, taxiETA);
            process.stdout.write(JSON.stringify({
              ok: true, action: 'taxi_check',
              taxi_eta: taxiETA,
              remaining_wait: decision.remaining_wait,
              should_call: decision.call,
              diff: decision.diff,
            }) + '\n');

            if (decision.call) {
              taxiInfo = `\n\n🚕 打车过去约 ${taxiETA} 分钟，建议现在出发，刚好到号进店！需要帮你叫车吗？`;
            } else if (decision.diff > 0 && decision.diff <= 10) {
              taxiInfo = `\n\n🚕 打车过去约 ${taxiETA} 分钟，再等几分钟出发就来得及。`;
            }
          }
        }

        const fullMessage = notifyMsg + taxiInfo;
        writeHeartbeat(fullMessage);
        process.stdout.write(JSON.stringify({ ok: true, action: 'notified', message: notifyMsg, taxi_info: taxiInfo }) + '\n');
      }

      // 正常等待中
      process.stdout.write(JSON.stringify({
        ok: true, status, position, estimated_min: estimatedMin,
        action: 'waiting', tick: tickCount,
        ...(eventMessage && { event: eventMessage }),
      }) + '\n');

    } catch (e) {
      process.stderr.write(`[tick ${tickCount}] Error: ${e.message}\n`);
      process.stdout.write(JSON.stringify({ ok: false, error: e.message, action: 'retry', tick: tickCount }) + '\n');
    }

    await sleep(POLL_INTERVAL * 1000);
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

main().catch(e => { process.stderr.write(e.message + '\n'); process.exit(1); });
