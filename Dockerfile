FROM python:3.12.4

COPY ./bot/main.py ./main.py
COPY ./python ./shared
COPY ./bot/requirements.txt ./requirements.txt

RUN python -m pip install --no-cache-dir wheel && \
    python -m pip install --no-cache-dir -r requirements.txt && \
    python -m pip install ./shared

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT python -m uvicorn main:app --proxy-headers --host 0.0.0.0 --port 80
