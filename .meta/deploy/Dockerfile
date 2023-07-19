FROM python:3.11

WORKDIR /app

COPY ../../requirements.txt requirements.txt
RUN ["pip", "install", "-r", "requirements.txt"]

COPY ../../src src/
COPY ../../Makefile Makefile

EXPOSE 8080

CMD ["make", "wakeup_remote_anna"]
