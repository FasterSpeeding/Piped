FROM registry.access.redhat.com/ubi9/python-312@sha256:e58da77627d3cd889c1fe862bac08f96da1698d0cff8e5e233d67aa9fd0083b5 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:e58da77627d3cd889c1fe862bac08f96da1698d0cff8e5e233d67aa9fd0083b5

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
