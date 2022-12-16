FROM python:3.11.0

ARG app_id
ARG client_secret
ARG private_key
ARG python_path="python"
ARG webhook_secret
ENV CLIENT_ID=app_id
ENV CLIENT_SECRET=client_secret
ENV PRIVATE_KEY=private_key
ENV PYTHON_PATH=python_path
ENV WEBHOOK_SECRET=webhook_secret

COPY ./main.py ./main.py
COPY ./requirements.txt ./requirements.txt

RUN python -m pip install --upgrade pip wheel
RUN python -m pip install -r requirements.txt

# TODO: https://github.com/ome/devspace/issues/38?
ENTRYPOINT ["python", "-m", "uvicorn", "main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "80"]
