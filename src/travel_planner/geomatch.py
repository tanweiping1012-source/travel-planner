"""Judge whether a geocoder actually found the place that was asked for.

Amap covers mainland China. Asked for somewhere outside it, the service does
not return nothing — it returns the closest Chinese name it can find, with
plausible coordinates and no indication that anything went wrong:

    东京        -> 广西壮族自治区贵港市平南县东京   (a village, not Tokyo)
    捷里别尔卡  -> 贵州省黔东南苗族侗族自治州丹寨县里别

Coordinates like these flow silently into route lookups, and every distance
and duration computed from them is confidently wrong while looking exactly
like a verified fact. An empty result would be far safer than this, so the
mismatch has to be detected here rather than trusted downstream.

Two signals are enough, and both are decidable from the response alone:
the query text is missing from the address that came back, or a destination
resolved to a village.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

#: Administrative levels too small to be a destination a traveller named.
#: A query for a city that lands on one of these matched something else.
SUSPICIOUS_LEVELS = frozenset({"村庄", "门牌号", "道路", "兴趣点", "生活服务"})

#: Levels that answer a destination query properly.
SETTLEMENT_LEVELS = frozenset({"国家", "省", "市", "区县", "开发区", "乡镇", "村庄"})


def _normalize(text: Any) -> str:
    return "".join(str(text or "").split()).lower()


def assess_geocode(
    query: str,
    formatted_address: Any,
    level: Any = None,
    candidate_count: int = 1,
    expect_settlement: bool = False,
) -> Dict[str, Any]:
    """Rate one geocode candidate against the query that produced it.

    ``expect_settlement`` marks a query that named a city or region rather
    than a specific venue; only then does a village-level hit count against
    the match, since a venue legitimately resolves to a small place.
    """

    address = _normalize(formatted_address)
    wanted = _normalize(query)
    level_text = str(level or "").strip()
    reasons = []

    name_in_address = bool(wanted) and wanted in address
    if not name_in_address:
        reasons.append(
            f"返回地址「{formatted_address}」中不包含查询词「{query}」，"
            "可能是模糊匹配到了无关地点"
        )

    level_suspicious = expect_settlement and level_text in SUSPICIOUS_LEVELS
    if level_suspicious:
        reasons.append(
            f"查询的是城市或地区，却匹配到「{level_text}」级别的地点"
        )

    if candidate_count > 1:
        reasons.append(f"存在 {candidate_count} 个同名候选，可能指向不同地方")

    if not name_in_address or level_suspicious:
        confidence = "LOW"
    elif candidate_count > 1:
        confidence = "MEDIUM"
    else:
        confidence = "HIGH"

    return {
        "confidence": confidence,
        "name_in_address": name_in_address,
        "level": level_text or None,
        "candidate_count": candidate_count,
        "matched_address": str(formatted_address or ""),
        "reasons": reasons,
    }


def coverage_hint(assessment: Optional[Dict[str, Any]]) -> Optional[str]:
    """Explain a low-confidence match in terms the traveller can act on."""

    if not assessment or assessment.get("confidence") != "LOW":
        return None
    return (
        "高德的地点数据以中国大陆为主。查询境外地点时它不会返回空结果，"
        "而是返回名称相近的国内地点，坐标看起来完全正常。"
        "请勿把这个结果当作已核实的地点，也不要用它计算车程。"
    )
