FROM registry.access.redhat.com/ubi9/python-312@sha256:5e80833fe6cca33826db27373f1cd119bcc32e9daa26afd6cca7aeae289cf156 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:5e80833fe6cca33826db27373f1cd119bcc32e9daa26afd6cca7aeae289cf156

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
