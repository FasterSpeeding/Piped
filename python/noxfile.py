# -*- coding: utf-8 -*-
# BSD 3-Clause License
#
# Copyright (c) 2020-2024, Faster Speeding
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
from __future__ import annotations

__all__: list[str] = [
    "build",
    "cleanup",
    "copy_actions",
    "flake8",
    "freeze_locks",
    "generate_docs",
    "publish",
    "reformat",
    "slot_check",
    "spell_check",
    "test",
    "test_coverage",
    "test_publish",
    "type_check",
    "verify_markup",
    "verify_types",
]

import datetime
import itertools
import pathlib
import re
import tomllib
import typing
from collections import abc as collections

import nox
import piped_shared

_CallbackT = typing.TypeVar("_CallbackT", bound=collections.Callable[..., typing.Any])

_config = piped_shared.Config.read(pathlib.Path("./"))
nox.options.sessions = _config.default_sessions
_DEPS_DIR = pathlib.Path("./dev-requirements")
_SELF_INSTALL_REGEX = re.compile(r"^\.\[.+\]$")


def _tracked_files(session: nox.Session, *, force_all: bool = False) -> collections.Iterable[str]:
    output = session.run("git", "--no-pager", "grep", "--threads=1", "-l", "", external=True, log=False, silent=True)
    assert isinstance(output, str)

    if _config.path_ignore and not force_all:
        return (path for path in output.splitlines() if not _config.path_ignore.search(path))

    return output.splitlines()


def _install_deps(
    session: nox.Session, *groups: str, only_dev: bool = True
) -> None:
    if not groups:
        return

    target_type = "group"

    if only_dev:
        target_type = "only-group"

    session.install("uv")
    # session.run_install("uv", "sync", "--locked", *map(f"--{target_type}={{}}".format, groups), env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location})



def _try_find_option(
    session: nox.Session, name: str, /, *other_names: str, when_empty: str | None = None
) -> str | None:
    args_iter = iter(session.posargs)
    names = {name, *other_names}

    for arg in args_iter:
        if arg in names:
            return next(args_iter, when_empty)


def _filtered_session(
    *,
    python: str | collections.Sequence[str] | bool | None = None,
    py: str | collections.Sequence[str] | bool | None = None,
    reuse_venv: bool | None = None,
    name: str | None = None,
    venv_backend: typing.Any = "uv",
    venv_params: typing.Any = None,
    tags: list[str] | None = None,
) -> collections.Callable[[_CallbackT], _CallbackT | None]:
    """Filtering version of `nox.session`."""

    def decorator(callback: _CallbackT, /) -> _CallbackT | None:
        name_ = name or callback.__name__
        if name_ in _config.hide:
            return None

        return nox.session(
            python=python,
            py=py,
            reuse_venv=reuse_venv,
            name=name,
            venv_backend=venv_backend,
            venv_params=venv_params,
            tags=tags,
        )(callback)

    return decorator


@_filtered_session(venv_backend="none")
def cleanup(session: nox.Session) -> None:
    """Cleanup any temporary files made in this project by its nox tasks."""
    import shutil

    # Remove directories
    raw_paths = ["./dist", "./site", "./.nox", "./.pytest_cache", "./coverage_html", ".mypy_cache"]
    if _config.project_name:
        raw_paths.append(f"{_config.project_name}.egg-info")

    for raw_path in raw_paths:
        path = pathlib.Path(raw_path)
        try:
            shutil.rmtree(str(path.absolute()))

        except FileNotFoundError:
            session.warn(f"[ SKIP ] '{raw_path}'")

        except Exception as exc:
            session.error(f"[ FAIL ] Failed to remove '{raw_path}': {exc!s}")  # noqa: TC400

        else:
            session.log(f"[  OK  ] Removed '{raw_path}'")

    # Remove individual files
    for raw_path in ["./.coverage", "./coverage_html.xml", "./gogo.patch"]:
        path = pathlib.Path(raw_path)
        try:
            path.unlink()

        except FileNotFoundError:
            session.warn(f"[ SKIP ] '{raw_path}'")

        except Exception as exc:
            session.error(f"[ FAIL ] Failed to remove '{raw_path}': {exc!s}")  # noqa: TC400

        else:
            session.log(f"[  OK  ] Removed '{raw_path}'")


@nox.session(name="copy-actions")
def copy_actions(session: nox.Session) -> None:
    """Copy over the github actions from Piped without updating the git reference."""
    _install_deps(session, "templating")
    session.run("python", str(pathlib.Path(__file__).parent / "copy_actions.py"), env=env)


def _pyproject_toml() -> dict[str, typing.Any] | None:
    try:
        with pathlib.Path("pyproject.toml").open("rb") as _file:
            return tomllib.load(_file)

    except FileNotFoundError:
        return None


def _freeze_file(session: nox.Session, path: pathlib.Path, /) -> None:
    if not path.is_symlink():
        target = path.with_name(path.name[:-3] + ".txt")
        target.unlink(missing_ok=True)
        session.run(
            "pip-compile-cross-platform",
            "--generate-hashes",
            "-o",
            str(target),
            "--min-python-version",
            _config.version(_pyproject_toml()),
            str(path),
        )


_EXTRAS_FILTER = re.compile(r"\[.+\]")


@nox.session(name="freeze-locks", reuse_venv=True)
def freeze_locks(session: nox.Session) -> None:
    """Freeze the dependency locks."""
    _install_deps(session, "freeze-locks")

    for path in _config.dep_sources:
        session.chdir(path.parent)
        session.run("uv", "lock", "--upgrade")


@_filtered_session(name="generate-docs", reuse_venv=True)
def generate_docs(session: nox.Session) -> None:
    """Generate docs for this project using Mkdoc."""
    _install_deps(session, "docs")
    output_directory = _try_find_option(session, "-o", "--output") or "./site"
    session.run("mkdocs", "build", "--strict", "-d", output_directory)


@_filtered_session(reuse_venv=True)
def flake8(session: nox.Session) -> None:
    """Run this project's modules against the pre-defined flake8 linters."""
    _install_deps(session, "lint")
    session.log("Running flake8")
    session.run("flake8", *_config.top_level_targets, log=False)


@_filtered_session(reuse_venv=True, name="slot-check")
def slot_check(session: nox.Session) -> None:
    """Check this project's slotted classes for common mistakes."""
    # TODO: don't require installing .?
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, "lint")
    session.run("slotscheck", "-m", _config.assert_project_name())


@_filtered_session(reuse_venv=True, name="spell-check")
def spell_check(session: nox.Session) -> None:
    """Check this project's text-like files for common spelling mistakes."""
    _install_deps(session, "lint")
    session.log("Running codespell")
    session.run("codespell", *_tracked_files(session), log=False)


@_filtered_session(reuse_venv=True)
def build(session: nox.Session) -> None:
    """Build this project using flit."""
    _install_deps(session, "publish")
    session.log("Starting build")
    session.run("flit", "build")


_LICENCE_PATTERN = re.compile(r"(Copyright \(c\) (\d+-?\d*))")


def _update_licence(match: re.Match[str]) -> str:
    licence_str, date_range = match.groups()
    start = date_range.split("-", 1)[0]
    current_year = str(datetime.datetime.now().year)

    if start == current_year:
        return licence_str

    return f"{licence_str.removesuffix(date_range)}{start}-{current_year}"


_LICENCE_FILE_PATTERN = re.compile(r".*(rs|py)|LICENSE")


@_filtered_session(name="update-licence", venv_backend="none")
def update_licence(session: nox.Session):
    """Bump the end year of the project's licence to the current year."""
    for path in map(pathlib.Path, _tracked_files(session)):
        if not _LICENCE_FILE_PATTERN.fullmatch(path.name):
            continue

        data = path.read_text()
        new_data = _LICENCE_PATTERN.sub(_update_licence, data)

        if new_data != data:
            path.write_text(new_data)


@_filtered_session(name="verify-markup", reuse_venv=True)
def verify_markup(session: nox.Session):
    """Verify the syntax of the repo's markup files."""
    _install_deps(session, "lint")
    tracked_files = list(_tracked_files(session))

    session.log("Running pre_commit_hooks.check_toml")
    session.run(
        "python",
        "-m",
        "pre_commit_hooks.check_toml",
        *(path for path in tracked_files if path.endswith(".toml")),
        success_codes=[0, 1],
        log=False,
    )

    session.log("Running pre_commit_hooks.check_yaml")
    session.run(
        "python",
        "-m",
        "pre_commit_hooks.check_yaml",
        *(path for path in tracked_files if path.endswith(".yml") or path.endswith(".yaml")),
        success_codes=[0, 1],
        log=False,
    )


def _publish(session: nox.Session, /, *, env: dict[str, str] | None = None) -> None:
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, "publish")

    env = env or session.env.copy()
    if target := session.env.get("PUBLISH_TARGET"):
        env["FLIT_INDEX_URL"] = target

    if token := session.env.get("PUBLISH_TOKEN"):
        env["FLIT_PASSWORD"] = token

    env.setdefault("FLIT_USERNAME", "__token__")
    session.run("flit", "publish", env=env)


@_filtered_session(reuse_venv=True)
def publish(session: nox.Session):
    """Publish this project to pypi."""
    _publish(session)


@_filtered_session(name="test-publish", reuse_venv=True)
def test_publish(session: nox.Session) -> None:
    """Publish this project to test pypi."""
    env = session.env.copy()
    env.setdefault("PYPI_TARGET", "https://test.pypi.org/legacy/")
    _publish(session, env=env)


@_filtered_session(reuse_venv=True)
def reformat(session: nox.Session) -> None:
    """Reformat this project's modules to fit the standard style."""
    _install_deps(session, "reformat")
    if _config.top_level_targets:
        session.run("black", *_config.top_level_targets)
        session.run("isort", *_config.top_level_targets)
        session.run("pycln", *_config.top_level_targets, "--config", "pyproject.toml")

    tracked_files = list(_tracked_files(session))  # TODO: sometimes force all or more granular controls?
    py_files = [path for path in tracked_files if re.fullmatch(r".+\.pyi?$", path)]

    if py_files:
        session.log("Running sort-all")
        session.run("sort-all", *py_files, success_codes=[0, 1], log=False)

    session.log("Running pre_commit_hooks.end_of_file_fixer")
    session.run("python", "-m", "pre_commit_hooks.end_of_file_fixer", *tracked_files, success_codes=[0, 1], log=False)

    session.log("Running pre_commit_hooks.trailing_whitespace_fixer")
    session.run(
        "python", "-m", "pre_commit_hooks.trailing_whitespace_fixer", *tracked_files, success_codes=[0, 1], log=False
    )


@_filtered_session(reuse_venv=True)
def test(session: nox.Session) -> None:
    """Run this project's tests using pytest."""
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, "tests")
    # TODO: can import-mode be specified in the config.
    session.run("pytest", "-n", "auto", "--import-mode", "importlib")


@_filtered_session(name="test-coverage", reuse_venv=True)
def test_coverage(session: nox.Session) -> None:
    """Run this project's tests while recording test coverage."""
    project_name = _config.assert_project_name()
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, "tests")
    # TODO: can import-mode be specified in the config.
    # https://github.com/nedbat/coveragepy/issues/1002
    session.run(
        "pytest",
        "-n",
        "auto",
        f"--cov={project_name}",
        "--cov-report",
        "html:coverage_html",
        "--cov-report",
        "xml:coverage.xml",
    )


def _run_pyright(session: nox.Session, /, *args: str) -> None:
    session.run("python", "-m", "pyright", "--version")
    session.run("python", "-m", "pyright", *args)


@_filtered_session(name="type-check", reuse_venv=True)
def type_check(session: nox.Session) -> None:
    """Statically analyse and veirfy this project using Pyright."""
    _install_deps(session, "type-checking")
    _run_pyright(session)

    if _config.mypy_targets:
        success_codes = [0]
        if _config.mypy_allowed_to_fail:
            success_codes.append(1)

        session.run("python", "-m", "mypy", *_config.mypy_targets, "--show-error-codes", success_codes=success_codes)


@_filtered_session(name="verify-types", reuse_venv=True)
def verify_types(session: nox.Session) -> None:
    """Verify the "type completeness" of types exported by the library using Pyright."""
    project_name = _config.assert_project_name()
    # TODO is installing . necessary here?
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, "type-checking")
    _run_pyright(session, "--verifytypes", project_name, "--ignoreexternal")


@nox.session(name="copy-piped", reuse_venv=True)
def sync_piped(session: nox.Session) -> None:
    """Copy over Piped's configuration without fetching."""
    copy_actions(session)


@_filtered_session(name="fetch-piped", reuse_venv=True)
def fetch_piped(session: nox.Session) -> None:
    """Fetch Piped from upstream and resync."""
    session.run("git", "submodule", "update", "--remote", "piped", external=True)
    _install_deps(session, "nox")
    # We call this through nox's CLI like this to ensure that the updated version
    # of these sessions are called.
    session.run("nox", "-s", "copy-piped")


@nox.session(name="bot-package-diff", venv_backend="none")
def bot_package_diff(session: nox.Session) -> None:
    session.run("git", "add", ".", external=True)
    output = session.run("git", "diff", "HEAD", external=True, silent=True)
    assert isinstance(output, str)

    path = pathlib.Path("./gogo.patch")
    if output:
        with path.open("w+") as file:
            file.write(output)

    else:
        path.unlink(missing_ok=True)


@nox.session(name="is-diff-file-empty", venv_backend="none")
def is_diff_file_empty(_: nox.Session):
    if pathlib.Path("./gogo.patch").exists():
        exit("Diff created")
