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
        ts: str | None = None,
    ) -> None:
        if ts is None:
            # 不做時區轉換，交給呼叫端傳入（由 app.py 用台北時間產生）
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
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
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
