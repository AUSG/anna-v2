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
# 의존성은 빌드 시 설치한다. 부팅할 때 재설치하면 서버 시작이 늦어져
# Fly가 머신 시작 직후 확인하는 리스닝 소켓 검사(0.0.0.0:8080)를 통과하지 못할 수 있다.
CMD ["poetry", "run", "gunicorn", "--config", "src/gunicorn_config.py", "--chdir", "src", "anna:create_app()", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120"]
