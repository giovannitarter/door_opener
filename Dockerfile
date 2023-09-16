FROM python:latest

RUN pip install paho-mqtt python-telegram-bot==13.15 requests

RUN mkdir /root/door_opener
ADD apriporta.py /root/door_opener/
ADD config.py /root/door_opener/

WORKDIR /root
ENTRYPOINT [ "python", "/root/door_opener/apriporta.py" ]

