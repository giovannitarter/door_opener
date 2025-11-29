#!/usr/bin/env python3

import logging
import traceback
from telegram import Update
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
        ApplicationBuilder, ContextTypes,
        CommandHandler, CallbackQueryHandler
        )
from telegram.ext import filters

import signal
import asyncio
import aiomqtt
import json
import time
import requests
import argparse
import os

import config


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger('httpx').setLevel(logging.ERROR)


kbd = InlineKeyboardMarkup(
        [

            [
                # InlineKeyboardButton("/start", callback_data="start"),
                InlineKeyboardButton("/open", callback_data="open"),
            ]
        ],
    )


class Bot():

    def __init__(self, loop):
        self.shutdown_evt = asyncio.Event()
        self.application = ApplicationBuilder().token(
                cfg["TELEGRAM_TOKEN"]
                ).build()

        msg_filter = filters.User(username=cfg["ALLOWED_USERS"].split(","))

        start_handler = CommandHandler('start', self.start_hnd, msg_filter)
        open_handler = CommandHandler('open', self.open_hnd, msg_filter)
        button_handler = CallbackQueryHandler(self.button_hnd)

        self.application.add_handler(start_handler)
        self.application.add_handler(open_handler)
        self.application.add_handler(button_handler)

        self.mqtt = None
        return

    def set_mqtt(self, mqtt):
        self.mqtt = mqtt
        return

    async def start_hnd(self, update: Update,
                        context: ContextTypes.DEFAULT_TYPE):

        logging.info(f"start {update.effective_chat.id}")

        await update.message.reply_text(
                "Available actions:",
                reply_markup=kbd
                )

    async def open_hnd(self, update: Update,
                       context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        logging.info(f"open {chat_id}")
        if self.mqtt:
            await self.mqtt.publish(cfg["RELAY_TOPIC"], payload="TOGGLE")

            await context.bot.send_message(
                chat_id=chat_id,
                text="Opening",
                reply_markup=kbd
                )

    async def button_hnd(self, update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        if query.data == "open":
            if self.mqtt:
                await self.mqtt.publish(cfg["RELAY_TOPIC"], payload="TOGGLE")
                await query.message.reply_text(
                    text="Opening",
                    reply_markup=kbd
                )


async def run_telegram(enbot):

    async with enbot.application:

        await enbot.application.start()
        await enbot.application.updater.start_polling()

        logging.info("started")
        await enbot.shutdown_evt.wait()

        await enbot.application.updater.stop()
        await enbot.application.stop()


async def shutdown(signal, enbot):
    """Cleanup tasks tied to the service's shutdown."""

    logging.info("shutdown callback!")

    logging.info(f"Received exit signal {signal.name}...")

    enbot.shutdown_evt.set()

    if enbot.application.running:
        await enbot.application.stop()

    tasks = [t for t in asyncio.all_tasks() if t is not
             asyncio.current_task()]

    [task.cancel() for task in tasks]

    logging.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


def exc_handler(loop, context):
    logging.error(context.get("exception"))
    logging.error(context["message"])
    loop.stop()
    return


def parse_json_message(payload):

    res = None

    try:
        text = payload.decode("utf-8")
        res = json.loads(text)

    except json.JSONDecodeError:
        logging.error("cannot decode json")
        logging.error(f"{payload}")

    except Exception:
        logging.error("generic error in parsing json")
        logging.error(traceback.format_exc())

    return res


async def handle_message(enbot, message):
    _ = parse_json_message(message.payload)
    # logging.info(json.dumps(msg, indent=4))

    _ = await loop.run_in_executor(
        None,
        requests.get,
        cfg["KEEPALIVE_URL"],
        )

    return


async def run_mqtt(enbot):

    while not enbot.shutdown_evt.is_set():
        try:
            async with aiomqtt.Client(cfg["MQTT_BROKER_ADDR"]) as client:
                enbot.set_mqtt(client)
                await client.subscribe(cfg["STATE_TOPIC"])
                async for message in client.messages:
                    await handle_message(enbot, message)

        except aiomqtt.MqttError:
            logging.error("Mqtt connection lost, reconnecting")
            enbot.set_mqtt(None)
            asyncio.sleep(2)

        except Exception:
            logging.error("generic error in mqtt loop")
            logging.error(traceback.format_exc())


if __name__ == "__main__":

    time.tzset()

    parser = argparse.ArgumentParser(
            prog='Energy notifier telegram bot',
            description='What the program does',
            epilog='Text at the bottom of help'
            )
    parser.add_argument("-c", '--conf')
    args = parser.parse_args()

    if args.conf is None:
        cfg = config.parse_config_env()
    elif os.path.exists(args.conf):
        cfg = config.parse_config_file(args.conf)
    else:
        print("Cannot parse config")
        exit(1)

    logging.info(json.dumps(cfg, indent=4))

    loop = asyncio.get_event_loop()
    bt = Bot(loop)

    for s in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(
            s,
            lambda s=s, bt=bt: asyncio.create_task(shutdown(s, bt))
        )
    loop.set_exception_handler(exc_handler)

    loop.create_task(run_telegram(bt))
    loop.create_task(run_mqtt(bt))

    try:
        loop.run_forever()
    finally:
        logging.info("Successfully shutdown service")
        loop.close()
