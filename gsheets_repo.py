import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

class LedgerSheetRepo:
    def __init__(self, sa_json_path: str, spreadsheet_id: str):
        creds = Credentials.from_service_account_file(sa_json_path, scopes=SCOPES)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(spreadsheet_id)

        self.ws_records = sh.worksheet("records")
        self.ws_groups = sh.worksheet("groups")

    # ===== groups (啟用狀態) =====
    def get_group_enabled(self, group_id: str) -> bool:
        rows = self.ws_groups.get_all_records()
        for r in rows:
            if str(r.get("group_id", "")) == group_id:
                v = r.get("enabled", False)
                if isinstance(v, bool):
                    return v
                return str(v).strip().upper() == "TRUE"
        return False

    def enable_group(self, group_id: str, actor_user_id: str):
        rows = self.ws_groups.get_all_records()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # 已存在 -> 更新 enabled
        for idx, r in enumerate(rows, start=2):  # header 在第 1 列
            if str(r.get("group_id", "")) == group_id:
                self.ws_groups.update(f"B{idx}", "TRUE")
                self.ws_groups.update(f"D{idx}", actor_user_id)
                return

        # 不存在 -> 新增
        self.ws_groups.append_row(
            [group_id, "TRUE", now, actor_user_id, ""],
            value_input_option="USER_ENTERED",
        )

    # ===== records (記帳明細) =====
    def add_record(
        self,
        ts: str,
        amount: int,
        category: str,
        item: str,
        currency: str,
        user_id: str,
        raw_text: str,
        group_id: str,
    ):
        # records 欄位順序：ts,amount,category,item,currency,user_id,raw_text,group_id
        self.ws_records.append_row(
            [ts, amount, category, item, currency, user_id, raw_text, group_id],
            value_input_option="USER_ENTERED",
        )

    def query_records(
        self,
        group_id: str,
        start_iso: str,
        end_iso: str,
        category: str | None = None,
        limit: int = 50,
    ):
        """
        簡化版：get_all_records 後過濾
        - 依 group_id 過濾（避免多群組混）
        - 依 ts 字串區間過濾（要求 ts 格式一致：YYYY-MM-DD HH:mm:ss）
        """
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
