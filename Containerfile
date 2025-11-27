FROM registry.access.redhat.com/ubi9/python-312@sha256:92c71d1e64cf84b9aa6e8e81555397175b9367298b456d24eac5b55ab41fdab9 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:92c71d1e64cf84b9aa6e8e81555397175b9367298b456d24eac5b55ab41fdab9

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
