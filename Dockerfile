FROM registry.access.redhat.com/ubi9/python-312@sha256:7eff0198911e53c3c67634e82e6c156e3bd491149721e998280f104b7a185772 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./
COPY ./python ./shared

RUN pip install uv && \
    uv sync --frozen --only-group bot && \
    uv pip install ./shared

FROM registry.access.redhat.com/ubi9/python-312@sha256:7eff0198911e53c3c67634e82e6c156e3bd491149721e998280f104b7a185772

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
