
import os

envvars = [
    ("MQTT_BROKER_ADDR", ""),
    ("MQTT_BROKER_PORT", ""),
    ("POWER_TOPIC", ""),
    ("RELAY_TOPIC", ""),
    ("MQTT_BROKER_TIMEOUT", ""),
    ("CHAT_ID", ""),
    ("POWER_WINDOW_SIZE", 60),
    ("KEEPALIVE_URL", None),
    ("TELEGRAM_TOKEN", None),
    ("ALLOWED_USERS", None),
    ]


def parse_config():

    res = {}

    for k, def_value in envvars:
        res[k] = os.environ.get(k, def_value)

    users = res.get("ALLOWED_USERS")
    if users is not None:
        users = users.strip()
        users = [x.strip() for x in users.split(",")]
    res["users"] = users

    return res
