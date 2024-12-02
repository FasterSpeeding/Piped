FROM registry.access.redhat.com/ubi9/python-312@sha256:116fc1952f0647e4f1f0d81b4f8dfcf4e8fcde735f095314a7532c7dc64bdf7f AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./
COPY ./python ./shared

RUN pip install uv && \
    uv sync --frozen --only-group bot && \
    uv pip install ./shared

FROM registry.access.redhat.com/ubi9/python-312@sha256:116fc1952f0647e4f1f0d81b4f8dfcf4e8fcde735f095314a7532c7dc64bdf7f

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
