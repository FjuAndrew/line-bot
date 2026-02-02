import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials


GS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def ensure_service_account_file(path: str = "service_account.json") -> str:
    """
    Render 建議：把整份 service_account.json 內容放 env: GOOGLE_SERVICE_ACCOUNT_JSON
    啟動時寫出檔案供 google-auth 使用
    """
    if os.path.exists(path):
        return path

    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        raise RuntimeError("Missing env: GOOGLE_SERVICE_ACCOUNT_JSON")

    with open(path, "w", encoding="utf-8") as f:
        f.write(sa_json)

    return path


class LedgerRepo:
    """
    Google Sheets:
      - records: ts,amount,category,item,currency,user_id,raw_text,group_id
      - groups : group_id,enabled,created_at,created_by,note
    """

    def __init__(self, spreadsheet_id: str, records_sheet: str = "records", groups_sheet: str = "groups"):
        if not spreadsheet_id:
            raise RuntimeError("Missing spreadsheet_id")

        sa_path = ensure_service_account_file()
        creds = Credentials.from_service_account_file(sa_path, scopes=GS_SCOPES)

        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_key(spreadsheet_id)
        self.ws_records = self.sh.worksheet(records_sheet)
        self.ws_groups = self.sh.worksheet(groups_sheet)

    # ===== groups =====
    def get_group_enabled(self, group_id: str) -> bool:
        rows = self.ws_groups.get_all_records()
        for r in rows:
            if str(r.get("group_id", "")) == group_id:
                v = r.get("enabled", False)
                if isinstance(v, bool):
                    return v
                return str(v).strip().upper() == "TRUE"
        return False

    def enable_group(self, group_id: str, actor_user_id: str) -> None:
        rows = self.ws_groups.get_all_records()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        for idx, r in enumerate(rows, start=2):  # header 在第1列
            if str(r.get("group_id", "")) == group_id:
                self.ws_groups.update(f"B{idx}", "TRUE")
                self.ws_groups.update(f"D{idx}", actor_user_id)
                return

        self.ws_groups.append_row(
            [group_id, "TRUE", now, actor_user_id, ""],
            value_input_option="USER_ENTERED",
        )

    # ===== records =====
    def add_record(
        self,
        group_id: str,
        user_id: str,
        raw_text: str,
        item: str,
        amount: int,
        category: str,
        currency: str = "TWD",
        ts: str = None,
    ) -> None:
        if ts is None:
            # 若呼叫端沒給時間，就用 UTC
            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        self.ws_records.append_row(
            [ts, int(amount), category, item, currency, user_id, raw_text, group_id],
            value_input_option="USER_ENTERED",
        )

    def query_records(
        self,
        group_id: str,
        start_iso: str,
        end_iso: str,
        category: str = None,
        limit: int = 50,
    ):
        rows = self.ws_records.get_all_records()
        out = []
        for r in rows:
            if str(r.get("group_id", "")) != group_id:
                continue
            ts = str(r.get("ts", ""))
            if not (start_iso <= ts < end_iso):
                continue
            if category and str(r.get("category", "")) != category:
                continue
            out.append(r)

        out.sort(key=lambda x: str(x.get("ts", "")), reverse=True)
        return out[:limit]

    def summary_by_category(
        self,
        group_id: str,
        start_iso: str,
        end_iso: str,
        category: str = None,
    ) -> dict:
        """
        回傳：
          - total_amount
          - total_count
          - by_category: {category: {"amount": x, "count": y}}
        若 category 有給，則只統計該類別（by_category 仍會回傳單一類別）
        """
        rows = self.ws_records.get_all_records()
        total_amount = 0
        total_count = 0
        by_cat = {}

        for r in rows:
            if str(r.get("group_id", "")) != group_id:
                continue

            ts = str(r.get("ts", ""))
            if not (start_iso <= ts < end_iso):
                continue

            cat = str(r.get("category", "") or "未分類")
            if category and cat != category:
                continue

            amt = int(r.get("amount", 0) or 0)

            total_amount += amt
            total_count += 1

            if cat not in by_cat:
                by_cat[cat] = {"amount": 0, "count": 0}
            by_cat[cat]["amount"] += amt
            by_cat[cat]["count"] += 1

        by_cat = dict(sorted(by_cat.items(), key=lambda kv: kv[1]["amount"], reverse=True))

        return {
            "total_amount": total_amount,
            "total_count": total_count,
            "by_category": by_cat,
        }


if __name__ == "__main__":
    # 快速自測：確保此檔案可以被 import / 執行，不會縮排錯
    print("gsheets_repo loaded OK")
