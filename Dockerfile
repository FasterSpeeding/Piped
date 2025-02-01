FROM registry.access.redhat.com/ubi9/python-312@sha256:b642db8b1f0f9dca7bbe6999db7ac4c96cf3036833fc344af092268afbb02893 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./
COPY ./python ./shared

RUN pip install uv && \
    uv sync --frozen --only-group bot && \
    uv pip install ./shared

FROM registry.access.redhat.com/ubi9/python-312@sha256:b642db8b1f0f9dca7bbe6999db7ac4c96cf3036833fc344af092268afbb02893

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
