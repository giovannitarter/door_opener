#!/usr/bin/env python3


import logging
import traceback
from telegram import Update
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.ext import filters

import signal
import asyncio
import aiomqtt
import json
import time
import requests

import config


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger('httpx').setLevel(logging.ERROR)


kbd = InlineKeyboardMarkup(
        [

            [

                #InlineKeyboardButton("/start", callback_data="start"),
                InlineKeyboardButton("/open", callback_data="open"),
                InlineKeyboardButton("/status", callback_data="status"),
            ]
        ],
    )


class EnergyBot():

    def __init__(self, loop):
        self.shutdown_evt = asyncio.Event()
        self.application = ApplicationBuilder().token(
                cfg["TELEGRAM_TOKEN"]
                ).build()

        msg_filter = filters.Chat(username=cfg["ALLOWED_USERS"])

        start_handler = CommandHandler('start', self.start_hnd, msg_filter)
        status_handler = CommandHandler('status', self.status_hnd, msg_filter)
        open_handler = CommandHandler('open', self.open_hnd, msg_filter)
        button_handler = CallbackQueryHandler(self.button_hnd)

        self.application.add_handler(start_handler)
        self.application.add_handler(open_handler)
        self.application.add_handler(status_handler)
        self.application.add_handler(button_handler)

        self.last_sample = None

        self.window = []
        self.mqtt = None


    def set_mqtt(self, mqtt):
        self.mqtt = mqtt
        return


    def clean_window(self):
        return



    def add_sample(self, sample):

        stime, svalue = sample

        self.last_sample_ltime = time.time()
        self.last_sample_time = stime

        self.window = [s for s in self.window if s[0] > stime - cfg["POWER_WINDOW_SIZE"]]
        self.window.append((stime, svalue, self.last_sample_ltime))
        return


    def get_curr_power(self):
        res = None

        ctime = time.time()
        self.window = [
            x for x in self.window if x[2] > ctime - cfg["POWER_WINDOW_SIZE"]
            ]

        if len(self.window) > 1:
            watth = self.window[-1][1] - self.window[0][1]
            etime = self.window[-1][0] - self.window[0][0]

            #res = watth / (etime / 3600.) # watt
            res = watth * 3600. / etime # watt
        return res

    async def start_hnd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        await update.message.reply_text(
                "Available actions:",
                reply_markup=kbd
                )


    async def status_hnd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        logging.info(f"status {chat_id}")
        cpow = self.get_curr_power()

        if cpow:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"status, cpower: {cpow:.2f}"
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"status, not enough data"
                )

    async def open_hnd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        logging.info(f"open {chat_id}")
        if self.mqtt:
            await self.mqtt.publish(cfg["RELAY_TOPIC"], payload="TOGGLE")

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Opening",
                reply_markup=kbd
                )

    async def button_hnd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()


        #logging.info(f"message: {query.message}")
        #logging.info(f"inline_message_id: {query.inline_message_id}")

        if query.data == "status":
            cpow = self.get_curr_power()

            if cpow:
                await query.message.reply_text(
                        text=f"status, cpower: {cpow:.2f}",
                        reply_markup=kbd
                    )
            else:
                await query.message.reply_text(
                        text=f"status, not enough data",
                        reply_markup=kbd
                        )


        elif query.data == "open":
            if self.mqtt:
                await self.mqtt.publish(cfg["RELAY_TOPIC"], payload="TOGGLE")
                await query.message.reply_text(
                    text=f"Opening",
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

    logging.info(f"shutdown callback!")

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
    #logging.error(traceback.print_tb())
    loop.stop()
    return


def parse_json_message(payload):

    res = None

    try:
        text = payload.decode("utf-8")
        res = json.loads(text)

    except json.JSONDecodeError:
        logging.error("cannot decode json")

    except Exception as e:
        logging.error("generic error in parsing json")
        logging.error(traceback.format_exc())

    return res


def extract_sample(msg):

    res = None
    stime = msg.get("Time")
    cnt = msg.get("COUNTER", {}).get("C4")
    if stime and cnt:
        stime = time.strptime(stime, "%Y-%m-%dT%H:%M:%S")
        #stime.tm_isdst = False
        stime = time.mktime(stime)
        cnt = int(cnt)
        res = (stime, cnt)
    return res



async def handle_message(enbot, message):

    msg = parse_json_message(message.payload)
    if msg:
        #logging.info(json.dumps(msg, indent=4))
        smp = extract_sample(msg)

        cpow = None
        if smp:
            cpow = enbot.get_curr_power()
            str_time = time.strftime(
                    '%Y-%m-%d %H:%M:%S',
                    time.localtime(smp[0])
                    )
            logging.info(f"time: {str_time} counter: {smp[1]}, cpow: {cpow}")
            #logging.info(f"time: {smp[0]} counter: {smp[1]}, cpow: {cpow}")

        if smp:
            enbot.add_sample(smp)


        if enbot.last_sample and smp:

            ctime, cvalue = smp
            ltime, lvalue = enbot.last_sample

            etime = ctime - ltime
            cnt = cvalue - lvalue

            cpow = cnt * 3600 / etime
            if etime < 15 and cpow > 3900:
                logging.info("sending msg")

                await enbot.application.bot.send_message(
                        cfg["CHAT_ID"],
                        f"Power above theshold! current power: {cpow}"
                        )

        if smp:
            enbot.last_sample = smp
            kreq = await loop.run_in_executor(
                    None,
                    requests.get,
                    cfg["KEEPALIVE_URL"],
                    )
    return


async def run_mqtt(enbot):

    # loop = asyncio.get_running_loop()

    while not enbot.shutdown_evt.is_set():
        try:
            async with aiomqtt.Client(cfg["MQTT_BROKER_ADDR"]) as client:
                enbot.set_mqtt(client)
                async with client.messages() as messages:
                    await client.subscribe(cfg["POWER_TOPIC"])
                    async for message in messages:
                        await handle_message(enbot, message)

        except aiomqtt.MqttError:
            logging.error("Mqtt connection lost, reconnecting")
            enbot.set_mqtt(None)
            asyncio.sleep(2)

        except Exception:
            logging.error("generic error in mqtt loop")
            logging.error(traceback.format_exc())


if __name__ == "__main__":

    #os.environ["TZ"] = "Europe/Rome"
    time.tzset()

    cfg = config.parse_config()

    loop = asyncio.get_event_loop()
    eb = EnergyBot(loop)

    for s in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(
            s,
            lambda s=s, eb=eb: asyncio.create_task(shutdown(s, eb))
        )
    loop.set_exception_handler(exc_handler)
    #loop.create_task(lambda eb=eb: run_telegram(eb))
    #loop.create_task(lambda eb=eb: run_mqtt(eb))

    loop.create_task(run_telegram(eb))
    loop.create_task(run_mqtt(eb))

    try:
        loop.run_forever()
    finally:
        logging.info("Successfully shutdown service")
        #async mqtt loop"loop.close()
        loop.close()
