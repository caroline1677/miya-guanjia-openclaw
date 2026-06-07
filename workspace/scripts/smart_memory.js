// workspace/scripts/smart_memory.js
'use strict';
const { mergeProfile, appendDiary, readProfile } = require('./lib/memory.js');

const LONGCAT_BASE = 'https://api.longcat.chat/openai/v1';
const LONGCAT_KEY = 'YOUR_LONGCAT_KEY';

const EXTRACT_SYSTEM_PROMPT = `你是一个信息提取助手。从对话中提取用户偏好更新和日记条目。
返回严格的 JSON 对象，格式如下（没有的字段直接省略）：
{
  "profile_updates": {
    "diet.spicy": false,
    "budget.max": 150,
    "transport": "subway",
    "preferred_cuisines": ["日料"]
  },
  "diary_entry": "一句话总结"
}
只输出 JSON，不要其他文字，不要 markdown 代码块。`;

function parseArgs(args) {
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i].startsWith('--')) {
      const key = args[i].slice(2);
      // Handle multi-word values (everything until next --)
      const nextFlag = args.slice(i + 1).findIndex(a => a.startsWith('--'));
      const valueArgs = nextFlag === -1 ? args.slice(i + 1) : args.slice(i + 1, i + 1 + nextFlag);
      opts[key] = valueArgs.join(' ');
      i += valueArgs.length;
    }
  }
  return opts;
}

async function extractMemory(conversation) {
  const res = await fetch(`${LONGCAT_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${LONGCAT_KEY}`,
    },
    body: JSON.stringify({
      model: 'LongCat-2.0-Preview',
      messages: [
        { role: 'system', content: EXTRACT_SYSTEM_PROMPT },
        { role: 'user', content: `对话内容：\n${conversation}` },
      ],
      temperature: 0.1,
      max_tokens: 512,
    }),
  });
  if (!res.ok) throw new Error(`LLM API error: ${res.status}`);
  const data = await res.json();
  let content = (data.choices?.[0]?.message?.content || '{}').trim();
  // Strip markdown if present
  content = content.replace(/^```(?:json)?\n?/m, '').replace(/```$/m, '').trim();
  return JSON.parse(content);
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const userId = opts['user-id'];
  const conversation = opts.conversation;

  // --set-nickname: 直接写入昵称，不走 LLM
  if (userId && typeof opts['set-nickname'] !== 'undefined') {
    const nick = opts['set-nickname'] || '';
    mergeProfile(userId, { nickname: nick });
    process.stdout.write(JSON.stringify({ ok: true, nickname: nick }) + '\n');
    return;
  }

  if (!userId || !conversation) {
    process.stderr.write('用法: smart_memory.js --user-id <id> --conversation "<text>"\n');
    process.exit(1);
  }

  let extracted;
  try {
    extracted = await extractMemory(conversation);
  } catch (e) {
    process.stderr.write(`LLM extraction failed: ${e.message}\n`);
    // Graceful fallback: just write a diary entry without profile updates
    appendDiary(userId, `[对话记录] ${conversation.slice(0, 100)}`);
    process.stdout.write(JSON.stringify({ ok: true, updates: {}, diary_entry: '(LLM不可用，原始记录已保存)', fallback: true }) + '\n');
    return;
  }

  let updates = {};
  if (extracted.profile_updates && Object.keys(extracted.profile_updates).length > 0) {
    mergeProfile(userId, extracted.profile_updates);
    updates = extracted.profile_updates;
  }

  if (extracted.diary_entry) {
    appendDiary(userId, extracted.diary_entry);
  }

  process.stdout.write(JSON.stringify({
    ok: true,
    updates,
    diary_entry: extracted.diary_entry || '',
  }, null, 2) + '\n');
}

main().catch(e => { process.stderr.write(e.message + '\n'); process.exit(1); });
