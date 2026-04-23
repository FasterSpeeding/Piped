FROM registry.access.redhat.com/ubi9/python-312@sha256:0abad955c2c2e4575dc8987d76b8c49a7dd8e0679063e3118dab03c54528232f AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:0abad955c2c2e4575dc8987d76b8c49a7dd8e0679063e3118dab03c54528232f

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
