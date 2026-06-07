// workspace/scripts/restaurant_monitor.js
'use strict';
const { readTasks, writeTasks, appendDiary, readProfile } = require('./lib/memory.js');

const MOCK_SERVER = process.env.MOCK_SERVER_URL || 'http://mock-server:5001';

// ─── API calls ────────────────────────────────────────────────────────────

async function checkQueue(restaurant) {
  const res = await fetch(`${MOCK_SERVER}/restaurant/${encodeURIComponent(restaurant)}/queue`);
  if (!res.ok) throw new Error(`Mock server error ${res.status}: ${await res.text()}`);
  return res.json();
}

async function takeNumber({ restaurant, userId, partySize, tableType }) {
  const body = { user_id: userId, party_size: Number(partySize) };
  if (tableType) body.table_type = tableType;
  const res = await fetch(
    `${MOCK_SERVER}/restaurant/${encodeURIComponent(restaurant)}/queue/take`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
  if (!res.ok) throw new Error(`Take number error ${res.status}: ${await res.text()}`);
  return res.json();
}

async function checkNumber(restaurant, queueNumber) {
  const res = await fetch(
    `${MOCK_SERVER}/restaurant/${encodeURIComponent(restaurant)}/queue/${encodeURIComponent(queueNumber)}`
  );
  if (!res.ok) throw new Error(`Status check error ${res.status}: ${await res.text()}`);
  const data = await res.json();
  // 后端正常返回无 ok 字段，错误返回 {ok:false, error:"..."}
  if (data.error) throw new Error(data.error);
  return data;
}

async function generateNotification({ restaurant, queueNumber, tableTypeCn, position, estimatedMin, eventMessage, userPrefs }) {
  const body = {
    restaurant,
    queue_number: queueNumber,
    table_type_cn: tableTypeCn,
    position,
    estimated_min: estimatedMin,
    ...(eventMessage && { event_message: eventMessage }),
    ...(userPrefs && { user_prefs: userPrefs }),
  };
  const res = await fetch(
    `${MOCK_SERVER}/notification/queue`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  );
  if (!res.ok) throw new Error(`Notification error ${res.status}: ${await res.text()}`);
  return res.json();
}

// ─── Monitor registration ──────────────────────────────────────────────────

async function registerMonitor({ userId, restaurant, threshold, message, queueNumber, tableType }) {
  const tasks = readTasks(userId);
  const taskId = `task_${Date.now()}`;
  tasks.push({
    id: taskId,
    type: 'restaurant_monitor',
    params: {
      restaurant,
      threshold: Number(threshold),
      ...(queueNumber && { queue_number: queueNumber }),
      ...(tableType  && { table_type: tableType }),
    },
    notify_message: message || `${restaurant} 快到你了`,
    created_at: new Date().toISOString(),
    status: 'active',
  });
  writeTasks(userId, tasks);
  const note = queueNumber
    ? `注册排队监控：${restaurant}，号码 ${queueNumber}，阈值 ${threshold} 桌`
    : `注册排队监控：${restaurant}，阈值 ${threshold} 桌`;
  appendDiary(userId, note);
  return { ok: true, task_id: taskId };
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
  const cmd  = argv[0];
  const opts = parseArgs(argv.slice(1));

  if (cmd === 'check') {
    const data = await checkQueue(opts.restaurant || '海底捞福田');
    process.stdout.write(JSON.stringify(data, null, 2) + '\n');

  } else if (cmd === 'take') {
    const missing = ['user-id', 'restaurant', 'party-size'].filter(k => !opts[k]);
    if (missing.length) { process.stderr.write(`缺少参数: --${missing.join(', --')}\n`); process.exit(1); }
    const result = await takeNumber({
      restaurant: opts.restaurant,
      userId: opts['user-id'],
      partySize: opts['party-size'],
      tableType: opts['table-type'],
    });
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');

  } else if (cmd === 'status') {
    const missing = ['restaurant', 'number'].filter(k => !opts[k]);
    if (missing.length) { process.stderr.write(`缺少参数: --${missing.join(', --')}\n`); process.exit(1); }
    const data = await checkNumber(opts.restaurant, opts.number);
    process.stdout.write(JSON.stringify(data, null, 2) + '\n');

  } else if (cmd === 'notify') {
    const missing = ['restaurant', 'number', 'position', 'estimated-min'].filter(k => !opts[k]);
    if (missing.length) { process.stderr.write(`缺少参数: --${missing.join(', --')}\n`); process.exit(1); }
    const data = await generateNotification({
      restaurant: opts.restaurant,
      queueNumber: opts.number,
      tableTypeCn: opts['table-type-cn'] || '中桌',
      position: Number(opts.position),
      estimatedMin: Number(opts['estimated-min']),
      eventMessage: opts['event-message'],
      userPrefs: opts['user-prefs'],
    });
    process.stdout.write(JSON.stringify(data, null, 2) + '\n');

  } else if (cmd === 'register') {
    const missing = ['user-id', 'restaurant', 'threshold'].filter(k => !opts[k]);
    if (missing.length) { process.stderr.write(`缺少参数: --${missing.join(', --')}\n`); process.exit(1); }
    const result = await registerMonitor({
      userId: opts['user-id'],
      restaurant: opts.restaurant,
      threshold: opts.threshold,
      message: opts.message,
      queueNumber: opts['queue-number'],
      tableType: opts['table-type'],
    });
    process.stdout.write(JSON.stringify(result) + '\n');

  } else {
    process.stderr.write(
      'Usage: restaurant_monitor.js <cmd> [options]\n' +
      '  check    --restaurant <name>\n' +
      '  take     --user-id <id> --restaurant <name> --party-size <n> [--table-type small|medium|large]\n' +
      '  status   --restaurant <name> --number <queue_number>\n' +
      '  notify   --restaurant <name> --number <qn> --position <n> --estimated-min <n> [--table-type-cn <cn>] [--event-message <msg>] [--user-prefs <prefs>]\n' +
      '  register --user-id <id> --restaurant <name> --threshold <n> [--queue-number <qn>] [--message <msg>]\n'
    );
    process.exit(1);
  }
}

main().catch(e => { process.stderr.write(e.message + '\n'); process.exit(1); });
