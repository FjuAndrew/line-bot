from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
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
import gunicorn
import random
import urllib.parse
from DrissionPage import ChromiumPage, ChromiumOptions
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
from apscheduler.schedulers.background import BackgroundScheduler
# from linebot.models import PostbackAction,URIAction, MessageAction, TemplateSendMessage, ButtonsTemplate
app = Flask(__name__)


channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
configuration = Configuration(access_token=channel_access_token)
#line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)


@app.route("/health", methods=['HEAD', 'GET'])
def health_check():
    now = datetime.now()
    target_hour = 17  # 指定小时

    if now.hour == target_hour and now.minute == target_minute:
        send_line_message()
        time.sleep(3600) 
    return 'OK', 200

@app.route("/", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        print(event)
        if "吃什麼" in event.message.text:
            choose_food(event)
        elif "喝什麼" in event.message.text:
            choose_drink(event) 
        elif '查詢' in event.message.text:
            user_message = event.message.text
            user_input_for_search = user_message.replace("查詢", "").strip()
            print(user_input_for_search)
            button_template(event,user_input_for_search) 
        elif '匯率' in event.message.text:
            search_exchange(event)
        else:
            line_bot_apiv3.reply_message_with_http_info( ReplyMessageRequest( reply_token=event.reply_token, messages=[TextMessage(text=event.message.text)]))
        
def choose_food(event):
        with ApiClient(configuration) as api_client:
            line_bot_apiv3 = MessagingApi(api_client)
            eat = random.choice(['八方', '7-11', '滷肉飯', '涼麵','燒臘','麥噹噹','摩斯','拉麵','咖哩飯'])
            line_bot_apiv3.reply_message_with_http_info( ReplyMessageRequest( reply_token=event.reply_token, messages=[TextMessage(text=eat)]))
            
def choose_drink(event):
        with ApiClient(configuration) as api_client:
            line_bot_apiv3 = MessagingApi(api_client)
            drink = random.choice(['可不可','得正','50嵐','鶴茶樓','再睡','一沐日'])
            line_bot_apiv3.reply_message_with_http_info( ReplyMessageRequest( reply_token=event.reply_token, messages=[TextMessage(text=drink)]))

def search_exchange(event):
        with ApiClient(configuration) as api_client:
            line_bot_apiv3 = MessagingApi(api_client)
            line_bot_apiv3.reply_message_with_http_info( ReplyMessageRequest( reply_token=event.reply_token, messages=[TextMessage(text="爬取中，請稍後")]))
            url = 'https://accessibility.cathaybk.com.tw/exchange-rate-search.aspx' 
            response = requests.get(url)
            exchange= []
            keywords=["日圓","美元","人民幣","歐元"]
            # 2. 檢查請求是否成功
            if response.status_code == 200:
                # 3. 使用 BeautifulSoup 解析網頁內容
                soup = BeautifulSoup(response.text, 'html.parser')
                # 4. 提取所需的數據
                titles = soup.find_all('td')
                try:
                    for i in range(0, len(titles), 3):
                        # 確保不超出範圍
                        if i < len(titles):
                            text = titles[i].get_text()
                            if any(keyword in text for keyword in keywords):  # 檢查是否有關鍵字匹配
                                # 如果匹配，加入當前標題和後面兩個標題
                                for j in range(i, min(i + 3, len(titles))):
                                    exchange.append(titles[j].get_text())
                                    print(f"已加入{titles[j].get_text()}")
                    grouped_data = [exchange[i:i + 3] for i in range(0, len(exchange), 3)]
                    formatted_message = "\n".join([" | ".join(group) for group in grouped_data])
                except Exception as e:
                    print(f"發生錯誤:{e}")
            else:
                print(f'請求失敗，狀態碼：{response.status_code}')
                formatted_message = "爬取失敗"
            #line_bot_apiv3.reply_message_with_http_info( ReplyMessageRequest( reply_token=event.reply_token, messages=[TextMessage(text=formatted_message)]))
            line_bot_apiv3.push_message(
                PushMessageRequest(
                    to=event.source.user_id,
                    messages=[TextMessage(text=formatted_message)]
                )
            )

def button_template(event,user_input_for_search):
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
                    # 可以修改為自己想要的actions
                ]
            )
        template_message = TemplateMessage(
            alt_text='查詢任意門',
            template=buttons_template
        )
        try:
            # line_bot_api.reply_message('<REPLY_TOKEN>', template_message)
            line_bot_apiv3.reply_message(ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[template_message] # 加上關鍵字參數
            ))
        except LineBotApiError as e:
            print(f"Error: {e}")
def send_line_message():    
    with ApiClient(configuration) as api_client:
        line_bot_apiv3 = MessagingApi(api_client)
        try:
            user_id = 'Uffd67f5430e7b403887d0c8f0701ea14'
            line_bot_apiv3.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text='Hello! Damn SoB')]
                ))
            print("測試主動發訊息")
        except Exception as e:
            print(f'Error: {e}')
        

if __name__ == "__main__":
    # 初始化调度器
    scheduler = BackgroundScheduler()
    # 每天在特定时间发送消息，例如每天的 10:00 AM
    scheduler.add_job(send_line_message, 'cron', minute=0)
    scheduler.start()
    
    app.run()
