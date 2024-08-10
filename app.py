from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import os
import random
from linebot.models import *

app = Flask(__name__)
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

configuration = Configuration(channel_access_token)
handler = WebhookHandler(channel_secret)
with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)



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

        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=event.message.text)]
            )
        )
@ handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    if "吃什麼" in event.message.text:
        eat = random.choice(['水餃', '小7', '火鍋', '炒飯','拉麵','陽春麵'])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=eat))





if __name__ == "__main__":
    app.run()
