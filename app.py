from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot import LineBotApi
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import os
import random
from linebot.models import *

app = Flask(__name__)
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

if not channel_secret or not channel_access_token:
    raise ValueError("Environment variables for LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN are required.")


line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)


@app.route("/", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    app.logger.info("Request headers: " + str(request.headers))
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature.")
        abort(400)
    except Exception as e:
        app.logger.error(f"Error handling request: {e}")
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    if "吃什麼" in event.message.text:
        eat = random.choice(['水餃', '小7', '火鍋', '炒飯', '拉麵', '陽春麵'])
        message = TextSendMessage(text=eat)
    else:
        # 默认回复消息
        message = TextSendMessage(text=event.message.text)
    
    try:
        line_bot_api.reply_message(event.reply_token, message)
    except Exception as e:
        app.logger.error(f"Error sending reply message: {e}")



if __name__ == "__main__":
    app.run()
