# -*- coding: utf-8 -*-
# BSD 3-Clause License
#
# Copyright (c) 2020-2022, Faster Speeding
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import hmac
import os
import sys
import time
import typing
from collections import abc as collections

import dotenv
import fastapi
import httpx
import jwt
import pydantic

if sys.version_info < (3, 10):
    raise RuntimeError("Only supports Python 3.10+")

dotenv.load_dotenv()

APP_ID = os.environ["app_id"]
CLIENT_SECRET = os.environ["client_secret"].encode("UTF-8")
PRIVATE_KEY = jwt.jwk_from_pem(os.environ["private_key"].encode())
WEBHOOK_SECRET = os.environ["webhook_secret"]

app = fastapi.FastAPI()
http = httpx.AsyncClient()

jwt_instance = jwt.JWT()


class Repository:
    id: int  # noqa: VNE003
    full_name: str


class Webhook(pydantic.BaseModel):
    action: str


class Ping:
    ...


class PullRequest:
    ...


def auth_request() -> str:
    return jwt_instance.encode(
        {"iat": int(time.time()) - 60, "exp": int(time.time()) + 120, "iss": APP_ID}, PRIVATE_KEY, alg="RS256"
    )


# TODO: fix starlette's decorator type hints
@app.middleware("http")  # pyright: ignore [ reportUntypedFunctionDecorator ]
async def auth_middleware(
    request: fastapi.Request, call_next: collections.Callable[..., collections.Awaitable[typing.Any]]
) -> fastapi.Response:
    user_agent = request.headers.get("User-Agent", "")
    signature = request.headers.get("X-Hub-Signature-256")
    if not user_agent.startswith("GitHub-Hookshot/") or not signature:
        return fastapi.Response(content="Missing or invalid required header", status_code=404)

    digest = "sha256=" + hmac.new(CLIENT_SECRET, await request.body(), digestmod="sha256").hexdigest()

    if not hmac.compare_digest(signature, digest):
        return fastapi.Response(content="Signature invalid", status_code=401)

    return await call_next(request)


@app.post("/")
async def get(
    body: typing.Dict[str, str], request: fastapi.Request, x_github_event: str = fastapi.Header()
) -> fastapi.Response:
    match x_github_event:
        case _:
            print(x_github_event, body)

    return fastapi.Response(status_code=204)
