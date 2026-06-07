#!/usr/bin/env node
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

loadDotEnv();

const API_HOST = normalizeHost(process.env.QWEATHER_API_HOST || '');
const BASE_URL = process.env.QWEATHER_BASE_URL || (API_HOST ? `https://${API_HOST}/v7` : 'https://devapi.qweather.com/v7');
const GEO_URL = process.env.QWEATHER_GEO_URL || (API_HOST ? `https://${API_HOST}/geo/v2` : 'https://geoapi.qweather.com/v2');
const ALERT_URL = process.env.QWEATHER_ALERT_URL || (API_HOST ? `https://${API_HOST}` : 'https://devapi.qweather.com');
const AUTH_MODE = process.env.QWEATHER_AUTH_MODE || 'header';
const DEFAULT_LOCATION = process.env.QWEATHER_DEFAULT_LOCATION || '101280601';
const REFERENCE_LOCATIONS = loadReferenceLocations();

function loadDotEnv() {
  const candidates = [
    '/home/node/.openclaw/.env',
    '/home/ubuntu/.openclaw/.env',
    path.join(os.homedir(), '.openclaw', '.env'),
  ];

  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;
    const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      if (!match) continue;
      const key = match[1];
      let value = match[2].trim();
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      if (!process.env[key]) process.env[key] = value;
    }
  }
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const command = args[0] && !args[0].startsWith('--') ? args.shift() : 'now';
  const options = {};

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--location' || arg === '-l') {
      options.location = args[++i];
    } else if (arg === '--lang') {
      options.lang = args[++i];
    } else if (arg === '--unit') {
      options.unit = args[++i];
    } else if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return { command, options };
}

function usage() {
  return `Usage:
  weather_qweather.js now [--location Shenzhen|101280601|lon,lat]
  weather_qweather.js forecast [--location Shenzhen|101280601|lon,lat]
  weather_qweather.js warnings [--location Shenzhen|101280601|lon,lat]
  weather_qweather.js all [--location Shenzhen|101280601|lon,lat]

Environment:
  QWEATHER_KEY is read from the process environment or ~/.openclaw/.env.
  QWEATHER_API_HOST is recommended for current QWeather credentials.
`;
}

function normalizeHost(host) {
  return String(host || '').trim().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
}

function requireKey() {
  const key = process.env.QWEATHER_KEY;
  if (!key) {
    throw new Error('QWEATHER_KEY is not configured. Add it to ~/.openclaw/.env or the process environment.');
  }
  return key;
}

function looksResolvedLocation(location) {
  return /^\d{6,}$/.test(location) || /^-?\d+(\.\d+)?,-?\d+(\.\d+)?$/.test(location);
}

function parseLonLat(value) {
  const match = String(value || '').match(/^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$/);
  if (!match) return null;
  return { lon: match[1], lat: match[2] };
}

async function requestJson(baseUrl, endpoint, params) {
  const url = new URL(`${baseUrl}${endpoint}`);
  const headers = { accept: 'application/json' };
  if (AUTH_MODE !== 'query') headers['X-QW-Api-Key'] = params.key;

  Object.entries(params).forEach(([key, value]) => {
    if (key === 'key' && AUTH_MODE !== 'query') return;
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  });

  const res = await fetch(url, { headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(`QWeather HTTP ${res.status}`);
  }
  if (data.code && data.code !== '200' && data.code !== '204') {
    throw new Error(`QWeather API code ${data.code}`);
  }
  return data;
}

async function resolveLocation(input, key, lang) {
  const raw = input || DEFAULT_LOCATION;
  const aliases = buildLocationAliases(REFERENCE_LOCATIONS);
  const normalized = String(raw).trim();
  const alias = aliases.get(aliasKey(normalized));
  if (alias) return aliasLocation(alias, raw);

  const lonLat = parseLonLat(normalized);
  if (lonLat) return { id: normalized, name: normalized, input: raw, ...lonLat };

  if (/^\d{6,}$/.test(normalized)) {
    return { id: normalized, name: normalized, input: raw };
  }

  const data = await requestJson(GEO_URL, '/city/lookup', {
    location: normalized,
    key,
    lang,
    number: '1',
  });
  const match = data.location && data.location[0];
  if (!match) throw new Error(`No QWeather location found for: ${raw}`);
  return {
    id: match.id,
    name: match.name,
    adm1: match.adm1,
    adm2: match.adm2,
    country: match.country,
    lat: match.lat,
    lon: match.lon,
    input: raw,
  };
}

function loadReferenceLocations() {
  const files = [
    path.join(__dirname, '..', 'references', 'shenzhen_locations.json'),
  ];
  const locations = [];

  for (const file of files) {
    if (!fs.existsSync(file)) continue;
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (Array.isArray(data.locations)) locations.push(...data.locations);
  }

  return locations;
}

function buildLocationAliases(locations) {
  const aliases = new Map();
  for (const location of locations) {
    const names = new Set([location.id, location.name, ...(location.aliases || [])].filter(Boolean));
    for (const name of names) aliases.set(aliasKey(name), location);
    for (const scope of location.scopes || []) {
      for (const name of names) aliases.set(aliasKey(`${scope}${name}`), location);
    }
  }
  return aliases;
}

function aliasKey(value) {
  return String(value || '').trim().toLowerCase();
}

function aliasLocation(location, input) {
  return {
    id: location.id,
    name: location.name,
    lat: location.lat,
    lon: location.lon,
    input,
  };
}

async function getNow(location, key, lang, unit) {
  const data = await requestJson(BASE_URL, '/weather/now', { location: location.id, key, lang, unit });
  const now = data.now || {};
  return {
    source: 'qweather',
    location,
    observed_at: now.obsTime || null,
    condition: now.text || '',
    temp_c: numberOrNull(now.temp),
    feels_like_c: numberOrNull(now.feelsLike),
    wind: compactWind(now),
    wind_dir: now.windDir || '',
    wind_scale: now.windScale || '',
    humidity: numberOrNull(now.humidity),
    precip_mm: numberOrNull(now.precip),
    pressure_hpa: numberOrNull(now.pressure),
    cloud: numberOrNull(now.cloud),
    dew_c: numberOrNull(now.dew),
  };
}

async function getForecast(location, key, lang, unit) {
  const data = await requestJson(BASE_URL, '/weather/3d', { location: location.id, key, lang, unit });
  return {
    source: 'qweather',
    location,
    forecast_days: (data.daily || []).map((day) => ({
      date: day.fxDate,
      sunrise: day.sunrise || null,
      sunset: day.sunset || null,
      day_condition: day.textDay || '',
      night_condition: day.textNight || '',
      max_temp_c: numberOrNull(day.tempMax),
      min_temp_c: numberOrNull(day.tempMin),
      wind_day: compactWind({ windDir: day.windDirDay, windScale: day.windScaleDay }),
      wind_night: compactWind({ windDir: day.windDirNight, windScale: day.windScaleNight }),
      humidity: numberOrNull(day.humidity),
      precip_mm: numberOrNull(day.precip),
      uv_index: numberOrNull(day.uvIndex),
    })),
  };
}

async function getWarnings(location, key, lang) {
  const warnings = [];
  const errors = [];

  if (location.lat && location.lon) {
    try {
      const data = await requestJson(ALERT_URL, `/weatheralert/v1/current/${location.lat}/${location.lon}`, {
        key,
        lang,
      });
      warnings.push(...normalizeWarnings(data.warning || data.alerts || data.data || []));
      return { source: 'qweather', endpoint: 'weatheralert/v1/current', location, warnings };
    } catch (error) {
      errors.push(`weatheralert/v1/current: ${error.message}`);
    }
  }

  try {
    const data = await requestJson(BASE_URL, '/warning/now', { location: location.id, key, lang });
    warnings.push(...normalizeWarnings(data.warning || []));
    return { source: 'qweather', endpoint: 'v7/warning/now', location, warnings };
  } catch (error) {
    errors.push(`v7/warning/now: ${error.message}`);
  }

  throw new Error(`QWeather warnings unavailable (${errors.join('; ')})`);
}

function normalizeWarnings(items) {
  return items.map((warning) => {
    return {
      id: warning.id || warning.warningId || '',
      sender: warning.sender || '',
      title: warning.title || warning.name || '',
      type: warningTypeName(warning.typeName) || warningTypeName(warning.eventType) || warningTypeName(warning.type),
      type_code: warningTypeCode(warning.typeName) || warningTypeCode(warning.eventType) || warningTypeCode(warning.type) || warning.typeCode || '',
      level: warning.level || warning.severityColor || '',
      severity: warning.severity || '',
      start_time: warning.startTime || warning.startTimeLocal || null,
      end_time: warning.endTime || warning.endTimeLocal || null,
      text: warning.text || warning.description || '',
    };
  });
}

function warningTypeName(value) {
  if (!value) return '';
  if (typeof value === 'object') return value.name || '';
  return String(value);
}

function warningTypeCode(value) {
  if (!value || typeof value !== 'object') return '';
  return value.code || '';
}

function compactWind(data) {
  const dir = data.windDir || '';
  const scale = data.windScale || '';
  return dir && scale ? `${dir}${scale}\u7ea7` : (dir || scale || '');
}

function numberOrNull(value) {
  if (value === undefined || value === null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

async function main() {
  const { command, options } = parseArgs(process.argv);
  if (options.help || command === 'help') {
    process.stdout.write(usage());
    return;
  }

  const key = requireKey();
  const lang = options.lang || 'zh';
  const unit = options.unit || 'm';
  const location = await resolveLocation(options.location, key, lang);

  let result;
  if (command === 'now') {
    result = await getNow(location, key, lang, unit);
  } else if (command === 'forecast') {
    result = await getForecast(location, key, lang, unit);
  } else if (command === 'warnings') {
    result = await getWarnings(location, key, lang);
  } else if (command === 'all') {
    const [now, forecast, warnings] = await Promise.all([
      getNow(location, key, lang, unit),
      getForecast(location, key, lang, unit),
      getWarnings(location, key, lang).catch((error) => ({
        source: 'qweather',
        location,
        warnings: [],
        warning_error: error.message,
      })),
    ]);
    result = {
      source: 'qweather',
      location,
      now,
      forecast_days: forecast.forecast_days,
      warnings: warnings.warnings,
      warning_error: warnings.warning_error,
    };
  } else {
    throw new Error(`Unknown command: ${command}`);
  }

  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
});
