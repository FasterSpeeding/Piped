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

import contextlib
import dataclasses
import datetime
import enum
import hmac
import io
import logging
import math
import os
import pathlib
import subprocess  # noqa: S404
import sys
import tempfile
import time
import tomllib
import types
import typing
import zipfile
from collections import abc as collections
from typing import Self

import anyio
import dotenv
import fastapi
import httpx
import jwt
import pydantic
import starlette.middleware
from anyio.streams import memory as streams
from asgiref import typing as asgiref
from dateutil import parser as dateutil

if sys.version_info < (3, 11):
    raise RuntimeError("Only supports Python 3.10+")

_LOGGER = logging.getLogger("piped.bot")
_LOGGER.setLevel("INFO")

dotenv.load_dotenv()

_username = os.environ.get("client_name", default="always-on-duty") + "[bot]"

with httpx.Client() as client:
    _user_id = int(client.get(f"https://api.github.com/users/{_username}").json()["id"])

APP_ID = os.environ["app_id"]
COMMIT_ENV = {
    "GIT_AUTHOR_NAME": _username,
    "GIT_AUTHOR_EMAIL": f"{_user_id}+{_username}@users.noreply.github.com",
    "GIT_COMMITTER_NAME": _username,
}
COMMIT_ENV["GIT_COMMITTER_EMAIL"] = COMMIT_ENV["GIT_AUTHOR_EMAIL"]
CLIENT_SECRET = os.environ["client_secret"].encode()
PYTHON_PATH = os.environ["python_path"]
WEBHOOK_SECRET = os.environ["webhook_secret"]
jwt_instance = jwt.JWT()


class _Config(pydantic.BaseModel):
    bot_actions: set[str] = pydantic.Field(
        default_factory=lambda: {"Freeze PR dependency changes", "Resync piped", "Reformat PR code"}
    )


class _ProcessingIndex:
    """Index of the PRs being processed."""

    __slots__ = ("_prs", "_repos")

    def __init__(self) -> None:
        self._prs: dict[str, anyio.CancelScope] = {}
        self._repos: dict[int, list[int]] = {}

    def _pr_id(self, repo_id: int, pr_id: int, /) -> str:
        return f"{repo_id}:{pr_id}"

    async def close(self) -> None:
        """Cancel all active PR processing tasks."""
        self._repos.clear()
        prs = self._prs
        self._prs = {}
        _LOGGER.info("Stopping all current calls")
        for scope in prs.values():
            scope.cancel()

        await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

    async def clear_for_repo(self, repo_id: int, /, *, repo_name: str | None = None) -> None:
        """Cancel the active PR processing tasks for a Repo.

        Parameters
        ----------
        repo_id
            ID of the repo to cancel the active tasks for.
        repo_name
            Name of the repo to cancel the active tasks for.

            Used for logging.
        """
        if prs := self._repos.get(repo_id):
            repo_name = repo_name or str(repo_id)
            _LOGGER.info("Stopping calls for all PRs in %s", repo_name)
            for pr_id in prs:
                self._prs.pop(self._pr_id(repo_id, pr_id)).cancel()

            await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

    async def stop_for_pr(self, repo_id: int, pr_id: int, /, *, repo_name: str | None = None) -> None:
        """Cancel the active processing task for a PR.

        Parameters
        ----------
        repo_id
            ID of the repo to cancel an active task in.
        pr_id
            ID of the PR to cancel the active processing task for.
        repo_name
            Name of the repo to cancel an active task in.

            Use for logging.
        """
        if pr := self._prs.pop(self._pr_id(repo_id, pr_id), None):
            repo_name = repo_name or str(repo_id)
            _LOGGER.info("Stopping call for %s:%s", repo_name, pr_id)
            pr.cancel()
            await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

    def start(self, repo_id: int, pr_id: int, /, *, repo_name: str | None = None) -> anyio.CancelScope:
        """Create a cancel scope for processing a specific PR.

        This will cancel any previous processing task for the passed PR.

        Parameters
        ----------
        repo_id
            ID of the repo to start a processing task for.
        pr_id
            ID of the pull request to start a processing task for.
        repo_name
            Name of the repo this task is in.

            Use for logging.

        Returns
        -------
        anyio.CancelScope
            Cancel scope to use for this task.
        """
        key = self._pr_id(repo_id, pr_id)
        repo_name = repo_name or str(repo_id)

        if pr := self._prs.pop(key, None):
            _LOGGER.info("Stopping previous call for for %s:%s", repo_name, pr_id)
            pr.cancel()

        _LOGGER.info("Starting call for %s:%s", repo_name, pr_id)
        scope = anyio.CancelScope()
        self._prs[key] = scope
        return scope


class _Tokens:
    """Index of the Github API tokens this application has authorised."""

    __slots__ = ("_installation_tokens", "_private_key")

    def __init__(self) -> None:
        self._installation_tokens: dict[int, tuple[datetime.datetime, str]] = {}
        self._private_key = jwt.jwk_from_pem(os.environ["private_key"].encode())

    def app_token(self) -> str:
        """Generate an application app token.

        !!! warning
            This cannot does not provide authorization for repos or
            organisations the application is authorised in.
        """
        now = int(time.time())
        token = jwt_instance.encode(
            {"iat": now - 60, "exp": now + 60 * 3, "iss": APP_ID}, self._private_key, alg="RS256"
        )
        return token

    async def installation_token(self, http: httpx.AsyncClient, installation_id: int, /) -> str:
        """Authorise an installation specific token.

        This is used to authorise organisation and repo actions and will return
        cached tokens.

        Parameters
        ----------
        http
            REST client to use to authorise the token.
        installation_id
            ID of the installation to authorise a token for.
        """
        if token_info := self._installation_tokens.get(installation_id):
            expire_by = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(seconds=60)
            if token_info[0] >= (expire_by):
                return token_info[1]

        # TODO: do we need/want to use an async lock here?
        response = await _request(
            http,
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            json={"permissions": {"actions": "read", "checks": "write", "contents": "write", "workflows": "write"}},
            token=self.app_token(),
        )
        data = response.json()
        token = data["token"]
        self._installation_tokens[installation_id] = (dateutil.isoparse(data["expires_at"]), token)
        return token


async def _request(
    http: httpx.AsyncClient,
    method: typing.Literal["GET", "PATCH", "POST", "DELETE"],
    endpoint: str,
    /,
    *,
    json: dict[str, typing.Any] | None = None,
    query: dict[str, str] | None = None,
    token: str | None = None,
) -> httpx.Response:
    """Make a request to Github's API.

    Parameters
    ---------
    http
        The REST client to use to make the request.
    endpoint
        Endpoint to request to.

        This will be appended to `"https://api.github.com"` if it doesn't
        start with `"https://"`.
    json
        Dict of the JSON payload to include in this request.
    query
        Dict of the query string parameters to include for this request.
    token
        The authorisation token to use.
    """
    if not endpoint.startswith("https://"):
        endpoint = f"https://api.github.com{endpoint}"

    headers = {"X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if json:
        headers["Content-Type"] = "application/vnd.github+json"

    response = await http.request(method, endpoint, follow_redirects=True, headers=headers, json=json, params=query)
    response.raise_for_status()
    return response


class _CachedReceive:
    """Helper ASGI event receiver which first returned the cached request body."""

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
    """Helper function for returning a quick error response.

    Parameters
    ----------
    send
        The ASGI send callback to use to send this response.
    body
        The error message.
    status_code
        The error's status code.
    """
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"text/plain; charset=UTF-8")],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


def _find_headers(scope: asgiref.HTTPScope, headers: collections.Collection[bytes]) -> dict[bytes, bytes]:
    """Helper function for extracting specific headers from an ASGI request.

    Parameters
    ----------
    scope
        The ASGI HTTP scope payload to get the headers from.
    headers
        Collection of the headers to find.
    """
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
    """ASGI signature authorisation middleware."""

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


@dataclasses.dataclass(slots=True)
class _Workflow:
    name: str
    workflow_id: int


class _WorkflowAction(str, enum.Enum):
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    REQUESTED = "requested"


class _WorkflowDispatch:
    """Workflow dispatch tracker."""

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: dict[
            tuple[int, int, str], streams.MemoryObjectSendStream[tuple[int, str, _WorkflowAction]]
        ] = {}

    def consume_event(self, body: dict[str, typing.Any], /) -> None:
        """Dispatch a workflow_run event.

        Parameters
        ----------
        body
            Dict body of the workflow_run event.
        """
        head_repo_id = int(body["workflow_run"]["head_repository"]["id"])
        head_sha = body["workflow_run"]["head_sha"]
        repo_id = int(body["repository"]["id"])

        if send := self._listeners.get((repo_id, head_repo_id, head_sha)):
            action = _WorkflowAction(body["action"])
            name = body["workflow_run"]["name"]
            workflow_id = int(body["workflow_run"]["id"])
            send.send_nowait((workflow_id, name, action))

    @contextlib.contextmanager
    def track_workflows(
        self, repo_id: int, head_repo_id: int, head_sha: str, /
    ) -> collections.Generator["_IterWorkflows", None, None]:
        """Async context manager which manages tracking the workflows for a PR.

        Parameters
        ----------

        Returns
        -------
        _IterWorkflows
            Async iterable of the received workflow finishes.

            `_IterWorkflows.filter_names` should be used to set this to filter
            for specific names before iterating over this.
        """
        # TODO: the typing for this function is wrong, we should be able to just pass item_type.
        key = (repo_id, head_repo_id, head_sha)
        send, recv = anyio.create_memory_object_stream(math.inf, item_type=tuple[int, str, _WorkflowAction])
        self._listeners[key] = send

        yield _IterWorkflows(recv)

        send.close()
        del self._listeners[key]


class _IterWorkflows:
    """Async iterable of received workflow finishes."""

    __slots__ = ("_filter", "_recv")

    def __init__(self, recv: streams.MemoryObjectReceiveStream[tuple[int, str, _WorkflowAction]], /) -> None:
        self._filter: collections.Collection[str] = ()
        self._recv = recv

    async def __aiter__(self) -> collections.AsyncIterator[_Workflow]:
        timeout_at = time.time() + 5
        waiting_on = {name: False for name in self._filter}

        while waiting_on:
            any_running = any(waiting_on.values())
            if not any_running:
                if time.time() > timeout_at:
                    break

                timeout = timeout_at

            else:
                timeout = None

            try:
                with anyio.fail_after(timeout):
                    workflow_id, name, action = await self._recv.receive()

            except TimeoutError:
                return

            if name not in waiting_on:
                continue

            if action is _WorkflowAction.COMPLETED:
                del waiting_on[name]
                yield _Workflow(name, workflow_id)

            else:
                waiting_on[name] = True

    def filter_names(self, names: collections.Collection[str], /) -> Self:
        """Set this to only track specific workflows.

        This will override any previously set filter.

        Parameters
        ----------
        names
            Collection of workflow names to filter for.

        Returns
        -------
        typing.Self
            The async workflow iterable.
        """
        self._filter = names
        return self


async def _on_startup():
    app.state.http = httpx.AsyncClient()
    app.state.index = _ProcessingIndex()
    app.state.tokens = _Tokens()
    app.state.workflows = _WorkflowDispatch()


async def _on_shutdown():
    await app.state.index.close()
    assert isinstance(app.state.http, httpx.AsyncClient)
    await app.state.http.aclose()


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
    assert isinstance(request.app.state.http, httpx.AsyncClient)
    assert isinstance(request.app.state.index, _ProcessingIndex)
    assert isinstance(app.state.tokens, _Tokens)
    assert isinstance(app.state.workflows, _WorkflowDispatch)
    http = request.app.state.http
    index = request.app.state.index
    tokens = app.state.tokens
    workflows = app.state.workflows
    match (x_github_event, body):
        case ("pull_request", {"action": "closed", "number": number, "repository": repo_data}):
            await index.stop_for_pr(int(repo_data["id"]), int(number), repo_name=repo_data["full_name"])

        case ("pull_request", {"action": "opened" | "reopened" | "synchronize"}):
            tasks.add_task(_process_repo, http, tokens, index, workflows, body)
            return fastapi.Response(status_code=202)

        case ("workflow_run", _):
            workflows.consume_event(body)

        case ("installation", {"action": "removed", "repositories_removed": repositories_removed}):
            for repo in repositories_removed:
                await index.clear_for_repo(int(repo["id"]))

        case ("installation_repositories", {"action": "removed", "repositories": repositories}):
            for repo in repositories:
                await index.clear_for_repo(int(repo["id"]))

        case (
            "github_app_authorization"
            | "installation"
            | "installation_repositories"
            | "installation_target"
            | "pull_request"
            | "workflow_run",
            _,
        ):
            pass

        case _:
            _LOGGER.info(
                "Ignoring unexpected event type %r. These events should be disabled for this app", x_github_event
            )
            return fastapi.Response("Event type not implemented", status_code=501)

    return fastapi.Response(status_code=204)


def _read_toml(path: pathlib.Path) -> dict[str, typing.Any]:
    with path.open("rb") as file:
        return tomllib.load(file)


@contextlib.asynccontextmanager
async def _with_cloned(url: str, /, *, branch: str = "master") -> collections.AsyncGenerator[pathlib.Path, None]:
    """Async context manager which shallow clones a repo into a temporary directory.

    Parameters
    ----------
    url
        URL of the repository to clone.

        This must include an installation which is authorised for
        `contents: write`.
        (`https://x-access-token:<token>@github.com/owner/repo.git`)
    branch
        The branch to clone.
    """
    temp_dir = await anyio.to_thread.run_sync(lambda: tempfile.TemporaryDirectory[str](ignore_cleanup_errors=True))
    try:
        await anyio.run_process(
            ["git", "clone", url, "--depth", "1", "--branch", branch, temp_dir.name],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        yield pathlib.Path(temp_dir.name)

    finally:
        # TODO: this just fails on Windows sometimes
        await anyio.to_thread.run_sync(temp_dir.cleanup)


class _RunCheck:
    """Context manager which manages the Github check suite for this application."""

    __slots__ = ("check_id", "commit_hash", "http", "index", "repo_name", "token")

    def __init__(self, http: httpx.AsyncClient, /, *, token: str, repo_name: str, commit_hash: str) -> None:
        """Initialise this context manager.

        Parameters
        ----------
        http
            REST client to use to manage the check suite.
        token
            Installation token to use to authorise the check suite requests.

            This must be authorised for `checks: write`.
        repo_name
            The repo's full name in the format `"{owner_name}/{repo_name}"`.
        commit_hash
            Hash of the PR commit this run is for.
        """
        self.check_id = -1
        self.commit_hash = commit_hash
        self.http = http
        self.repo_name = repo_name
        self.token = token

    async def __aenter__(self) -> Self:
        result = await _request(
            self.http,
            "POST",
            f"/repos/{self.repo_name}/check-runs",
            json={"name": "Inspecting PR", "head_sha": self.commit_hash},
            token=self.token,
        )
        self.check_id = int(result.json()["id"])
        return self

    async def __aexit__(
        self,
        exc_type: typing.Optional[type[BaseException]],
        _: typing.Optional[BaseException],
        __: typing.Optional[types.TracebackType],
    ) -> None:
        # TODO: this isn't actually marking it as cancel?
        if exc_type:
            conclusion = "failure" if issubclass(exc_type, Exception) else "cancelled"

        else:
            conclusion = "success"

        # TODO:
        # Consider setting exception name as {"output": {"summary"}}
        # Consider setting exception traceback as {"output": {"text"}}
        # For this we will likely want a add_filter for tokens
        # And also a set_changes for the summary and text and success
        await _request(
            self.http,
            "PATCH",
            f"/repos/{self.repo_name}/check-runs/{self.check_id}",
            json={"conclusion": conclusion},
            token=self.token,
        )

    async def mark_running(self) -> None:
        if self.check_id == -1:
            raise RuntimeError("Not running yet")

        await _request(
            self.http,
            "PATCH",
            f"/repos/{self.repo_name}/check-runs/{self.check_id}",
            json={"started_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(), "status": "in_progress"},
            token=self.token,
        )


async def _process_repo(
    http: httpx.AsyncClient,
    tokens: _Tokens,
    index: _ProcessingIndex,
    workflows: _WorkflowDispatch,
    body: dict[str, typing.Any],
) -> None:
    repo_data = body["repository"]
    repo_id = int(repo_data["id"])
    pr_id = int(body["number"])
    full_name = repo_data["full_name"]
    head_name = body["pull_request"]["head"]["repo"]["full_name"]
    head_ref = body["pull_request"]["head"]["ref"]
    head_repo_id = body["pull_request"]["head"]["repo"]["id"]
    head_sha = body["pull_request"]["head"]["sha"]
    installation_id = body["installation"]["id"]

    with (
        index.start(repo_id, pr_id, repo_name=full_name),
        workflows.track_workflows(repo_id, head_repo_id, head_sha) as tracked_workflows,
    ):
        token = await tokens.installation_token(http, installation_id)
        git_url = f"https://x-access-token:{token}@github.com/{head_name}.git"
        _LOGGER.info("Cloning %s:%s branch %s", full_name, pr_id, head_ref)
        run_ctx = _RunCheck(http, token=token, repo_name=full_name, commit_hash=head_sha)

        # TODO: pipe output to file to send in comment
        async with _with_cloned(git_url, branch=head_ref) as temp_dir_path, run_ctx:
            pyproject = await anyio.to_thread.run_sync(_read_toml, temp_dir_path / "pyproject.toml")
            config = _Config.parse_obj(pyproject["tool"]["piped"])
            if not config.bot_actions:
                _LOGGER.warn("Received event from %s repo with no bot_wait_for", full_name)
                return

            await run_ctx.mark_running()
            async for workflow in tracked_workflows.filter_names(config.bot_actions):
                await _apply_patch(http, token, full_name, workflow, cwd=temp_dir_path)

            await anyio.run_process(["git", "push"], cwd=temp_dir_path, stdout=sys.stdout, stderr=sys.stderr)


async def _apply_patch(
    http: httpx.AsyncClient, token: str, repo_name: str, workflow: _Workflow, /, *, cwd: pathlib.Path
) -> None:
    """Apply a patch file from another workflow's artifacts and commit its changes.

    This specifically looks for an artefact called `gogo.patch` and unzips it
    to get the file at `./gogo.patch`.

    Parameters
    ----------
    http
        The REST client to use to scan and download the workflow's artefacts.
    token
        The integration token to use.

        This must be authorised for `actions: read`.
    repo_name
        The repo's full name in the format `"{owner_name}/{repo_name}"`.
    workflow
        The workflow run to apply the patch of (if set).
    cwd
        Path to the target repo's top level directory.
    """
    # TODO: pagination support
    response = await _request(
        http,
        "GET",
        f"https://api.github.com/repos/{repo_name}/actions/runs/{workflow.workflow_id}/artifacts",
        token=token,
        query={"per_page": "100"},
    )
    for artifact in response.json()["artifacts"]:
        if artifact["name"] != "gogo.patch":
            continue

        response = await _request(http, "GET", artifact["archive_download_url"], token=token)
        zipped = zipfile.ZipFile(io.BytesIO(await response.aread()))
        # It's safe to extract to cwd since gogo.patch is git ignored.
        patch_path = await anyio.to_thread.run_sync(zipped.extract, "gogo.patch", cwd)

        try:
            # TODO: could --3way or --unidiff-zero help with conflicts here?
            await anyio.run_process(["git", "apply", patch_path], cwd=cwd, stdout=sys.stdout, stderr=sys.stderr)

        # If this conflicted then we should allow another CI run to redo these
        # changes after the current changes have been pushed.
        except subprocess.CalledProcessError:
            pass

        else:
            await anyio.run_process(
                ["git", "commit", "-am", workflow.name], cwd=cwd, stdout=sys.stdout, stderr=sys.stderr, env=COMMIT_ENV
            )

        await anyio.to_thread.run_sync(pathlib.Path(patch_path).unlink)
        break


# TODO: for some reason this is getting stuck on a background task while trying to stop it
# TODO: this probably shouldn't run on a PR with conflicts.
