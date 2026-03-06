FROM registry.access.redhat.com/ubi9/python-312@sha256:296739d2ac81b73257716e4eec1a25409c00b46f8d387fc287669ba62a7c1bc2 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:296739d2ac81b73257716e4eec1a25409c00b46f8d387fc287669ba62a7c1bc2

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
