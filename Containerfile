FROM registry.access.redhat.com/ubi9/python-312@sha256:a0a5885769d5a8c5123d3b15d5135b254541d4da8e7bc445d95e1c90595de470 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:a0a5885769d5a8c5123d3b15d5135b254541d4da8e7bc445d95e1c90595de470

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
