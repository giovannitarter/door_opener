FROM python:3.10

ADD requirements.txt /root/
RUN pip install -r /root/requirements.txt

RUN mkdir /root/door_opener
ADD door_opener.py /root/
ADD config.py /root/

WORKDIR /root
ENTRYPOINT [ "python", "/root/door_opener.py" ]

