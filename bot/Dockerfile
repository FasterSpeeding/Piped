FROM python:3.11.0

ARG app_id
ARG client_secret
ARG private_key
ARG webhook_secret
ENV CLIENT_ID=app_id
ENV CLIENT_SECRET=client_secret
ENV PRIVATE_KEY=private_key
ENV WEBHOOK_SECRET=webhook_secret

COPY ./main.py ./main.py
COPY ./requirements.txt ./requirements.txt

RUN python -m pip install --upgrade pip wheel
RUN python -m pip install -r requirements.txt

ENTRYPOINT ["python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
