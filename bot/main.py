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
import starlette.middleware
from asgiref import typing as asgiref

if sys.version_info < (3, 10):
    raise RuntimeError("Only supports Python 3.10+")

dotenv.load_dotenv()

APP_ID = os.environ["app_id"]
CLIENT_SECRET = os.environ["client_secret"].encode()
PRIVATE_KEY = jwt.jwk_from_pem(os.environ["private_key"].encode())
WEBHOOK_SECRET = os.environ["webhook_secret"]


class _CachedReceive:
    __slots__ = ("_data", "_receive")

    def __init__(self, data: bytearray, receive: asgiref.ASGIReceiveCallable) -> None:
        self._data: typing.Optional[bytearray] = data  # TODO: should this be chunked?
        self._receive = receive  # TODO: check this behaviour

    async def __call__(self) -> asgiref.ASGIReceiveEvent:
        if not self._data:
            return await self._receive()

        data = self._data
        self._data = None
        return {"type": "http.request", "body": data, "more_body": False}


async def _error_response(send: asgiref.ASGISendCallable, body: bytes, /, *, status_code: int = 400) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"text/plain; charset=UTF-8")],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


# TODO: check user agent header starts with "GitHub-Hookshot/"?
class AuthMiddleware:
    __slots__ = ("app",)

    # starlette.types.ASGIApp is more appropriate but less concise than this callable type.
    def __init__(
        self,
        app: collections.Callable[
            [asgiref.Scope, asgiref.ASGIReceiveCallable, asgiref.ASGISendCallable], collections.Awaitable[None]
        ],
    ) -> None:
        self.app = app

    async def __call__(
        self, scope: asgiref.Scope, receive: asgiref.ASGIReceiveCallable, send: asgiref.ASGISendCallable
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for header_name, header_value in scope["headers"]:
            if header_name.lower() == b"x-hub-signature-256":
                signature = header_value
                break

        else:
            await _error_response(send, b"Missing signature header")
            return

        more_body = True
        payload = bytearray()
        while more_body:
            event = await receive()
            match event:
                case {"type": "http.request"}:
                    more_body = event.get("more_body", False)
                    payload.extend(event.get("body") or b"")
                case _:
                    raise NotImplementedError

        digest = "sha256=" + hmac.new(CLIENT_SECRET, payload, digestmod="sha256").hexdigest()

        if not hmac.compare_digest(signature.decode(), digest):
            await _error_response(send, b"Invalid signature", status_code=401)
            return

        await self.app(scope, _CachedReceive(payload, receive), send)


app = fastapi.FastAPI(middleware=[starlette.middleware.Middleware(AuthMiddleware)])
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


@app.post("/webhook")
async def post_webhook(
    body: typing.Dict[str, typing.Any], request: fastapi.Request, x_github_event: str = fastapi.Header()
) -> fastapi.Response:
    match x_github_event:
        case _:
            pass

    return fastapi.Response(status_code=204)
