FROM registry.access.redhat.com/ubi9/python-312@sha256:fc9702e64d88c030b19b2298a5b6604bd2a5ac9f210833691cdaac3a43e29a2d AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./
COPY ./python ./shared

RUN pip install uv && \
    uv sync --frozen --only-group bot && \
    uv pip install ./shared

FROM registry.access.redhat.com/ubi9/python-312@sha256:fc9702e64d88c030b19b2298a5b6604bd2a5ac9f210833691cdaac3a43e29a2d

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
