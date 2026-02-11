FROM registry.access.redhat.com/ubi9/python-312@sha256:bcdbab62d80f7dd88b4c2ce69a5cf8e9e1e367ac39b2e5d7f5d3f532d936ec80 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:bcdbab62d80f7dd88b4c2ce69a5cf8e9e1e367ac39b2e5d7f5d3f532d936ec80

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
