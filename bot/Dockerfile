FROM python:3.11.1

ARG app_id
ARG client_secret
ARG private_key
ARG webhook_secret
ENV CLIENT_ID=app_id
ENV CLIENT_SECRET=client_secret
ENV PRIVATE_KEY=private_key
ENV WEBHOOK_SECRET=webhook_secret

COPY ./bot/main.py ./main.py
COPY ./python ./shared
COPY ./bot/requirements.txt ./requirements.txt

RUN python -m pip install --no-cache-dir wheel && \
    python -m pip install --no-cache-dir -r requirements.txt && \
    python -m pip install ./shared

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
