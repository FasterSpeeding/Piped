FROM registry.access.redhat.com/ubi9/python-312@sha256:3da39d0c938994161bdf9b6b13eb2eacd9a023c86dd5166f3da31df171c88780 AS install

WORKDIR /workspace

COPY ./pyproject.toml ./
COPY ./uv.lock ./

RUN pip install uv && \
    uv sync --frozen

FROM registry.access.redhat.com/ubi9/python-312@sha256:3da39d0c938994161bdf9b6b13eb2eacd9a023c86dd5166f3da31df171c88780

WORKDIR /workspace

COPY --from=install /workspace/.venv ./venv
COPY ./bot/main.py ./main.py

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["./venv/bin/python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
