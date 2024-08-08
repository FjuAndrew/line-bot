from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import os

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ['UZ83W/SnkQoLRE3cyBmA4lmjqvr1sWUMr480jsOSwcUvkgYaBS6V7Tr8IrwZEj4iTZyqgx9X/pTUYg9U4Ayai4GdL0cS3umfQprdmWH+kCs4zhzfGItLdYwSHdXGoANpwR8L1V5QKg0nyv2fmjczawdB04t89/1O/w1cDnyilFU='])
handler = WebhookHandler(os.environ['f4ff46da7257b20d8b6a663ff2557927'])


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    message = TextSendMessage(text=event.message.text)
    line_bot_api.reply_message(event.reply_token, message)

import os
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)