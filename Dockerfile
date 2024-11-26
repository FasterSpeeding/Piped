FROM python:3.13.0 AS install

WORKDIR /workspace

COPY ./bot/pyproject.toml ./
COPY ./bot/uv.lock ./
COPY ./python ./shared

RUN pip install uv && \
    uv sync --locked && \
    ./.venv/bin/python -m pip install ./shared

FROM python:3.13.0

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
