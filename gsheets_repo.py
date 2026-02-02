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
    Render 建議：
    - 不要把 service_account.json 上傳 GitHub
    - 把整份 JSON 內容放到環境變數：GOOGLE_SERVICE_ACCOUNT_JSON
    - 程式啟動時寫出檔案供 google-auth 使用
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
      - wallet : group_id,balance,updated_at,updated_by

    注意：
      - records/groups/wallet 的 header(第一列) 必須「唯一且不要有空白」
      - wallet 若 header 重複，get_all_records() 會直接爆
    """

    def __init__(
        self,
        spreadsheet_id: str,
        records_sheet: str = "records",
        groups_sheet: str = "groups",
        wallet_sheet: str = "wallet",
    ):
        if not spreadsheet_id:
            raise RuntimeError("Missing spreadsheet_id")

        sa_path = ensure_service_account_file()
        creds = Credentials.from_service_account_file(sa_path, scopes=GS_SCOPES)

        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_key(spreadsheet_id)

        self.ws_records = self.sh.worksheet(records_sheet)
        self.ws_groups = self.sh.worksheet(groups_sheet)

        # wallet 可能不存在 -> 給出明確錯誤
        try:
            self.ws_wallet = self.sh.worksheet(wallet_sheet)
        except Exception as e:
            raise RuntimeError(f"Wallet worksheet '{wallet_sheet}' not found. Please create it.") from e

    # =========================
    # groups
    # =========================
    def get_group_enabled(self, group_id: str) -> bool:
        rows = self.ws_groups.get_all_records()
        for r in rows:
            if str(r.get("group_id", "")) == str(group_id):
                v = r.get("enabled", False)
                if isinstance(v, bool):
                    return v
                return str(v).strip().upper() == "TRUE"
        return False

    def enable_group(self, group_id: str, actor_user_id: str) -> None:
        rows = self.ws_groups.get_all_records()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        for idx, r in enumerate(rows, start=2):  # header 在第1列
            if str(r.get("group_id", "")) == str(group_id):
                # 單格更新用 update_acell 最穩
                self.ws_groups.update_acell(f"B{idx}", "TRUE")
                self.ws_groups.update_acell(f"D{idx}", actor_user_id)
                return

        self.ws_groups.append_row(
            [group_id, "TRUE", now, actor_user_id, ""],
            value_input_option="USER_ENTERED",
        )

    # =========================
    # records
    # =========================
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
            if str(r.get("group_id", "")) != str(group_id):
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
        category: str | None = None,
    ) -> dict:
        rows = self.ws_records.get_all_records()
        total_amount = 0
        total_count = 0
        by_cat: dict[str, dict] = {}

        for r in rows:
            if str(r.get("group_id", "")) != str(group_id):
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

    # =========================
    # wallet (儲存金)
    # =========================
    def _wallet_find_row(self, group_id: str) -> int | None:
        """
        回傳 wallet 表內對應 group_id 的 row index（從 2 開始），找不到回 None
        用 get_all_values() 避開 header 重複造成 get_all_records() 爆炸
        """
        values = self.ws_wallet.get_all_values()  # 2D list
        if not values:
            return None

        # values[0] 是 header
        for i in range(1, len(values)):
            row = values[i]
            if len(row) >= 1 and str(row[0]).strip() == str(group_id):
                return i + 1  # sheet row index (1-based)
        return None

    def get_balance(self, group_id: str) -> int:
        row_idx = self._wallet_find_row(group_id)
        if row_idx is None:
            return 0

        v = self.ws_wallet.acell(f"B{row_idx}").value
        try:
            return int(v or 0)
        except Exception:
            return 0

    def deposit(self, group_id: str, amount: int, actor_user_id: str) -> int:
        """
        存入金額，回傳存入後餘額
        """
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row_idx = self._wallet_find_row(group_id)

        if row_idx is None:
            new_balance = int(amount)
            self.ws_wallet.append_row(
                [group_id, new_balance, now, actor_user_id],
                value_input_option="USER_ENTERED",
            )
            return new_balance

        cur = self.get_balance(group_id)
        new_balance = cur + int(amount)

        # 單格更新用 update_acell（避免 update() 400 "B2"）
        self.ws_wallet.update_acell(f"B{row_idx}", str(new_balance))
        self.ws_wallet.update_acell(f"C{row_idx}", now)
        self.ws_wallet.update_acell(f"D{row_idx}", actor_user_id)
        return new_balance

    def deduct(self, group_id: str, amount: int, actor_user_id: str) -> int:
        """
        扣款（記帳時用），回傳扣款後餘額
        若 wallet 沒有該 group_id，視為 0 再扣（可能變負數）
        """
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row_idx = self._wallet_find_row(group_id)

        if row_idx is None:
            new_balance = 0 - int(amount)
            self.ws_wallet.append_row(
                [group_id, new_balance, now, actor_user_id],
                value_input_option="USER_ENTERED",
            )
            return new_balance

        cur = self.get_balance(group_id)
        new_balance = cur - int(amount)

        self.ws_wallet.update_acell(f"B{row_idx}", str(new_balance))
        self.ws_wallet.update_acell(f"C{row_idx}", now)
        self.ws_wallet.update_acell(f"D{row_idx}", actor_user_id)
        return new_balance


if __name__ == "__main__":
    print("gsheets_repo loaded OK")
