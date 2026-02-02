from flask import Flask, request, abort, jsonify, redirect
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    LocationMessageContent,
    StickerMessageContent,
    ImageMessageContent,
    VideoMessageContent,
    AudioMessageContent,
    FileMessageContent,
    UserSource,
    RoomSource,
    GroupSource,
    FollowEvent,
    UnfollowEvent,
    JoinEvent,
    LeaveEvent,
    PostbackEvent,
    BeaconEvent,
    MemberJoinedEvent,
    MemberLeftEvent,
)

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    PushMessageRequest,
    MulticastRequest,
    BroadcastRequest,
    TextMessage,
    ApiException,
    LocationMessage,
    StickerMessage,
    ImageMessage,
    TemplateMessage,
    FlexMessage,
    Emoji,
    QuickReply,
    QuickReplyItem,
    ConfirmTemplate,
    ButtonsTemplate,
    CarouselTemplate,
    CarouselColumn,
    ImageCarouselTemplate,
    ImageCarouselColumn,
    FlexBubble,
    FlexImage,
    FlexBox,
    FlexText,
    FlexIcon,
    FlexButton,
    FlexSeparator,
    FlexContainer,
    MessageAction,
    URIAction,
    PostbackAction,
    DatetimePickerAction,
    CameraAction,
    CameraRollAction,
    LocationAction,
    ErrorResponse
)
from linebot.exceptions import LineBotApiError
import os
import json
import gunicorn
import random
import urllib.parse
from DrissionPage import ChromiumPage, ChromiumOptions
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

# ===== 新增：拆出去的模組 =====
from ledger import parse_ledger_command, resolve_ledger_range, TAIPEI_TZ
from gsheets_repo import LedgerRepo

app = Flask(__name__)

channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
user_id = os.getenv('USER_ID')

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

SECRET_FILES_PATH = "/etc/secrets"
JSON_FILE_PATH = os.path.join(SECRET_FILES_PATH, "user_ids.json")

def initialize_json_file():
    if not os.path.exists(JSON_FILE_PATH):
        with open(JSON_FILE_PATH, "w") as f:
            json.dump({"user_ids": []}, f)
            print(f"Created new JSON file at {JSON_FILE_PATH}")
    else:
        print(f"JSON file already exists at {JSON_FILE_PATH}")

def add_user_id_to_json(user_id):
    initialize_json_file()
    with open(JSON_FILE_PATH, "r") as f:
        data = json.load(f)

    if user_id not in data["user_ids"]:
        data["user_ids"].append(user_id)
        print(f"User ID {user_id} added to JSON file.")

    with open(JSON_FILE_PATH, "w") as f:
        json.dump(data, f, indent=4)

def get_all_user_ids():
    initialize_json_file()
    with open(JSON_FILE_PATH, "r") as f:
        data = json.load(f)
    return data["user_ids"]

# =========================================================
# ✅ 記帳 Repo（全域初始化一次，避免每次訊息都重新連 Sheets）
# =========================================================
LEDGER_SPREADSHEET_ID = os.getenv("LEDGER_SPREADSHEET_ID")
repo = None
if LEDGER_SPREADSHEET_ID:
    repo = LedgerRepo(spreadsheet_id=LEDGER_SPREADSHEET_ID)

ENABLE_TRIGGER = "啟用記帳功能"

@app.route("/health", methods=['HEAD', 'GET'])
def health_check():
    timezone = pytz.timezone('Asia/Taipei')
    now = datetime.now(timezone)
    target_hour = 10
    print(now.hour)

    if now.hour == target_hour and 10 <= now.minute <= 19:
        send_line_message()
    return 'OK', 200

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    print(user_id)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text='感謝加入好友')]
            )
        )

@app.route('/send_message', methods=['POST', 'GET'])
def send_message():
    data = request.json
    if 'user_id' not in data or 'message' not in data:
        return jsonify({'error': 'user_id and message are required'}), 400

    user_id = data['user_id']
    message = data['message']

    try:
        with ApiClient(configuration) as api_client:
            line_bot_apiv3 = MessagingApi(api_client)
            push_message_request = PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=message)]
            )
            line_bot_apiv3.push_message(push_message_request)
            return jsonify({'status': 'success', 'message': 'Message sent successfully!'}), 200

    except LineBotApiError as e:
        return jsonify({'error': f'Failed to send message: {e.status_code} - {e.error.message}'}), 500

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        print(event)

        source_type = event.source.type  # "user" / "group"
        group_id = None
        if source_type == "group":
            group_id = event.source.group_id
            print(f"Group ID: {group_id}")

        text = (event.message.text or "").strip()

        # =========================================================
        # ✅ 記帳功能：多群組動態啟用（已拆到 repo / ledger 模組）
        # =========================================================
        if source_type == "group" and group_id and repo:
            # 1) 觸發啟用
            if ENABLE_TRIGGER in text:
                try:
                    repo.enable_group(group_id=group_id, actor_user_id=event.source.user_id)
                    line_bot_apiv3.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="此群組已啟用記帳功能")]
                        )
                    )
                except Exception as e:
                    line_bot_apiv3.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f"啟用失敗：{e}")]
                        )
                    )
                return

            # 2) gate：已啟用才處理記帳/查詢
            try:
                enabled = repo.get_group_enabled(group_id)
            except Exception as e:
                print(f"[ledger] get_group_enabled error: {e}")
                enabled = False

            if enabled:
                cmd = parse_ledger_command(text)

                # 記帳：類別 金額 商品
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
                        line_bot_apiv3.reply_message_with_http_info(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=f"已記錄：{cmd['category']} {cmd['amount']} {cmd['item']}")]
                            )
                        )
                    except Exception as e:
                        line_bot_apiv3.reply_message_with_http_info(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=f"記錄失敗：{e}")]
                            )
                        )
                    return

                # 查詢
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
                            limit=50
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

                        line_bot_apiv3.reply_message_with_http_info(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=msg)]
                            )
                        )
                    except Exception as e:
                        line_bot_apiv3.reply_message_with_http_info(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=f"查詢失敗：{e}")]
                            )
                        )
                    return

        # ===================== 你原本的功能（保留） =====================
        if re.search(r"吃.*麼|吃啥", text):
            choose_food(event)
        elif re.search(r"喝.*麼|喝啥", text):
            choose_drink(event)
        elif '查詢' in text:
            user_message = text
            user_input_for_search = user_message.replace("查詢", "").strip()
            print(user_input_for_search)
            button_template(event, user_input_for_search)
        elif '測試' in text:
            test_template(event)
        elif '中介' in text:
            send_button_template(event)
        elif '匯率' in text:
            search_exchange(event)
        elif '聽寶的' in text:
            listenbao(event)
        else:
            line_bot_apiv3.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=text)]
                )
            )

def choose_food(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        eat = random.choice(['八方', '7-11', '滷肉飯', '涼麵','牛肉麵','麥噹噹','摩斯','拉麵','咖哩飯','粥','秀秀早餐','聽寶的'])
        line_bot_apiv3.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=eat)]))

def choose_drink(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        drink = random.choice(['可不可','得正','50嵐','鶴茶樓','再睡','一沐日','青山','UG','壽奶茶','迷客夏','COCO','聽寶的'])
        line_bot_apiv3.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=drink)]))

def listenbao(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        drink = random.choice(['動作快點','愛哥哥','哥哥晚安','哥哥早安','我要睡覺','來陪我','快去讀書','拖拖拉拉','波波調皮','噗咕乖乖','玩Bumble','寶是公主寶說的算','我是不是變胖了','我的腿是不是變粗了','呆瓜哥哥','你還想在這邊跟我聊天喔','討厭哥哥','哥哥是小豬'])
        line_bot_apiv3.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=drink)]))

def search_exchange(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        line_bot_apiv3.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="爬取中，請稍後")]))
        url = 'https://accessibility.cathaybk.com.tw/exchange-rate-search.aspx'
        response = requests.get(url)
        exchange = []
        keywords = ["日圓","美元","人民幣","歐元"]
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            titles = soup.find_all('td')
            try:
                for i in range(0, len(titles), 3):
                    if i < len(titles):
                        t = titles[i].get_text()
                        if any(keyword in t for keyword in keywords):
                            for j in range(i, min(i + 3, len(titles))):
                                exchange.append(titles[j].get_text())
                grouped_data = [exchange[i:i + 3] for i in range(0, len(exchange), 3)]
                today = datetime.now().strftime('%Y-%m-%d')
                additional_info = f"今日匯率信息\n日期: {today}\n\n"
                formatted_rates = []
                for currency, buy, sell in grouped_data:
                    formatted_rates.append(f"{currency}\n買入: {buy}\n賣出: {sell}\n")
                formatted_message = additional_info + "\n".join(formatted_rates)
            except Exception as e:
                print(f"發生錯誤:{e}")
                formatted_message = "爬取失敗"
        else:
            formatted_message = "爬取失敗"

        line_bot_apiv3.push_message(
            PushMessageRequest(
                to=event.source.user_id,
                messages=[TextMessage(text=formatted_message)]
            )
        )

def button_template(event, user_input_for_search):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        user_input_for_search = urllib.parse.quote(user_input_for_search)
        buttons_template = ButtonsTemplate(
            title='查詢任意門',
            thumbnail_image_url='https://i.imgur.com/nwFbufB.jpeg',
            text='請選擇以下連結',
            actions=[
                MessageAction(label='說哈囉', text='Hello!'),
                URIAction(label='GOOGLE', uri=f'https://www.google.com/search?q={user_input_for_search}'),
                URIAction(label='維基', uri=f'https://zh.wikipedia.org/wiki/{user_input_for_search}'),
                URIAction(label='Google Maps', uri=f'https://www.google.com/maps/search/{user_input_for_search}')
            ]
        )
        template_message = TemplateMessage(
            alt_text='查詢任意門',
            template=buttons_template
        )
        try:
            line_bot_apiv3.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[template_message]
            ))
        except LineBotApiError as e:
            print(f"Error: {e}")

def send_line_message():
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        try:
            line_bot_apiv3.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text='Hello! Damn SoB')]
                ))
            print("已發出訊息")
        except Exception as e:
            print(f'Error: {e}')

def test_template(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        buttons_template = ButtonsTemplate(
            title='查詢任意門',
            thumbnail_image_url='https://i.imgur.com/nwFbufB.jpeg',
            text='請選擇以下操作',
            actions=[
                PostbackAction(label='開啟 Google', data='open_google')
            ]
        )
        template_message = TemplateMessage(
            alt_text='查詢任意門',
            template=buttons_template
        )
        try:
            line_bot_apiv3.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[template_message]
            ))
        except LineBotApiError as e:
            print(f"Error: {e}")

@app.route('/track_and_redirect', methods=['POST', 'GET'])
def track_and_redirect():
    user_id = request.args.get('user_id')
    print(f"{user_id}點擊了按鈕!")
    return redirect('https://www.google.com')

def send_button_template(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        tracking_url = f'https://line-bot-fi4w.onrender.com/track_and_redirect?user_id={event.source.user_id}'
        buttons_template = ButtonsTemplate(
            title='查詢 Google',
            text='點擊下方按鈕開啟 Google',
            actions=[
                URIAction(label='開啟 Google', uri=tracking_url)
            ]
        )
        template_message = TemplateMessage(
            alt_text='查詢 Google',
            template=buttons_template
        )
        line_bot_apiv3.reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[template_message]
        ))

@handler.add(PostbackEvent)
def handle_postback(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        data = event.postback.data
        timestamp = event.timestamp
        print(timestamp)

        if data == 'open_google':
            url = 'https://www.google.com'
            line_bot_apiv3.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=f'您選擇了開啟 Google: {url}')]
            ))
        else:
            line_bot_apiv3.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="無法處理的操作")]
            ))

if __name__ == "__main__":
    app.run()
