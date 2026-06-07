# AMap POI Type Codes

Common categories used by Miya/OpenClaw:

| Category | AMap types | Meaning |
| --- | --- | --- |
| restaurant | 050000 | 餐饮服务 |
| shopping | 060000 | 购物服务 / 商场 |
| life | 070000 | 生活服务 |
| entertainment | 080000 | 体育休闲/娱乐场所，电影院可用更具体关键词过滤 |
| cinema | 080000 | 电影院/娱乐，配合 keywords=电影院 |
| hotel | 100000 | 住宿服务，酒店、宾馆、民宿 |
| scenic | 110000 | 风景名胜，景区、公园、地质公园等 |
| transport | 150000 | 交通设施服务，火车站、地铁站、公交站等 |
| medical | 090000 | 医疗保健服务 |
| all | empty | 不限制 types，仅按关键词搜索 |

Prefer a broad type plus a specific keyword. Examples:

- 酒店/民宿: `--category hotel --keywords "大鹏半岛民宿"`
- 餐厅: `--category restaurant --keywords "大鹏半岛海鲜"`
- 景点: `--category scenic --keywords "大鹏半岛景点"`
- 商场: `--category shopping --keywords "深圳商场"`
- 电影院: `--category cinema --keywords "电影院"`

Use `citylimit=true` by default for city-specific user requests to avoid irrelevant cross-city results.
