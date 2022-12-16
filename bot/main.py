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
import logging
import os
import pathlib
import subprocess  # noqa: S404
import sys
import tempfile
import time
import typing
from collections import abc as collections

import anyio
import dotenv
import fastapi
import httpx
import jwt
import starlette.middleware
import tomllib
from asgiref import typing as asgiref

if sys.version_info < (3, 11):
    raise RuntimeError("Only supports Python 3.10+")

_LOGGER = logging.getLogger("piped.bot")
_LOGGER.setLevel("INFO")

dotenv.load_dotenv()

APP_ID = os.environ["app_id"]
_client_name = os.environ.get("client_name", default="always-on-duty")
COMMIT_ENV = {
    "GIT_COMMITTER_NAME": f"{_client_name}[bot]",
    "GIT_COMMITTER_EMAIL": f"123456789+{_client_name}[bot]@users.noreply.github.com",
}
COMMIT_ENV["GIT_AUTHOR_NAME"] = COMMIT_ENV["GIT_COMMITTER_NAME"]
COMMIT_ENV["GIT_AUTHOR_EMAIL"] = COMMIT_ENV["GIT_COMMITTER_EMAIL"]
CLIENT_SECRET = os.environ["client_secret"].encode()
PRIVATE_KEY = jwt.jwk_from_pem(os.environ["private_key"].encode())
PYTHON_PATH = os.environ["python_path"]
WEBHOOK_SECRET = os.environ["webhook_secret"]
jwt_instance = jwt.JWT()


class _ProcessingIndex:
    __slots__ = ("_prs", "_repos")

    def __init__(self) -> None:
        self._prs: dict[str, anyio.CancelScope] = {}
        self._repos: dict[int, list[int]] = {}

    def _pr_id(self, repo_id: int, pr_id: int, /) -> str:
        return f"{repo_id}:{pr_id}"

    async def close(self) -> None:
        self._repos.clear()
        prs = self._prs
        self._prs = {}
        _LOGGER.info("Stopping all current calls")
        for scope in prs.values():
            scope.cancel()

        await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

    async def clear_for_repo(self, repo_id: int, /, *, repo_name: str | None = None) -> None:
        if prs := self._repos.get(repo_id):
            repo_name = repo_name or str(repo_id)
            _LOGGER.info("Stopping calls for all PRs in %s", repo_name)
            for pr_id in prs:
                self._prs.pop(self._pr_id(repo_id, pr_id)).cancel()

            await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

    async def stop_for_pr(self, repo_id: int, pr_id: int, /, *, repo_name: str | None = None) -> None:
        if pr := self._prs.pop(self._pr_id(repo_id, pr_id), None):
            repo_name = repo_name or str(repo_id)
            _LOGGER.info("Stopping call for %s:%s", repo_name, pr_id)
            pr.cancel()
            await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

    def start(self, repo_id: int, pr_id: int, /, *, repo_name: str | None = None) -> anyio.CancelScope:
        key = self._pr_id(repo_id, pr_id)
        repo_name = repo_name or str(repo_id)

        if pr := self._prs.pop(key, None):
            _LOGGER.info("Stopping previous call for for %s:%s", repo_name, pr_id)
            pr.cancel()

        _LOGGER.info("Starting call for %s:%s", repo_name, pr_id)
        scope = anyio.CancelScope()
        self._prs[key] = scope
        return scope


class _CachedReceive:
    __slots__ = ("_data", "_receive")

    def __init__(self, data: bytearray, receive: asgiref.ASGIReceiveCallable) -> None:
        self._data: bytearray | None = data  # TODO: should this be chunked?
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


def _find_headers(scope: asgiref.HTTPScope, headers: collections.Collection[bytes]) -> dict[bytes, bytes]:
    results: dict[bytes, bytes] = {}

    for header_name, header_value in scope["headers"]:
        header_name = header_name.lower()
        if header_name in headers:
            results[header_name] = header_value

            if len(results) == len(headers):
                break

    return results


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

        signature = _find_headers(scope, (b"x-hub-signature-256",)).get(b"x-hub-signature-256")
        if not signature:
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


async def _on_startup():
    app.state.index = _ProcessingIndex()
    app.state.session = httpx.AsyncClient()


async def _on_shutdown():
    await app.state.index.close()
    assert isinstance(app.state.session, httpx.AsyncClient)
    await app.state.session.aclose()


app = fastapi.FastAPI(middleware=[starlette.middleware.Middleware(AuthMiddleware)])
app.router.on_startup.append(_on_startup)
app.router.on_shutdown.append(_on_shutdown)


@app.post("/webhook")
async def post_webhook(
    body: dict[str, typing.Any],
    request: fastapi.Request,
    tasks: fastapi.BackgroundTasks,
    x_github_event: str = fastapi.Header(),
) -> fastapi.Response:
    assert isinstance(request.app.state.index, _ProcessingIndex)
    assert isinstance(request.app.state.session, httpx.AsyncClient)
    index = request.app.state.index
    session = request.app.state.session
    # TODO: check_run and check_suite?
    match x_github_event:
        case "pull_request":
            pass

        case "installation":
            if body["action"] == "removed":
                for repo in body["repositories_removed"]:
                    await index.clear_for_repo(int(repo["id"]))

            return fastapi.Response(status_code=204)

        case "installation_repositories":
            if body["action"] == "removed":
                for repo in body["repositories"]:
                    await index.clear_for_repo(int(repo["id"]))

            return fastapi.Response(status_code=204)

        case "installation_target" | "github_app_authorization":
            return fastapi.Response(status_code=204)

        case _:
            _LOGGER.info(
                "Ignoring unexpected event type %r. These events should be disabled for this app", x_github_event
            )
            return fastapi.Response("Event type not implemented", status_code=501)

    status_code = 204
    match body["action"]:
        case "closed":
            repo_data = body["repository"]
            await index.stop_for_pr(int(repo_data["id"]), int(body["number"]), repo_name=repo_data.get("full_name"))

        case "opened" | "reopened" | "synchronize":
            status_code = 202
            tasks.add_task(_process_repo, session, index, body)

        case _:
            pass

    return fastapi.Response(status_code=status_code)


def _auth_request() -> str:
    return jwt_instance.encode(
        {"iat": int(time.time()) - 60, "exp": int(time.time()) + 120, "iss": APP_ID}, PRIVATE_KEY, alg="RS256"
    )


def _read_toml(path: pathlib.Path) -> dict[str, typing.Any]:
    with path.open("rb") as file:
        return tomllib.load(file)


async def _process_repo(session: httpx.AsyncClient, index: _ProcessingIndex, body: dict[str, typing.Any]) -> None:
    repo_data = body["repository"]
    repo_id = int(repo_data["id"])
    pr_id = int(body["number"])
    full_name = repo_data.get("full_name") or str(repo_id)

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        with index.start(repo_id, pr_id, repo_name=full_name):
            temp_dir = await anyio.to_thread.run_sync(
                lambda: tempfile.TemporaryDirectory[str](ignore_cleanup_errors=True)
            )
            assert temp_dir
            temp_dir_path = pathlib.Path(temp_dir.name)
            token = _auth_request()

            head_name = body["pull_request"]["head"]["repo"]["full_name"]
            head_ref = body["pull_request"]["head"]["ref"]
            git_url = f"https://x-access-token:{token}@github.com/{head_name}"
            _LOGGER.info("Cloning %s:%s branch %s into %s", full_name, pr_id, head_ref, temp_dir_path)
            await anyio.run_process(
                ["git", "clone", git_url, "--depth", "1", "--branch", head_ref, temp_dir.name],
                stdout=sys.stdout,
                stderr=sys.stderr,
            )

            pyproject = await anyio.to_thread.run_sync(_read_toml, temp_dir_path / "pyproject.toml")
            bot_sessions = ((pyproject.get("tool") or {}).get("piped") or {}).get("bot_sessions")
            if not bot_sessions:
                _LOGGER.warn("Received event from %s repo with no bot_sessions", full_name)
                return

            # TODO: this is currently a RCE so this needs to make sure piped and noxfile.py haven't
            # been changed
            # TODO: filter to work out which actions should even be ran.
            # TODO: pipe output to file to send in comment
            await anyio.run_process(
                [PYTHON_PATH, "-m", "nox", "-s", *bot_sessions], cwd=temp_dir_path, stdout=sys.stdout, stderr=sys.stderr
            )

            await anyio.run_process(["git", "add", "."], cwd=temp_dir_path, stdout=sys.stdout, stderr=sys.stderr)
            try:
                await anyio.run_process(
                    ["git", "commit", "-am", "Reformatting PR"],
                    cwd=temp_dir_path,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    env=COMMIT_ENV,
                )

            except subprocess.CalledProcessError as exc:
                # 1 indicates no changes were found.
                if exc.returncode != 1:
                    raise

            else:
                await anyio.run_process(["git", "push"], cwd=temp_dir_path, stdout=sys.stdout, stderr=sys.stderr)
    finally:
        if temp_dir:
            # TODO: this just fails on Windows sometimes
            await anyio.to_thread.run_sync(temp_dir.cleanup)
