from flask import Flask, request, abort, jsonify, redirect
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    FollowEvent,
    PostbackEvent,
)

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    TemplateMessage,
    ButtonsTemplate,
    MessageAction,
    URIAction,
    PostbackAction,
)
from linebot.exceptions import LineBotApiError

import os
import json
import random
import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import pytz

# ===== 拆出去的模組 =====
from ledger import parse_ledger_command, resolve_ledger_range, TAIPEI_TZ
from gsheets_repo import LedgerRepo

app = Flask(__name__)

# ===== LINE 設定 =====
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
USER_ID = os.getenv("USER_ID")

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

# ===== 你原本的 Secret JSON 存放（保留） =====
SECRET_FILES_PATH = "/etc/secrets"
JSON_FILE_PATH = os.path.join(SECRET_FILES_PATH, "user_ids.json")


def initialize_json_file():
    if not os.path.exists(JSON_FILE_PATH):
        os.makedirs(SECRET_FILES_PATH, exist_ok=True)
        with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump({"user_ids": []}, f)
            print(f"Created new JSON file at {JSON_FILE_PATH}")


def add_user_id_to_json(user_id):
    initialize_json_file()
    with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    if user_id not in data["user_ids"]:
        data["user_ids"].append(user_id)

    with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_all_user_ids():
    initialize_json_file()
    with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["user_ids"]


# =========================================================
# ✅ 記帳設定
# =========================================================
LEDGER_SPREADSHEET_ID = os.getenv("LEDGER_SPREADSHEET_ID")
ENABLE_TRIGGER = "啟用記帳功能"

repo = LedgerRepo(spreadsheet_id=LEDGER_SPREADSHEET_ID) if LEDGER_SPREADSHEET_ID else None


@app.route("/health", methods=["HEAD", "GET"])
def health_check():
    return "OK", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="感謝加入好友")],
            )
        )


@app.route("/send_message", methods=["POST", "GET"])
def send_message():
    data = request.json or {}
    if "user_id" not in data or "message" not in data:
        return jsonify({"error": "user_id and message are required"}), 400

    to_user_id = data["user_id"]
    message = data["message"]

    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=to_user_id,
                    messages=[TextMessage(text=message)],
                )
            )
        return jsonify({"status": "success"}), 200
    except LineBotApiError as e:
        return jsonify({"error": str(e)}), 500


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = (event.message.text or "").strip()
    source_type = event.source.type  # user / group / room

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # =========================
        # 群組才處理記帳功能
        # =========================
        group_id = None
        if source_type == "group":
            group_id = event.source.group_id

        # === 記帳功能（多群組動態啟用）===
        if source_type == "group" and group_id and repo:
            # 1) 觸發啟用
            if ENABLE_TRIGGER in text:
                try:
                    repo.enable_group(group_id=group_id, actor_user_id=event.source.user_id)
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="此群組已啟用記帳功能")],
                        )
                    )
                except Exception as e:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f"啟用失敗：{e}")],
                        )
                    )
                return

            # 2) gate：已啟用才處理記帳/查詢/彙整/指令
            try:
                enabled = repo.get_group_enabled(group_id)
            except Exception as e:
                print(f"[ledger] get_group_enabled error: {e}")
                enabled = False

            if enabled:
                cmd = parse_ledger_command(text)

                # 2.1 指令說明
                if cmd["type"] == "help":
                    msg = (
                        "記帳指令：\n"
                        "1) 啟用：啟用記帳功能\n"
                        "2) 記帳：類別 金額 商品\n"
                        "   例：餐飲 120 午餐\n"
                        "3) 查詢：查今天 / 查昨天 / 查本月 / 查 2026-02-01\n"
                        "   例：查本月 餐飲\n"
                        "4) 彙整：彙整 今天 / 彙整 昨天 / 彙整 本月 / 彙整 2026-02-01\n"
                        "   例：彙整 本月\n"
                    )
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=msg)],
                        )
                    )
                    return
                    
                if cmd["type"] == "deposit":
                    try:
                        new_balance = repo.deposit(
                            group_id=group_id,
                            amount=cmd["amount"],
                            actor_user_id=event.source.user_id
                        )
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=f"已存入 {cmd['amount']} 元\n目前儲存金：{new_balance} 元")]
                            )
                        )
                    except Exception as e:
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=f"存入失敗：{e}")]
                            )
                        )
                    return
                # 2.2 記帳：類別 金額 商品
                if cmd["type"] == "add":
                    try:
                        ts = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
                        repo.add_record(
                            group_id=group_id,
                            user_id=event.source.user_id,
                            raw_text=text,
                            item=cmd["item"],
                            amount=cmd["amount"],
                            category=cmd["category"],
                            currency="TWD",
                            ts=ts,
                        )

                        # ✅ 新增：扣儲存金並回覆餘額
                        balance = repo.deduct(
                            group_id=group_id,
                            amount=cmd["amount"],
                            actor_user_id=event.source.user_id
                        )

                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(
                                    text=(
                                        f"已記錄：{cmd['category']} {cmd['amount']} {cmd['item']}\n"
                                        f"剩餘儲存金：{balance} 元"
                                    )
                                )],
                            )
                        )
                    except Exception as e:
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=f"記錄失敗：{e}")],
                            )
                        )
                    return

                # 2.3 查詢明細
                if cmd["type"] == "query":
                    try:
                        start_dt, end_dt = resolve_ledger_range(cmd["range"])
                        start_iso = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                        end_iso = end_dt.strftime("%Y-%m-%d %H:%M:%S")

                        rows = repo.query_records(
                            group_id=group_id,
                            start_iso=start_iso,
                            end_iso=end_iso,
                            category=cmd.get("category"),
                            limit=50,
                        )

                        if not rows:
                            msg = "查無資料"
                        else:
                            total = sum(int(r.get("amount", 0)) for r in rows)
                            head = f"共 {len(rows)} 筆，合計 {total} 元"
                            lines = [
                                f"- {r.get('ts','')} {r.get('category','')} {r.get('amount','')} {r.get('item','')}"
                                for r in rows[:10]
                            ]
                            more = "" if len(rows) <= 10 else "\n(僅顯示前 10 筆；可用：查本月 餐飲)"
                            msg = head + "\n" + "\n".join(lines) + more

                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=msg)],
                            )
                        )
                    except Exception as e:
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=f"查詢失敗：{e}")],
                            )
                        )
                    return

                # 2.4 彙整：各類別合計
                if cmd["type"] == "summary":
                    try:
                        start_dt, end_dt = resolve_ledger_range(cmd["range"])
                        start_iso = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                        end_iso = end_dt.strftime("%Y-%m-%d %H:%M:%S")

                        data = repo.summary_by_category(
                            group_id=group_id,
                            start_iso=start_iso,
                            end_iso=end_iso,
                            category=cmd.get("category"),
                        )

                        if data["total_count"] == 0:
                            msg = "查無資料"
                        else:
                            head = f"彙整（{cmd['range']}）共 {data['total_count']} 筆，合計 {data['total_amount']} 元"
                            lines = []
                            for i, (cat, v) in enumerate(data["by_category"].items()):
                                if i >= 10:
                                    break
                                lines.append(f"- {cat}：{v['amount']} 元（{v['count']} 筆）")
                            more = "" if len(data["by_category"]) <= 10 else "\n(僅顯示前 10 類)"
                            msg = head + "\n" + "\n".join(lines) + more

                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=msg)],
                            )
                        )
                    except Exception as e:
                        line_bot_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=f"彙整失敗：{e}")],
                            )
                        )
                    return

        # =========================
        # 你原本的其他功能（保留）
        # =========================
        if re.search(r"吃.*麼|吃啥", text):
            eat = random.choice(["八方", "7-11", "滷肉飯", "涼麵", "牛肉麵", "麥噹噹", "摩斯", "拉麵", "咖哩飯", "粥", "秀秀早餐", "聽寶的"])
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=eat)])
            )
            return

        if re.search(r"喝.*麼|喝啥", text):
            drink = random.choice(["可不可", "得正", "50嵐", "鶴茶樓", "再睡", "一沐日", "青山", "UG", "壽奶茶", "迷客夏", "COCO", "聽寶的"])
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=drink)])
            )
            return

        if "查詢" in text:
            user_input_for_search = text.replace("查詢", "").strip()
            q = urllib.parse.quote(user_input_for_search)
            buttons_template = ButtonsTemplate(
                title="查詢任意門",
                thumbnail_image_url="https://i.imgur.com/nwFbufB.jpeg",
                text="請選擇以下連結",
                actions=[
                    MessageAction(label="說哈囉", text="Hello!"),
                    URIAction(label="GOOGLE", uri=f"https://www.google.com/search?q={q}"),
                    URIAction(label="維基", uri=f"https://zh.wikipedia.org/wiki/{q}"),
                    URIAction(label="Google Maps", uri=f"https://www.google.com/maps/search/{q}"),
                ],
            )
            template_message = TemplateMessage(alt_text="查詢任意門", template=buttons_template)
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[template_message])
            )
            return

        if "匯率" in text:
            # 簡化版：你原本匯率爬蟲可自行替換回去
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="匯率功能：爬取中...")])
            )
            return

        # 預設回音
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=text)])
        )


@handler.add(PostbackEvent)
def handle_postback(event):
    # 你原本 postback 邏輯可自行補回
    pass


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
