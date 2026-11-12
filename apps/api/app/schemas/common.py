from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def _as_utc(v: datetime) -> datetime:
    """SQLite 는 tz 정보를 버리므로 저장값(UTC)을 읽을 때 다시 붙인다."""
    return v.replace(tzinfo=UTC) if v.tzinfo is None else v.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]
