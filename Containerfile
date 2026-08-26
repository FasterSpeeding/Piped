FROM registry.access.redhat.com/ubi9/python-312@sha256:aebe03384391689993c42998836597e6161ac5340cbc84518c1b0528a1c59ea8 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:aebe03384391689993c42998836597e6161ac5340cbc84518c1b0528a1c59ea8

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
