FROM python:3.11
EXPOSE 8080
WORKDIR /app

# install poetry
RUN ["pip", "install", "poetry"]

# install dependencies with poetry
COPY ../../pyproject.toml .
COPY ../../poetry.lock .
RUN ["poetry", "install"]

# copy source code
COPY ../../src src/
COPY ../../Makefile Makefile
COPY ../../README.md .

# run the app
CMD ["make", "wakeup_anna"]
