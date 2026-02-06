FROM registry.access.redhat.com/ubi9/python-312@sha256:d14dd0aa47b885e9e6d229c641cda40008c5d46ca90b02df1f5faf8baf178125 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:d14dd0aa47b885e9e6d229c641cda40008c5d46ca90b02df1f5faf8baf178125

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
