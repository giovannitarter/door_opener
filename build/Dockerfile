FROM python:3.10

ADD requirements.txt /root/
RUN pip install -r /root/requirements.txt

ADD src/ /root/

WORKDIR /root
ENTRYPOINT [ "python", "/root/bot.py" ]

