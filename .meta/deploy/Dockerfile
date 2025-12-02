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
CMD ["make", "wakeup_anna"]
