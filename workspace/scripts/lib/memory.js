// workspace/scripts/lib/memory.js
'use strict';
const fs = require('fs');
const path = require('path');

const WORKSPACE = process.env.WORKSPACE_PATH || '/home/node/.openclaw/workspace';

function userDir(userId) {
  return path.join(WORKSPACE, 'users', userId);
}

function ensureUserDir(userId) {
  const dir = userDir(userId);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    const tpl = path.join(WORKSPACE, 'users', '_template');
    if (fs.existsSync(tpl)) {
      fs.copyFileSync(path.join(tpl, 'profile.json'), path.join(dir, 'profile.json'));
      fs.copyFileSync(path.join(tpl, 'tasks.json'), path.join(dir, 'tasks.json'));
    } else {
      // Create defaults if no template
      fs.writeFileSync(path.join(dir, 'profile.json'), JSON.stringify({
        public: { diet: { spicy: true, allergies: [] }, budget: { max: 300 }, transport: 'any', location_home: '深圳', preferred_cuisines: [] },
        private: { liked_places: [], disliked_places: [], notes: '' }
      }, null, 2), 'utf-8');
      fs.writeFileSync(path.join(dir, 'tasks.json'), '[]', 'utf-8');
    }
  }
  return dir;
}

function readProfile(userId) {
  ensureUserDir(userId);
  const file = path.join(userDir(userId), 'profile.json');
  return JSON.parse(fs.readFileSync(file, 'utf-8'));
}

function writeProfile(userId, profile) {
  ensureUserDir(userId);
  fs.writeFileSync(
    path.join(userDir(userId), 'profile.json'),
    JSON.stringify(profile, null, 2),
    'utf-8'
  );
}

/**
 * Deep merge: dot-path updates into profile.public or profile.private.
 * e.g. mergeProfile('u1', { 'diet.spicy': false, 'budget.max': 150 })
 */
function mergeProfile(userId, updates) {
  const profile = readProfile(userId);
  for (const [dotPath, value] of Object.entries(updates)) {
    const parts = dotPath.split('.');
    // Try public first, then private
    let merged = false;
    for (const section of ['public', 'private']) {
      let cur = profile[section];
      let ok = true;
      for (const p of parts.slice(0, -1)) {
        if (cur && typeof cur === 'object' && p in cur) {
          cur = cur[p];
        } else { ok = false; break; }
      }
      if (ok && cur && typeof cur === 'object') {
        const lastKey = parts[parts.length - 1];
        if (Array.isArray(cur[lastKey]) && Array.isArray(value)) {
          // Merge arrays (e.g. preferred_cuisines)
          cur[lastKey] = [...new Set([...cur[lastKey], ...value])];
        } else {
          cur[lastKey] = value;
        }
        merged = true;
        break;
      }
    }
    if (!merged) {
      // Add to public if path not found
      const lastKey = parts[parts.length - 1];
      profile.public[lastKey] = value;
    }
  }
  writeProfile(userId, profile);
  return profile;
}

function readTasks(userId) {
  ensureUserDir(userId);
  const file = path.join(userDir(userId), 'tasks.json');
  return JSON.parse(fs.readFileSync(file, 'utf-8'));
}

function writeTasks(userId, tasks) {
  ensureUserDir(userId);
  fs.writeFileSync(
    path.join(userDir(userId), 'tasks.json'),
    JSON.stringify(tasks, null, 2),
    'utf-8'
  );
}

function appendDiary(userId, entry) {
  ensureUserDir(userId);
  const memDir = path.join(userDir(userId), 'memory');
  if (!fs.existsSync(memDir)) fs.mkdirSync(memDir, { recursive: true });
  const today = new Date().toISOString().slice(0, 10);
  const file = path.join(memDir, `${today}.md`);
  const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  fs.appendFileSync(file, `- ${timestamp} ${entry}\n`, 'utf-8');
}

function readRecentDiary(userId, days = 3) {
  const memDir = path.join(userDir(userId), 'memory');
  if (!fs.existsSync(memDir)) return '';
  const entries = [];
  for (let i = 0; i < days; i++) {
    const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    const file = path.join(memDir, `${d}.md`);
    if (fs.existsSync(file)) {
      entries.push(`## ${d}\n` + fs.readFileSync(file, 'utf-8'));
    }
  }
  return entries.join('\n');
}

/** Group: aggregate all members' public preferences */
function groupPublicProfiles(groupId) {
  const groupDir = path.join(WORKSPACE, 'groups', groupId);
  const membersFile = path.join(groupDir, 'members.json');
  if (!fs.existsSync(membersFile)) return [];
  const members = JSON.parse(fs.readFileSync(membersFile, 'utf-8'));
  return members.map(uid => {
    try {
      return { userId: uid, public: readProfile(uid).public };
    } catch {
      return { userId: uid, public: {} };
    }
  });
}

module.exports = {
  readProfile, writeProfile, mergeProfile,
  readTasks, writeTasks,
  appendDiary, readRecentDiary,
  groupPublicProfiles,
  ensureUserDir,
  WORKSPACE,
};
