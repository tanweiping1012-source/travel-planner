"""Timezone-aware datetime handling shared by the checking modules.

Everything this Skill compares in time — an opening hour against an arrival, a
lookup timestamp against the present — is meaningless without an offset, so
both parsing and the caller-supplied clock are guarded here rather than in each
module. Nothing infers a timezone: guessing one is what produced the
opening-hours false positives this code now exists to prevent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_datetime(value: Any, field: str = "datetime") -> datetime:
    """Parse an ISO 8601 string that must carry a UTC offset.

    ``Z`` is accepted as an alias for ``+00:00``; Python's parser only learned
    it in 3.11 and this code supports 3.9.
    """

    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed


def require_aware(moment: datetime, field: str = "now") -> datetime:
    """Reject a naive clock before it reaches an arithmetic operation.

    ``datetime.now()`` is the obvious thing for a caller to write and returns a
    naive value, which would otherwise surface much later as "can't subtract
    offset-naive and offset-aware datetimes" from inside a comparison. Saying
    so here names the argument and the fix; assuming UTC instead would be the
    same silent guess this module refuses to make.
    """

    if not isinstance(moment, datetime):
        raise ValueError(f"{field} must be a datetime")
    if moment.tzinfo is None:
        raise ValueError(
            f"{field} must be timezone-aware; use datetime.now(timezone.utc)"
        )
    return moment
