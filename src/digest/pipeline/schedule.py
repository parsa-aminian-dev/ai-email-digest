from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from src.digest.config.settings import DigestConfig


def daily_window(now: datetime, config: DigestConfig) -> tuple[datetime, datetime]:
    """Latest scheduled local-time boundary, including 23/25-hour DST days."""
    zone = ZoneInfo(config.timezone)
    local = now.astimezone(zone)
    hour, minute = map(int, config.time.split(":"))
    end = local.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0)
    if end.astimezone(UTC) > now.astimezone(UTC):
        end -= timedelta(days=1)
    start = end - timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)
