FROM registry.access.redhat.com/ubi9/python-312@sha256:fe1e89ce526b30cd4be26198b2243ef3f708adf3067839fe539e90eee9af1802 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:fe1e89ce526b30cd4be26198b2243ef3f708adf3067839fe539e90eee9af1802

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
