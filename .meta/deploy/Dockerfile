FROM ghcr.io/astral-sh/uv:0.13.6-python3.15-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1 UV_PYTHON_DOWNLOADS=0

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project


FROM python:3.15-slim-trixie

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

# copy source code
COPY --from=builder --chown=nonroot:nonroot /app/.venv /app/.venv
COPY --chown=nonroot:nonroot src /app/src

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

USER nonroot
WORKDIR /app
EXPOSE 8080

# run the app
# 의존성은 빌드 시 설치한다. 부팅할 때 재설치하면 서버 시작이 늦어져
# Fly가 머신 시작 직후 확인하는 리스닝 소켓 검사(0.0.0.0:8080)를 통과하지 못할 수 있다.
CMD ["gunicorn", "--config", "src/gunicorn_config.py", "--chdir", "src", "anna:create_app()", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120"]
