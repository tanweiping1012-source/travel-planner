# Travel Intake Template

Use this template to normalize a travel request. Do not require users to provide
JSON when their natural-language request already supplies the same information.

## Required information

- Origin and destination region
- Start and end dates
- Number of travelers
- Budget and whether it is per-person or party-total
- Travel style
- Required places with `CORE`, `IMPORTANT`, or `OPTIONAL` priority
- Excluded places
- Mobility level, walking limit, altitude acceptance, and accessibility needs
- Trade-off order among core places, cost, pace, and comfort
- Acceptance of weather-dependent core experiences
- Browser approval for Xiaohongshu and OTA research
- Relevant departure, return, and transfer constraints

## JSON template

```json
{
  "origin": "广州",
  "destination": "桂林与阳朔",
  "start_date": "2027-04-10",
  "end_date": "2027-04-13",
  "travelers": 2,
  "budget_cny": 3500,
  "budget_scope": "PER_PERSON",
  "style": "balanced",
  "must_visit": [
    {
      "name": "龙脊梯田",
      "priority": "CORE"
    }
  ],
  "excluded_places": [],
  "mobility": {
    "level": "MODERATE",
    "max_walking_km_per_day": 8,
    "accepts_high_altitude": true,
    "accessibility_needs": []
  },
  "tradeoff_priority": [
    "CORE_PLACES",
    "COST",
    "PACE",
    "COMFORT"
  ],
  "risk_tolerance": {
    "accepts_weather_dependent_core": true
  },
  "browser_approval": {
    "xiaohongshu": "ALLOW_MANUAL_LOGIN",
    "ota": "ANONYMOUS_ONLY"
  },
  "transport_preferences": {
    "accepts_early_departure": true,
    "accepts_overnight_transport": false,
    "accepts_transfers": true
  },
  "latest_return_time": null
}
```

## Field values

| Field | Values | Meaning |
|---|---|---|
| `budget_scope` | `PER_PERSON` / `PARTY_TOTAL` | Per-person or whole-party budget |
| `must_visit[].priority` | `CORE` / `IMPORTANT` / `OPTIONAL` | Removal priority during route optimization |
| `mobility.level` | `LOW` / `MODERATE` / `HIGH` | Physical intensity tolerance |
| `tradeoff_priority` | `CORE_PLACES`, `COST`, `PACE`, `COMFORT` | Conflict resolution order |
| `browser_approval.*` | `ANONYMOUS_ONLY` / `ALLOW_MANUAL_LOGIN` / `DENY` | Browser access boundary |

`CORE` never overrides safety, law, closure, physical limits, or actual access.

## Plain-text template

```text
使用 $travel-planner-mvp：
出发地：
核心目的地区域：
开始日期：
结束日期：
人数：
预算：人均 / 总计，人民币
旅行风格：
核心必去（不可删除）：
重要但可调整：
明确不去：
体力等级：低 / 中 / 高
每日最多步行：
是否接受 4000 米以上高海拔：
无障碍、老人、儿童或健康限制：
冲突时优先级：核心地点 / 省钱 / 松弛 / 舒适
是否接受核心景观受天气影响：
是否接受早班、夜班和中转：
每天最晚返回时间：
小红书授权：匿名只读 / 允许我手动登录 / 禁止
OTA 授权：匿名只读 / 允许我手动登录 / 禁止
其他住宿、行李或饮食偏好：
```
