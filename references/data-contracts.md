# Data Contracts

## Trip Request

Use the complete intake contract before research:

```json
{
  "origin": "广州",
  "destination": "桂林与阳朔",
  "origin_city": "广州",
  "destination_city": "桂林",
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
  "route_modes": ["transit", "driving"],
  "transport_preferences": {
    "accepts_early_departure": true,
    "accepts_overnight_transport": false,
    "accepts_transfers": true
  },
  "latest_return_time": null,
  "discovery": {
    "radius_meters": 10000,
    "types": "110000|140000",
    "limit": 15
  }
}
```

Allowed values:

```text
budget_scope: PER_PERSON | PARTY_TOTAL
must_visit[].priority: CORE | IMPORTANT | OPTIONAL
mobility.level: LOW | MODERATE | HIGH
tradeoff_priority[]: CORE_PLACES | COST | PACE | COMFORT
browser_approval.*: ANONYMOUS_ONLY | ALLOW_MANUAL_LOGIN | DENY
```

Run `validate-request` before source research. A `CORE` place is non-removable;
candidate repair may change optional places, cost, pace, or comfort according to
`tradeoff_priority`. Safety and legal access remain absolute constraints.

`browser_approval` is provider-specific:

- `ANONYMOUS_ONLY`: read public pages and stop at any login requirement.
- `ALLOW_MANUAL_LOGIN`: read public pages first; when login is required, stop
  and let the user log in manually.
- `DENY`: do not open that provider.

The validator returns:

```json
{
  "status": "READY",
  "missing_fields": [],
  "errors": [],
  "conflicts": [],
  "assumptions": [],
  "questions_required": []
}
```

Ask no intake questions when status is `READY`. For `NEEDS_CLARIFICATION`, ask
once for all returned missing fields and conflicts. For `INVALID`, request
corrections before research.

## Source Metadata

Attach this object to every external result:

```json
{
  "provider": "amap",
  "connector": "amap-web-api",
  "connector_type": "official_api",
  "channel": "api",
  "login_state": "NOT_APPLICABLE",
  "checked_at": "2026-08-10T10:00:00Z",
  "url": null,
  "confidence": "HIGH"
}
```

Allowed connector types:

```text
official_api
community_mcp
browser
web_search_fallback
user_provided
```

## Rail Option

```json
{
  "mode": "rail",
  "train_code": "G2",
  "origin_station": "广州南",
  "destination_station": "桂林北",
  "departure": "2027-04-10T07:00:00+08:00",
  "arrival": "2027-04-10T09:45:00+08:00",
  "duration_minutes": 165,
  "seats": {
    "second_class": "有",
    "first_class": "3"
  },
  "prices_cny": {
    "second_class": 164,
    "first_class": 263
  },
  "source": {
    "provider": "12306",
    "connector": "drfccv/mcp-server-12306",
    "connector_type": "community_mcp",
    "official_connector": false,
    "checked_at": "2027-04-01T10:00:00+08:00"
  }
}
```

## Flight Offer

```json
{
  "mode": "flight",
  "offer_id": "ctrip-web-result-1",
  "outbound": {
    "carrier": "Example Air",
    "flight_number": "EX123",
    "origin_airport": "CAN",
    "destination_airport": "KWL",
    "departure": "2027-04-10T07:50:00+08:00",
    "arrival": "2027-04-10T09:10:00+08:00",
    "duration_minutes": 80,
    "stops": 0
  },
  "return": null,
  "displayed_total_price": 620,
  "currency": "CNY",
  "baggage_visibility": "UNKNOWN",
  "final_price_guaranteed": false,
  "source": {
    "provider": "ctrip",
    "connector": "browser-adapter",
    "connector_type": "browser",
    "channel": "ctrip_web",
    "login_state": "PUBLIC_READY",
    "page_visible_only": true,
    "checked_at": "2027-04-01T18:00:00+08:00",
    "url": "https://..."
  }
}
```

## Social Research Result

Browser results must be normalized before they influence a plan:

```json
{
  "title": "杭州三日游路线",
  "url": "https://www.xiaohongshu.com/...",
  "author_display_name": "visible author name",
  "visible_body": "Visible note text",
  "published_at": null,
  "checked_at": "2026-08-10T10:00:00Z",
  "extracted_place_names": ["西湖", "灵隐寺"],
  "claims": [
    {
      "type": "QUEUE",
      "text": "Arrive before 08:00 to avoid queues",
      "confidence": "MEDIUM"
    }
  ],
  "place_evidence": [
    {
      "name": "西湖",
      "features": ["城市湖泊景观", "白堤与断桥步行线"],
      "why_visit": ["适合低强度慢游和日落散步"],
      "suggested_duration_minutes": 180,
      "best_time": "清晨或傍晚",
      "physical_load": "低至中等",
      "caveats": ["节假日断桥区域拥挤"]
    }
  ],
  "source": {
    "provider": "xiaohongshu",
    "connector": "browser-adapter",
    "connector_type": "browser",
    "channel": "xiaohongshu_web",
    "login_state": "CONNECTED",
    "page_visible_only": true
  }
}
```

Social notes are experience evidence, not authoritative facts. Validate every
place name, coordinate, route, opening time, and price with a stronger source.

`place_evidence` is mandatory for notes that influence the route. Do not ask
`compile-research` to infer structured facts from arbitrary prose.

## Destination Brief

Output of `compile-research`:

```json
{
  "status": "VALID",
  "destination": "杭州",
  "travel_style": "relaxed",
  "attraction_cards": [
    {
      "name": "西湖",
      "features": ["城市湖泊景观", "白堤与断桥步行线"],
      "why_visit": ["适合低强度慢游和日落散步"],
      "suggested_duration_minutes": 180,
      "best_time": ["清晨或傍晚"],
      "physical_load": ["低至中等"],
      "caveats": ["节假日断桥区域拥挤"],
      "source_refs": [
        {
          "title": "杭州松弛旅行",
          "url": "https://www.xiaohongshu.com/...",
          "published_at": "2026-06-01",
          "checked_at": "2026-08-10T10:00:00+08:00"
        }
      ],
      "evidence_count": 1,
      "missing_fields": []
    }
  ],
  "errors": [],
  "warnings": []
}
```

Cards with missing features, reason, duration, or sources are incomplete and
must be enriched before route generation.

## Connector Status

```json
{
  "provider": "xiaohongshu",
  "status": "LOGIN_REQUIRED",
  "checked_at": "2026-08-10T10:00:00Z",
  "message": "Manual login is required before search"
}
```

Allowed statuses:

```text
READY
PUBLIC_READY
LOGIN_REQUIRED
CONNECTED
EXPIRED
DEGRADED
BLOCKED
UNAVAILABLE
```

## Final Plan Content

`validate-plan` expects:

```json
{
  "name": "balanced",
  "days": [
    {
      "date": "2026-10-01",
      "theme": "西湖慢游",
      "activities": [
        {
          "id": "west-lake",
          "type": "ATTRACTION",
          "name": "西湖",
          "description": "沿白堤和湖滨慢走，观察湖光与城市边界。",
          "features": ["城市湖泊景观", "白堤与断桥步行线"],
          "why_visit": ["适合低强度慢游和日落散步"],
          "suggested_duration_minutes": 180,
          "best_time": "傍晚",
          "physical_load": "低至中等",
          "caveats": ["断桥区域可能拥挤"],
          "source_refs": ["xhs-note-1"]
        }
      ]
    }
  ],
  "segments": [],
  "flight_offers": [],
  "sources": [
    {
      "id": "xhs-note-1",
      "url": "https://www.xiaohongshu.com/...",
      "checked_at": "2026-08-10T10:00:00+08:00"
    }
  ]
}
```

Every major attraction must explain its distinctive features and inclusion
reason. A plan containing only transport activities is invalid.

## Itinerary for Feasibility Evaluation

```json
{
  "budget_cny": 1000,
  "constraints": {
    "max_daily_minutes": 720,
    "max_walking_km_per_day": 10,
    "default_transfer_buffer_minutes": 20,
    "stale_after_hours": 24
  },
  "activities": [
    {
      "id": "place-1",
      "name": "西湖",
      "type": "ATTRACTION",
      "start": "2026-10-01T09:00:00+08:00",
      "end": "2026-10-01T11:30:00+08:00",
      "opening_time": "00:00",
      "closing_time": "23:59",
      "estimated_cost": 0,
      "walking_km": 4,
      "source_checked_at": "2026-10-01T00:00:00+08:00"
    }
  ],
  "segments": [
    {
      "from_id": "place-1",
      "to_id": "place-2",
      "duration_minutes": 40,
      "buffer_minutes": 20,
      "estimated_cost": 6
    }
  ]
}
```

All datetimes must contain a timezone offset. Dynamic data must contain
`source_checked_at`.
