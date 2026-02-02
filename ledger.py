import re
from datetime import datetime, timedelta
import pytz

TAIPEI_TZ = pytz.timezone("Asia/Taipei")

def parse_ledger_command(text: str):
    """
    記帳（新版）：
      - 類別 金額 商品(可含空白)
        e.g. 餐飲 120 午餐
             交通 250 uber 回家

    查詢：
      - 查今天 / 查昨天 / 查本月
      - 查本月 餐飲
      - 查 2026-02-01
      - 查 2026-02-01 餐飲

    彙整：
      - 彙整 今天 / 彙整 昨天 / 彙整 本月
      - 彙整 2026-02-01
      - （可選）彙整 本月 餐飲  → 只彙整某類別（回傳總額+筆數）

    說明：
      - 指令 / help / ?
    """
    t = (text or "").strip()

    # 指令說明
    if t in ("指令", "help", "HELP", "?"):
        return {"type": "help"}

    # 彙整：彙整 今天/昨天/本月 (+ 類別可選)
    m = re.match(r"^彙整\s*(今天|昨天|本月)(?:\s+(\S+))?$", t)
    if m:
        return {"type": "summary", "range": m.group(1), "category": m.group(2)}

    # 彙整：彙整 YYYY-MM-DD (+ 類別可選)
    m = re.match(r"^彙整\s+(\d{4}-\d{2}-\d{2})(?:\s+(\S+))?$", t)
    if m:
        return {"type": "summary", "range": m.group(1), "category": m.group(2)}

    # 查詢：查今天/昨天/本月 (+ 類別)
    m = re.match(r"^查(今天|昨天|本月)(?:\s+(\S+))?$", t)
    if m:
        return {"type": "query", "range": m.group(1), "category": m.group(2)}

    # 查詢：查 YYYY-MM-DD (+ 類別)
    m = re.match(r"^查\s+(\d{4}-\d{2}-\d{2})(?:\s+(\S+))?$", t)
    if m:
        return {"type": "query", "range": m.group(1), "category": m.group(2)}

    # 記帳：類別 金額 商品(可含空白)
    m = re.match(r"^(\S+)\s+(\d+)\s+(.+)$", t)
    if m:
        category = m.group(1).strip()
        amount = int(m.group(2))
        item = m.group(3).strip()
        return {"type": "add", "item": item, "amount": amount, "category": category}

    # 存入：存入 金額
    m = re.match(r"^存入\s+(\d+)$", t)
    if m:
        return {"type": "deposit", "amount": int(m.group(1))}
    
    return {"type": "unknown"}


def resolve_ledger_range(range_key: str):
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

    if re.match(r"^\d{4}-\d{2}-\d{2}$", range_key):
        dt = datetime.fromisoformat(range_key)
        start = TAIPEI_TZ.localize(dt)
        return start, start + timedelta(days=1)

    raise ValueError("Unsupported range")

