# -*- coding: utf-8 -*-
# BSD 3-Clause License
#
# Copyright (c) 2020-2023, Faster Speeding
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
import os
import pathlib
import subprocess  # noqa: S404
import sys
import tempfile
import time
import traceback
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
import piped_shared
import starlette.middleware
from anyio.streams import memory as streams
from asgiref import typing as asgiref
from dateutil import parser as dateutil

if sys.version_info < (3, 11):
    raise RuntimeError("Only supports Python 3.11+")

_LOGGER = logging.getLogger("piped.bot")
_LOGGER.setLevel("INFO")

dotenv.load_dotenv()

_username = os.environ.get("CLIENT_NAME", default="always-on-duty") + "[bot]"

with httpx.Client() as client:
    _user_id = int(client.get(f"https://api.github.com/users/{_username}").json()["id"])

APP_ID = os.environ["APP_ID"]
COMMIT_ENV = {
    "GIT_AUTHOR_NAME": _username,
    "GIT_AUTHOR_EMAIL": f"{_user_id}+{_username}@users.noreply.github.com",
    "GIT_COMMITTER_NAME": _username,
}
COMMIT_ENV["GIT_COMMITTER_EMAIL"] = COMMIT_ENV["GIT_AUTHOR_EMAIL"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"].encode()
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
jwt_instance = jwt.JWT()


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

    def clear_for_repo(self, repo_id: int, /, *, repo_name: str | None = None) -> None:
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

    def stop_for_pr(self, repo_id: int, pr_id: int, /, *, repo_name: str | None = None) -> None:
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
        self._private_key = jwt.jwk_from_pem(os.environ["PRIVATE_KEY"].encode())

    def app_token(self, *, on_gen: collections.Callable[[str], None] | None = None) -> str:
        """Generate an application app token.

        !!! warning
            This cannot does not provide authorization for repos or
            organisations the application is authorised in.

        Parameters
        ----------
        on_gen
            Called on new token generation.

            This is for log filtering.
        """
        now = int(time.time())
        token = jwt_instance.encode(
            {"iat": now - 60, "exp": now + 60 * 2, "iss": APP_ID}, self._private_key, alg="RS256"
        )

        if on_gen:
            on_gen(token)

        return token

    async def installation_token(
        self,
        http: httpx.AsyncClient,
        installation_id: int,
        /,
        *,
        on_gen: collections.Callable[[str], None] | None = None,
    ) -> str:
        """Authorise an installation specific token.

        This is used to authorise organisation and repo actions and will return
        cached tokens.

        Parameters
        ----------
        http
            REST client to use to authorise the token.
        installation_id
            ID of the installation to authorise a token for.
        on_gen
            Called on new token generation for both app and installation tokens.

            This is for log filtering.

        Returns
        -------
        str
            The generated installation token.
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
            token=self.app_token(on_gen=on_gen),
        )
        data = response.json()
        token: str = data["token"]
        if on_gen:
            on_gen(token)

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
    output: typing.IO[str] | None = None,
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

    try:
        response.raise_for_status()
    except Exception:
        print("Response body:", file=output or sys.stderr)  # noqa: T201
        print(response.read().decode(), file=output or sys.stderr)  # noqa: T201
        raise

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
            "trailers": False,
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
        head_sha: str = body["workflow_run"]["head_sha"]
        repo_id = int(body["repository"]["id"])

        if send := self._listeners.get((repo_id, head_repo_id, head_sha)):
            action = _WorkflowAction(body["action"])
            name: str = body["workflow_run"]["name"]
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
        key = (repo_id, head_repo_id, head_sha)
        send, recv = anyio.create_memory_object_stream(1_000, item_type=tuple[int, str, _WorkflowAction])
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
            if not any(waiting_on.values()):
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
    assert isinstance(app.state.index, _ProcessingIndex)
    assert isinstance(app.state.http, httpx.AsyncClient)
    await app.state.index.close()
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
    assert isinstance(request.app.state.tokens, _Tokens)
    assert isinstance(request.app.state.workflows, _WorkflowDispatch)
    http = request.app.state.http
    index = request.app.state.index
    tokens = request.app.state.tokens
    workflows = request.app.state.workflows
    match (x_github_event, body):
        case ("pull_request", {"action": "closed", "number": number, "repository": repo_data}):
            index.stop_for_pr(int(repo_data["id"]), int(number), repo_name=repo_data["full_name"])
            await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

        case ("pull_request", {"action": "opened" | "reopened" | "synchronize"}):
            tasks.add_task(_process_repo, http, tokens, index, workflows, body)
            return fastapi.Response(status_code=202)

        case ("workflow_run", _):
            workflows.consume_event(body)

        case ("installation", {"action": "removed", "repositories_removed": repositories_removed}):
            for repo in repositories_removed:
                index.clear_for_repo(int(repo["id"]))

            await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

        case ("installation_repositories", {"action": "removed", "repositories": repositories}):
            for repo in repositories:
                index.clear_for_repo(int(repo["id"]))

            await anyio.sleep(0)  # Yield to the loop to let these cancels propagate

        # Guard to let these expected but ignored cases still return 204
        case (
            # check_suite events are received for the bot's check suites
            # regardless of configuration.
            "check_suite"
            | "github_app_authorization"
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


@contextlib.asynccontextmanager
async def _with_cloned(
    output: typing.IO[str], url: str, /, *, branch: str = "master"
) -> collections.AsyncGenerator[pathlib.Path, None]:
    """Async context manager which shallow clones a repo into a temporary directory.

    Parameters
    ----------
    output
        String file-like object this should pipe GIT's output to.
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
        await run_process(output, ["git", "clone", url, "--depth", "1", "--branch", branch, temp_dir.name])
        yield pathlib.Path(temp_dir.name)

    finally:
        # TODO: this just fails on Windows sometimes
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(temp_dir.cleanup)


class _RunCheck:
    """Context manager which manages the Github check suite for this application."""

    __slots__ = ("_check_id", "_commit_hash", "_filter_from_logs", "_http", "_output", "_repo_name", "_token")

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
        self._check_id = -1
        self._commit_hash = commit_hash
        self._filter_from_logs = [token]
        self._http = http
        self._output = io.StringIO()
        self._repo_name = repo_name
        self._token = token

    @property
    def output(self) -> io.StringIO:
        return self._output

    async def __aenter__(self) -> Self:
        result = await _request(
            self._http,
            "POST",
            f"/repos/{self._repo_name}/check-runs",
            json={"name": "Inspecting PR", "head_sha": self._commit_hash},
            output=self._output,
            token=self._token,
        )
        self._check_id = int(result.json()["id"])
        return self

    async def __aexit__(
        self,
        exc_cls: type[BaseException] | None,
        exc: BaseException | None,
        traceback_value: types.TracebackType | None,
    ) -> None:
        self._output.seek(0)
        output = {}

        if exc:
            conclusion = "failure" if isinstance(exc, Exception) else "cancelled"
            output["title"] = "Error"
            output["summary"] = str(exc)
            self._output.write("\n")
            self._output.write("```python\n")
            traceback.print_exception(exc_cls, exc, traceback_value, file=self._output)
            self._output.write("```\n")

        else:
            conclusion = "success"
            output["title"] = output["summary"] = "Success"

        # TODO: charlimit
        text = "\n".join(_censor(line, self._filter_from_logs) for line in self._output)
        output["text"] = f"```\n{text}\n```"

        # TODO: https://docs.github.com/en/get-started/writing-on-github/
        # working-with-advanced-formatting/creating-and-highlighting-code-blocks
        with anyio.CancelScope(shield=True):
            await _request(
                self._http,
                "PATCH",
                f"/repos/{self._repo_name}/check-runs/{self._check_id}",
                json={"conclusion": conclusion, "output": output},
                output=self._output,
                token=self._token,
            )

    def filter_from_logs(self, value: str, /) -> Self:
        """Mark a string as being filtered out of the logs.

        Parameters
        ----------
        value
            String to censor from logs.
        """
        self._filter_from_logs.append(value)
        return self

    async def mark_running(self) -> None:
        """Mark the check suite as running.

        Raises
        ------
        RuntimeError
            If called outside of this context manager's context.
        """
        if self._check_id == -1:
            raise RuntimeError("Not running yet")

        await _request(
            self._http,
            "PATCH",
            f"/repos/{self._repo_name}/check-runs/{self._check_id}",
            json={"started_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(), "status": "in_progress"},
            output=self._output,
            token=self._token,
        )


def _censor(value: str, filters: list[str], /) -> str:
    for filter_ in filters:
        value.replace(filter_, "***")

    return value


async def _process_repo(
    http: httpx.AsyncClient,
    tokens: _Tokens,
    index: _ProcessingIndex,
    workflows: _WorkflowDispatch,
    body: dict[str, typing.Any],
) -> None:
    repo_data: dict[str, typing.Any] = body["repository"]
    repo_id = int(repo_data["id"])
    pr_id = int(body["number"])
    full_name: str = repo_data["full_name"]
    head_name: str = body["pull_request"]["head"]["repo"]["full_name"]
    head_ref: str = body["pull_request"]["head"]["ref"]
    head_repo_id = int(body["pull_request"]["head"]["repo"]["id"])
    head_sha: str = body["pull_request"]["head"]["sha"]
    installation_id = int(body["installation"]["id"])

    with (
        index.start(repo_id, pr_id, repo_name=full_name),
        workflows.track_workflows(repo_id, head_repo_id, head_sha) as tracked_workflows,
    ):
        token = await tokens.installation_token(http, installation_id)
        git_url = f"https://x-access-token:{token}@github.com/{head_name}.git"
        _LOGGER.info("Cloning %s:%s branch %s", full_name, pr_id, head_ref)
        run_ctx = _RunCheck(http, token=token, repo_name=full_name, commit_hash=head_sha)

        async with run_ctx, _with_cloned(run_ctx.output, git_url, branch=head_ref) as temp_dir_path:
            config = await piped_shared.Config.read_async(temp_dir_path)
            if not config.bot_actions:
                _LOGGER.warn("Received event from %s repo with no bot_wait_for", full_name)
                return

            await run_ctx.mark_running()
            async for workflow in tracked_workflows.filter_names(config.bot_actions):
                await _apply_patch(http, run_ctx.output, token, full_name, workflow, cwd=temp_dir_path)

            await run_process(run_ctx.output, ["git", "push"], cwd=temp_dir_path)


async def _apply_patch(
    http: httpx.AsyncClient,
    output: typing.IO[str],
    token: str,
    repo_name: str,
    workflow: _Workflow,
    /,
    *,
    cwd: pathlib.Path,
) -> None:
    """Apply a patch file from another workflow's artifacts and commit its changes.

    This specifically looks for an artefact called `gogo.patch` and unzips it
    to get the file at `./gogo.patch`.

    Parameters
    ----------
    http
        The REST client to use to scan and download the workflow's artefacts.
    output
        String file-like object this should pipe GIT's output to.
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
        output=output,
        query={"per_page": "100"},
        token=token,
    )
    for artifact in response.json()["artifacts"]:
        if artifact["name"] != "gogo.patch":
            continue

        response = await _request(http, "GET", artifact["archive_download_url"], output=output, token=token)
        zipped = zipfile.ZipFile(io.BytesIO(await response.aread()))
        # It's safe to extract to cwd since gogo.patch is git ignored.
        patch_path = await anyio.to_thread.run_sync(zipped.extract, "gogo.patch", cwd)

        try:
            # TODO: could --3way or --unidiff-zero help with conflicts here?
            await run_process(output, ["git", "apply", patch_path], cwd=cwd)

        # If this conflicted then we should allow another CI run to redo these
        # changes after the current changes have been pushed.
        except subprocess.CalledProcessError:
            await anyio.to_thread.run_sync(pathlib.Path(patch_path).unlink)

        else:
            await anyio.to_thread.run_sync(pathlib.Path(patch_path).unlink)
            await run_process(output, ["git", "add", "."], cwd=cwd, env=COMMIT_ENV)
            await run_process(output, ["git", "commit", "-am", workflow.name], cwd=cwd, env=COMMIT_ENV)

        break


async def run_process(
    output: typing.IO[str],
    command: str | bytes | collections.Sequence[str | bytes],
    *,
    input: bytes | None = None,  # noqa: A002
    check: bool = True,
    cwd: str | bytes | os.PathLike[str] | None = None,
    env: collections.Mapping[str, str] | None = None,
    start_new_session: bool = False,
) -> None:
    try:
        # TODO: could --3way or --unidiff-zero help with conflicts here?
        result = await anyio.run_process(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            input=input,
            check=check,
            cwd=cwd,
            env=env,
            start_new_session=start_new_session,
        )

    except subprocess.CalledProcessError as exc:
        assert isinstance(exc.stdout, bytes)
        output.write(exc.stdout.decode())
        raise

    else:
        output.write(result.stdout.decode())
