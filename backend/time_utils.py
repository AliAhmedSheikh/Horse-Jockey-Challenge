from datetime import datetime
from zoneinfo import ZoneInfo

AU_TZ = ZoneInfo("Australia/Sydney")


def today_aus() -> str:
    return datetime.now(AU_TZ).strftime("%Y-%m-%d")
