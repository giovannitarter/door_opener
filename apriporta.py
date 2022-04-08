#!/usr/bin/python

import sys
import telegram
import logging
import os
import time

from telegram.ext import Updater
from telegram.ext import CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext.filters import Filters


import paho.mqtt.client as mqtt
import threading
import signal

import config as cfg


#logging.basicConfig(
#        level=logging.DEBUG,
#        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
#        )


#
#MQTT
#
class MqttClient():

    def __init__(self, callback, settings):

        self.exit = False
        self.callback = callback
        self.settings = settings

        self.connected = False

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.connect(
                self.settings["addr"],
                self.settings["port"],
                self.settings["timeout"],
                )
        self.client.reconnect_delay_set(min_delay=1, max_delay=120)

        self.main_thread = threading.Thread(target=self.mqtt_thread_body)
        self.main_thread.start()
        return


    def on_connect(self, client, userdata, flags, rc):
        """
        The callback for when the client receives a CONNACK response from the server.
        """

        print("Connected with result code {}".format(rc))

        if rc == 0:
            self.connected = True

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        return


    def on_message(self, client, userdata, msg):
        """
        The callback for when a PUBLISH message is received from the server.
        """
        self.callback(msg)
        return

    def on_disconnect(self, client, userdata, rc):

        if rc != 0:
            print("Unexpected disconnection.")

        self.connected = False

        return


    def publish(self, topic, msg):
        self.client.publish(topic, msg)
        return


    def mqtt_thread_body(self):
        while not self.exit:

            if not self.connected:

                print("Not connected, trying reconnection")

                try:
                    self.client.reconnect()
                    time.sleep(2)
                except Exception as e:
                    print("Exception occurred")
                    print(e)
                    time.sleep(5)
                    continue

            self.client.loop()

        return


    def close(self):
        self.client.disconnect()
        self.exit = True
        self.main_thread.join()
        return


class TelegramClient():

    def __init__(self, callback, settings):

        self.callback = callback

        keyboard = [
                [
                    InlineKeyboardButton("Open", callback_data='open'),
                #    InlineKeyboardButton("Option 2", callback_data='2')
                ],
                #[
                #    InlineKeyboardButton("Option 3", callback_data='3')
                #]
        ]
        self.reply_markup = InlineKeyboardMarkup(keyboard)

        self.updater = Updater(
                token=settings["api_key"],
                use_context=True
                )
        self.dispatcher = self.updater.dispatcher

        chat_filter = Filters.chat(chat_id=settings["chat"])
        user_filter = Filters.user(settings["users"])

        self.start_handler = CommandHandler("start", self.start_cmd)
        self.open_handler = CommandHandler(
                "open",
                self.open_cmd,
                filters=(chat_filter and user_filter)
                )

        self.dispatcher.add_handler(self.start_handler)
        self.dispatcher.add_handler(self.open_handler)

        self.dispatcher.add_handler(CallbackQueryHandler(self.button_callback))

        self.main_thread = threading.Thread(target=self.thread_body)
        self.main_thread.start()
        return


    def thread_body(self):
        #while not self.exit:

        try:
            self.updater.start_polling()
        except Exception as e:
            print(e)

        return


    def close(self):
        self.exit = True
        self.updater.stop()
        self.main_thread.join()
        return


    def start_cmd(self, update, context):
        self.send_help_message(update, context)
        return


    def open_cmd(self, update, context):

        context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Opening"
                )

        self.callback()
        return


    def button_callback(self, update, context):

        query = update.callback_query

        # CallbackQueries need to be answered, even if no notification to the user is needed
        # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
        query.answer()

        self.callback()

        query.edit_message_text(text="Opening")
        self.send_help_message(update, context)
        return


    def send_help_message(self, update, context):
        context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Touch to open",
                reply_markup=self.reply_markup
                )
        return


def received(msg):
    print("mqtt message received")
    print("receiverd on {} msg: {}".format(msg.topic, msg.payload))
    return


def received_telegram():
    print("Sending message to {}".format(settings["cmd_topic"]))
    MQTT_OBJ.publish(settings["cmd_topic"], "TOGGLE")
    return


def signal_handler(sig, frame):
    print("ctrl-c received")
    my_exit()
    return


def my_exit():

    MQTT_OBJ.close()
    print("mqtt closed")

    if TEL_OBJ is not None:
        TEL_OBJ.close()
    print("telegram closed")

    sys.exit(0)
    return


def parse_config():

    res = {}

    res["addr"] = os.environ.get("MQTT_BROKER_ADDR", cfg.MQTT_BROKER_ADDR)
    res["port"] = os.environ.get("MQTT_BROKER_PORT", cfg.MQTT_BROKER_PORT)
    res["timeout"] = os.environ.get("MQTT_BROKER_TIMEOUT", cfg.MQTT_BROKER_TIMEOUT)
    res["chat"] = os.environ.get("ALLOWED_CHAT", cfg.ALLOWED_CHAT)
    res["api_key"] = os.environ.get("TELEGRAM_API_KEY", cfg.TELEGRAM_API_KEY)
    res["cmd_topic"] = os.environ.get("CMD_TOPIC", "")

    users = os.environ.get("ALLOWED_USERS")

    if users is not None:
        users = [x.strip() for x in users.split(",")]
    else:
        users = cfg.ALLOWED_USERS
    res["users"] = users

    return res



if __name__ == "__main__":

    settings = parse_config()

    print("settings")
    for r in settings:
        print(f"{r}: \"{settings[r]}\"")
    print("")

    sys.stdout.flush()

    signal.signal(signal.SIGINT, signal_handler)
    MQTT_OBJ = MqttClient(received, settings)
    TEL_OBJ = TelegramClient(received_telegram, settings)

    signal.pause()

    my_exit()
