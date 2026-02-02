import re
from datetime import datetime, timedelta
from dateutil import tz

TAIPEI_TZ = tz.gettz("Asia/Taipei")

def parse_command(text: str):
    """
    支援：
    - 記帳：品項 金額 類別(可選)   e.g. 午餐 120 餐飲 / 咖啡 60
    - 查詢：查今天 / 查昨天 / 查本月 / 查本月 餐飲 / 查 2026-02-01 / 查 2026-02-01 餐飲
    """
    t = (text or "").strip()

    # 查詢：查今天/昨天/本月 (+ 類別)
    m = re.match(r"^查(今天|昨天|本月)(?:\s+(\S+))?$", t)
    if m:
        return {"type": "query", "range": m.group(1), "category": m.group(2)}

    # 查詢：查 YYYY-MM-DD (+ 類別)
    m = re.match(r"^查\s+(\d{4}-\d{2}-\d{2})(?:\s+(\S+))?$", t)
    if m:
        return {"type": "query", "range": m.group(1), "category": m.group(2)}

    # 記帳：品項 金額 類別(可選)
    m = re.match(r"^(.+?)\s+(-?\d+)(?:\s+(\S+))?$", t)
    if m:
        item = m.group(1).strip()
        amount = int(m.group(2))
        category = (m.group(3) or "其他").strip()
        return {"type": "add", "item": item, "amount": amount, "category": category}

    return {"type": "unknown"}

def resolve_date_range(range_key: str):
    now = datetime.now(TAIPEI_TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if range_key == "今天":
        return today, today + timedelta(days=1)

    if range_key == "昨天":
        return today - timedelta(days=1), today

    if range_key == "本月":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end

    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", range_key):
        start = datetime.fromisoformat(range_key).replace(tzinfo=TAIPEI_TZ)
        return start, start + timedelta(days=1)

    raise ValueError("Unsupported range")
