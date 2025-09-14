FROM registry.access.redhat.com/ubi9/python-312@sha256:a3af61fdae215cd8d8f67f8f737064b353dc0592567099de48b3c2563314810d AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --no-install-project --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:a3af61fdae215cd8d8f67f8f737064b353dc0592567099de48b3c2563314810d

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
