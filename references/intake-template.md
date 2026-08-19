# Travel Intake Template

Use this template to normalize a travel request. Do not require users to provide
JSON when their natural-language request already supplies the same information,
and do not ask for more than `validate-request` actually needs — see the split
below before using the plain-text template as an interview script.

## What actually blocks a run

`validate-request` only asks for three fields beyond the trip's own outline,
because each one changes the plan materially and has no safe default:

- `budget_scope` — a 2000 budget per person is twice a 2000 budget for the party
- `mobility.level` — decides which itineraries are possible at all
- `browser_approval` — consent, which cannot be assumed on someone's behalf

The trip's own outline is what a traveller states in one sentence: origin,
destination, start and end dates, traveler count, `budget_cny`, and `style`.
Together with the three fields above, that is the complete set that blocks.

## What is safely assumed

Everything else defaults if left unstated, and the default is reported back in
`assumptions` rather than silently applied:

| Field | Default when absent | Reading |
|---|---|---|
| `must_visit` | `[]` | No place is exempt from trade-offs |
| `excluded_places` | `[]` | Nothing to avoid |
| `mobility.max_walking_km_per_day` | 4 / 8 / 15 km, by `mobility.level` | The stated level already answers this |
| `mobility.accepts_high_altitude` | accepted | Re-asked only if a high-altitude core place appears |
| `mobility.accessibility_needs` | `[]` | No special needs |
| `tradeoff_priority` | `CORE_PLACES, COST, PACE, COMFORT` | Keep the core sights, then save money |
| `risk_tolerance.accepts_weather_dependent_core` | accepted | Re-asked only if it becomes decisive |

Do not ask for these up front. Asking turns a sentence a traveller would
actually say into a form — nobody volunteers that they have no excluded
places. A value the traveller *does* supply is still validated normally;
defaulting on absence never softens a check on presence.

## JSON template

Every field below is shown for reference, including the ones that default.
Only the fields listed under "What actually blocks a run" are mandatory.

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

Only the first block is worth asking as a batch when a request is genuinely
incomplete. The second block is optional detail a traveller may volunteer —
present it as "tell me if any of this applies," not as blanks to fill in, and
let the defaults above stand for whatever is left unsaid.

```text
使用 $travel-planner-mvp：
出发地：
核心目的地区域：
开始日期：
结束日期：
人数：
预算：人均 / 总计，人民币
旅行风格：
体力等级：低 / 中 / 高
小红书授权：匿名只读 / 允许我手动登录 / 禁止
OTA 授权：匿名只读 / 允许我手动登录 / 禁止
```

可选，不说则按合理默认处理：

```text
核心必去（不可删除）：
重要但可调整：
明确不去：
每日最多步行（不说则按体力等级默认 4/8/15 公里）：
是否接受 4000 米以上高海拔（不说则默认接受）：
无障碍、老人、儿童或健康限制（不说则默认无）：
冲突时优先级：核心地点 / 省钱 / 松弛 / 舒适（不说则默认此顺序）：
是否接受核心景观受天气影响（不说则默认接受）：
是否接受早班、夜班和中转：
每天最晚返回时间：
其他住宿、行李或饮食偏好：
```
