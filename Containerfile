FROM registry.access.redhat.com/ubi9/python-312@sha256:5672f8d77afd25befd51241daaafbad1d21350c101f5fdf41157430584fb2b5a AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:5672f8d77afd25befd51241daaafbad1d21350c101f5fdf41157430584fb2b5a

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
