
import os

envvars = [
    ("MQTT_BROKER_ADDR", ""),
    ("MQTT_BROKER_PORT", ""),
    ("STATE_TOPIC", ""),
    ("RELAY_TOPIC", ""),
    ("MQTT_BROKER_TIMEOUT", ""),
    ("CHAT_ID", ""),
    ("POWER_WINDOW_SIZE", 60),
    ("KEEPALIVE_URL", None),
    ("TELEGRAM_TOKEN", None),
    ("ALLOWED_USERS", None),
    ]


def validate_config(cfg):

    res = {}

    for k, def_value in envvars:
        res[k] = cfg.get(k, def_value)

    users = res.get("ALLOWED_USERS")
    if users is not None:
        users = users.strip()
        users = [x.strip() for x in users.split(",")]
    res["users"] = users

    return res


def parse_config_env():
    return validate_config(os.environ)


def parse_config_file(file):

    res = {}
    with open(file, "r") as fd:
        text = fd.readlines()
        for ln in text:
            fields = ln.strip().split("=", maxsplit=1)
            if len(fields) == 2:
                res[fields[0]] = fields[1]

    return validate_config(res)
