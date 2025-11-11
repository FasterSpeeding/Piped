FROM registry.access.redhat.com/ubi9/python-312@sha256:f9a256f5dc66ac635d854b4d80cb720846d6120606422fccbd35de1d69affd86 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:f9a256f5dc66ac635d854b4d80cb720846d6120606422fccbd35de1d69affd86

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
