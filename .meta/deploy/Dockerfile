FROM python:3.11
EXPOSE 8080
WORKDIR /app

# install poetry
RUN ["pip", "install", "poetry"]

# copy source code
COPY ../../pyproject.toml .
COPY ../../poetry.lock .
COPY ../../src src/
COPY ../../Makefile Makefile
COPY ../../README.md .

# install dependencies with poetry
RUN ["poetry", "install"]

# run the app
# 의존성은 빌드 시 이미 설치됨 — 부팅 시 재설치 없이 곧바로 서버를 띄워야
# fly가 머신 시작 직후 검사하는 리스닝 소켓 체크(0.0.0.0:8080)를 통과한다
CMD ["poetry", "run", "gunicorn", "--chdir", "src", "anna:flask_app", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120"]
