FROM registry.access.redhat.com/ubi9/python-312@sha256:946e1165dde472e1ab670fee010db9eafb8011964358a06e0d370a0bc0b1f06b AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./
COPY ./python ./shared

RUN pip install uv && \
    uv sync --frozen --only-group bot && \
    uv pip install ./shared

FROM registry.access.redhat.com/ubi9/python-312@sha256:946e1165dde472e1ab670fee010db9eafb8011964358a06e0d370a0bc0b1f06b

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
