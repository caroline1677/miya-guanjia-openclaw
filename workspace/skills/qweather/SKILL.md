---
name: qweather
description: "QWeather real-world weather skill. 用于真实天气、国内城市天气、深圳各区天气、实时天气、未来三天天气、天气预警、下雨了吗、要不要带伞、出门/通勤/约会/户外活动建议。Use this QWeather skill instead of the bundled wttr.in weather skill for Chinese cities and real-world local planning."
homepage: https://dev.qweather.com/docs/api/
metadata:
  openclaw:
    emoji: "☔"
    requires:
      bins: ["node"]
---

# QWeather

Use this skill for real-world weather answers, especially Chinese-city weather and local planning. Prefer this skill over the bundled `weather` skill because this one calls QWeather directly with the configured `QWEATHER_KEY` and `QWEATHER_API_HOST`.

Do not use `mock-server` for real user weather answers. The mock server is only for sandbox demos and repeatable tests.

Need a city name, supported district name, QWeather location ID, or coordinates. Default location is Shenzhen (`101280601`) for the current Miya workspace, but the skill name and script are intentionally not Shenzhen-specific.

## Commands

Current weather:

```bash
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js now --location 深圳
```

3-day forecast:

```bash
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js forecast --location 深圳
```

Severe weather warnings:

```bash
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js warnings --location 深圳
```

All weather data:

```bash
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js all --location 深圳
```

Shenzhen district examples:

```bash
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js now --location 南山区
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js forecast --location 大鹏新区
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js all --location 深圳南山区
```

Supported Shenzhen districts are stored in `references/shenzhen_locations.json`: 福田区、罗湖区、南山区、盐田区、宝安区、龙岗区、龙华区、坪山区、光明区、大鹏新区.

Other locations can use a city name, QWeather location ID, or `lon,lat` coordinates:

```bash
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js now --location Guangzhou
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js now --location 101280101
node /home/node/.openclaw/workspace/skills/qweather/scripts/weather_qweather.js now --location 113.93,22.53
```

## Output

The script returns JSON. Use the structured fields to answer the user rather than hard-coding activity decisions in the script.

Current weather includes:

- `condition`
- `temp_c`
- `feels_like_c`
- `wind`
- `humidity`
- `precip_mm`
- `pressure_hpa`

Forecast includes `forecast_days` with daily conditions, high/low temperatures, precipitation, humidity, and UV index.

Warnings includes `warnings` with title, type, type_code, level, severity, valid times, and text.

## Notes

- `QWEATHER_KEY` and `QWEATHER_API_HOST` must be available in the process environment or in `~/.openclaw/.env`.
- The script sends API Key authentication with the `X-QW-Api-Key` header by default.
- Do not print or expose `QWEATHER_KEY`.
- For safety-critical decisions, verify against official local weather services.
