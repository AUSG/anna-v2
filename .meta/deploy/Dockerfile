FROM python:3.10

WORKDIR /app

COPY ../../requirements.txt requirements.txt
RUN ["pip", "install", "-r", "requirements.txt"]

COPY ../../src src/
COPY ../../env env/
COPY ../../Makefile Makefile

EXPOSE 8080

CMD ["make", "run_deploy"]
