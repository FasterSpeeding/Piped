FROM registry.access.redhat.com/ubi9/python-312@sha256:ff373f4b42b662e99954adea770ca87b4ea963186cc752174ccb94aa08fa702d AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:ff373f4b42b662e99954adea770ca87b4ea963186cc752174ccb94aa08fa702d

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
