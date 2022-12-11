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
from __future__ import annotations

__all__: typing.List[str] = [
    "build",
    "cleanup",
    "copy_actions",
    "flake8",
    "freeze_dev_deps",
    "generate_docs",
    "publish",
    "reformat",
    "slot_check",
    "spell_check",
    "test",
    "test_coverage",
    "test_publish",
    "type_check",
    "verify_dev_deps",
    "verify_markup",
    "verify_types",
]

import itertools
import pathlib
import re
import shutil
import typing

import nox
import pydantic
import tomli

_CallbackT = typing.TypeVar("_CallbackT", bound=typing.Callable[..., typing.Any])


class _Config(pydantic.BaseModel):
    """Configuration class for the project config."""

    default_sessions: typing.List[str]
    extra_test_installs: typing.List[str] = pydantic.Field(default_factory=list)
    github_actions: typing.Union[typing.Dict[str, typing.Dict[str, str]], typing.List[str]] = pydantic.Field(
        default_factory=lambda: ["resync-piped"]
    )
    hide: typing.List[str] = pydantic.Field(default_factory=list)
    mypy_allowed_to_fail: bool = False
    mypy_targets: typing.List[str] = pydantic.Field(default_factory=list)

    # Right now pydantic fails to recognise Pattern[str] so we have to hide this
    # at runtime.
    if typing.TYPE_CHECKING:
        path_ignore: typing.Optional[typing.Pattern[str]] = None

    else:
        path_ignore: typing.Optional[typing.Pattern] = None

    project_name: typing.Optional[str] = None
    top_level_targets: typing.List[str]

    def assert_project_name(self) -> str:
        if not self.project_name:
            raise RuntimeError("This CI cannot run without project_name")

        return self.project_name


with pathlib.Path("pyproject.toml").open("rb") as _file:
    _config = _Config.parse_obj(tomli.load(_file)["tool"]["piped"])


nox.options.sessions = _config.default_sessions
_DEPS_DIR = pathlib.Path("./dev-requirements")
_SELF_INSTALL_REGEX = re.compile(r"^\.\[.+\]$")


def _dev_path(value: str) -> pathlib.Path:
    path = _DEPS_DIR / f"{value}.txt"
    if path.exists():
        return path

    return pathlib.Path(__file__).parent / "base-requirements" / f"{value}.txt"


_CONSTRAINT_DIR = _dev_path("constraints")


def _deps(*dev_deps: str, constrain: bool = False) -> typing.Iterator[str]:
    if constrain and _CONSTRAINT_DIR.exists():
        return itertools.chain(["-c", str(_CONSTRAINT_DIR)], _deps(*dev_deps))

    return itertools.chain.from_iterable(("-r", str(_dev_path(value))) for value in dev_deps)


def _tracked_files(session: nox.Session, *, force_all: bool = False) -> typing.Iterable[str]:
    output = session.run("git", "--no-pager", "grep", "--threads=1", "-l", "", external=True, log=False, silent=True)
    assert isinstance(output, str)

    if _config.path_ignore and not force_all:
        return (path for path in output.splitlines() if not _config.path_ignore.search(path))

    return output.splitlines()


def _install_deps(session: nox.Session, *requirements: str, first_call: bool = True) -> None:
    # --no-install --no-venv leads to it trying to install in the global venv
    # as --no-install only skips "reused" venvs and global is not considered reused.
    if not _try_find_option(session, "--skip-install", when_empty="True"):
        if first_call:
            session.install("--upgrade", "wheel")

        session.install("--upgrade", *map(str, requirements))

    elif any(map(_SELF_INSTALL_REGEX.fullmatch, requirements)):
        session.install("--upgrade", "--force-reinstall", "--no-dependencies", ".")


def _try_find_option(
    session: nox.Session, name: str, *other_names: str, when_empty: typing.Optional[str] = None
) -> typing.Optional[str]:
    args_iter = iter(session.posargs)
    names = {name, *other_names}

    for arg in args_iter:
        if arg in names:
            return next(args_iter, when_empty)


def _filtered_session(
    *,
    python: typing.Union[str, typing.Sequence[str], bool, None] = None,
    py: typing.Union[str, typing.Sequence[str], bool, None] = None,
    reuse_venv: typing.Optional[bool] = None,
    name: typing.Optional[str] = None,
    venv_backend: typing.Any = None,
    venv_params: typing.Any = None,
    tags: typing.Optional[typing.List[str]] = None,
) -> typing.Callable[[_CallbackT], typing.Union[_CallbackT, None]]:
    """Filtering version of `nox.session`."""

    def decorator(callback: _CallbackT, /) -> typing.Optional[_CallbackT]:
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
    raw_paths = ["./dist", "./site", "./.nox", "./.pytest_cache", "./coverage_html"]
    if _config.project_name:
        raw_paths.append(f"{_config.project_name}.egg-info")

    for raw_path in raw_paths:
        path = pathlib.Path(raw_path)
        try:
            shutil.rmtree(str(path.absolute()))

        except Exception as exc:
            session.warn(f"[ FAIL ] Failed to remove '{raw_path}': {exc!s}")

        else:
            session.log(f"[  OK  ] Removed '{raw_path}'")

    # Remove individual files
    for raw_path in ["./.coverage", "./coverage_html.xml"]:
        path = pathlib.Path(raw_path)
        try:
            path.unlink()

        except Exception as exc:
            session.warn(f"[ FAIL ] Failed to remove '{raw_path}': {exc!s}")

        else:
            session.log(f"[  OK  ] Removed '{raw_path}'")


class _Action:
    __slots__ = ("defaults", "required_names")

    def __init__(
        self, *, required: typing.Sequence[str] = (), defaults: typing.Optional[dict[str, str]] = None
    ) -> None:
        self.defaults = defaults or {}
        self.required_names = frozenset(required or ())


_NOX_DEP_DEFAULT = {"NOX_DEP_PATH": "./piped/python/base-requirements/nox.txt"}


_ACTIONS: typing.Dict[str, _Action] = {
    "freeze-for-pr": _Action(defaults=_NOX_DEP_DEFAULT),
    "lint": _Action(defaults=_NOX_DEP_DEFAULT),
    "pr-docs": _Action(defaults=_NOX_DEP_DEFAULT),
    "publish": _Action(defaults=_NOX_DEP_DEFAULT),
    "py-lint": _Action(defaults=_NOX_DEP_DEFAULT),
    "py-test": _Action(
        required=["PYTHON_VERSIONS"],
        defaults={**_NOX_DEP_DEFAULT, "CODECLIMATE_TOKEN": "", "OSES": "[ubuntu-latest, macos-latest, windows-latest]"},
    ),
    "reformat": _Action(defaults=_NOX_DEP_DEFAULT),
    "release-docs": _Action(defaults=_NOX_DEP_DEFAULT),
    "resync-piped": _Action(defaults=_NOX_DEP_DEFAULT),
    "type-check": _Action(defaults=_NOX_DEP_DEFAULT),
    "upgrade-dev-deps": _Action(defaults=_NOX_DEP_DEFAULT),
    "verify-frozen-deps": _Action(defaults=_NOX_DEP_DEFAULT),
    "verify-types": _Action(defaults=_NOX_DEP_DEFAULT),
}


def _copy_actions() -> None:
    """Copy over the github actions from Piped without updating the git reference."""
    to_write: typing.Dict[pathlib.Path, str] = {}
    if isinstance(_config.github_actions, dict):
        actions = iter(_config.github_actions.items())
        wild_card: typing.ItemsView[str, str] = (_config.github_actions.get("*") or {}).items()

    else:
        actions: typing.Iterable[typing.Tuple[str, typing.Dict[str, str]]] = (
            (name, {}) for name in _config.github_actions
        )
        wild_card = {}.items()

    for file_name, config in actions:
        if file_name == "*":
            continue

        config = {key.upper(): value for key, value in itertools.chain(wild_card, config.items())}
        file_name = file_name.replace("_", "-")
        action = _ACTIONS[file_name]
        if missing := action.required_names.difference(config.keys()):
            raise RuntimeError(f"Missing the following required fields for {file_name} actions: " + ", ".join(missing))

        file_name = f"{file_name}.yml"
        with (pathlib.Path(__file__).parent.parent / "github" / "actions" / file_name).open("r") as file:
            data = file.read()

        for name, value in config.items():
            data = data.replace("{{" + name + "}}", value)

        for name, value in action.defaults.items():
            if name not in config:
                data = data.replace("{{" + name + "}}", value)

        to_write[pathlib.Path("./.github/workflows") / file_name] = data

    for path, value in to_write.items():
        with path.open("w+") as file:
            file.write(value)


@nox.session(name="copy-actions")
def copy_actions(_: nox.Session) -> None:
    """Copy over the github actions from Piped without updating the git reference."""
    _copy_actions()


def _to_valid_urls(session: nox.Session) -> typing.Optional[typing.Set[pathlib.Path]]:
    if session.posargs:
        return set(map(pathlib.Path.resolve, map(pathlib.Path, session.posargs)))


_CONSTRAINTS_IN = pathlib.Path("./dev-requirements/constraints.in")


@_filtered_session(name="freeze-dev-deps", reuse_venv=True)
def freeze_dev_deps(session: nox.Session, *, other_dirs: typing.Sequence[pathlib.Path] = ()) -> None:
    """Upgrade the dev dependencies."""
    _install_deps(session, *_deps("freeze-deps"))
    valid_urls = _to_valid_urls(session)

    if not valid_urls:
        with pathlib.Path("./pyproject.toml").open("rb") as file:
            project = tomli.load(file).get("project") or {}
            deps = project.get("dependencies") or []
            if optional := project.get("optional-dependencies"):
                deps.extend(itertools.chain(*optional.values()))

        if deps:
            with _CONSTRAINTS_IN.open("w+") as file:
                file.write("\n".join(deps) + "\n")

        else:
            _CONSTRAINTS_IN.unlink(missing_ok=True)
            pathlib.Path("./dev-requirements/constraints.txt").unlink(missing_ok=True)

    for dir_path in itertools.chain((pathlib.Path("./dev-requirements/"),), other_dirs):
        for path in dir_path.glob("*.in"):
            if not path.is_symlink() and (not valid_urls or path.resolve() in valid_urls):
                target = path.with_name(path.name[:-3] + ".txt")
                target.unlink(missing_ok=True)
                session.run(
                    "pip-compile-cross-platform", "-o", str(target), "--min-python-version", "3.9,<3.12", str(path)
                )


@_filtered_session(name="verify-dev-deps", reuse_venv=True)
def verify_dev_deps(session: nox.Session) -> None:
    """Verify the dev deps by installing them."""
    valid_urls = _to_valid_urls(session)

    for path in pathlib.Path("./dev-requirements/").glob("*.txt"):
        if not valid_urls or path.resolve() in valid_urls:
            session.install("--dry-run", "-r", str(path))


@_filtered_session(name="generate-docs", reuse_venv=True)
def generate_docs(session: nox.Session) -> None:
    """Generate docs for this project using Mkdoc."""
    _install_deps(session, *_deps("docs"))
    output_directory = _try_find_option(session, "-o", "--output") or "./site"
    session.run("mkdocs", "build", "-d", output_directory)
    for path in ("./CHANGELOG.md", "./README.md"):
        shutil.copy(path, pathlib.Path(output_directory) / path)


@_filtered_session(reuse_venv=True)
def flake8(session: nox.Session) -> None:
    """Run this project's modules against the pre-defined flake8 linters."""
    _install_deps(session, *_deps("flake8"))
    session.log("Running flake8")
    session.run("pflake8", *_config.top_level_targets, log=False)


@_filtered_session(reuse_venv=True, name="slot-check")
def slot_check(session: nox.Session) -> None:
    """Check this project's slotted classes for common mistakes."""
    # TODO: better system for deciding whether this runs
    if _config.project_name:
        # TODO: don't require installing .?
        _install_deps(session, *_config.extra_test_installs, *_deps("lint", constrain=True))
        session.run("slotscheck", "-m", _config.project_name)


@_filtered_session(reuse_venv=True, name="spell-check")
def spell_check(session: nox.Session) -> None:
    """Check this project's text-like files for common spelling mistakes."""
    _install_deps(session, *_deps("lint"))
    session.log("Running codespell")
    session.run("codespell", *_tracked_files(session), "--ignore-regex", "TimeSchedule|Nd", log=False)


@_filtered_session(reuse_venv=True)
def build(session: nox.Session) -> None:
    """Build this project using flit."""
    _install_deps(session, *_deps("publish"))
    session.log("Starting build")
    session.run("flit", "build")


@_filtered_session(name="verify-markup", reuse_venv=True)
def verify_markup(session: nox.Session):
    """Verify the syntax of the repo's markup files."""
    _install_deps(session, *_deps("lint"))
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


def _publish(session: nox.Session, env: typing.Optional[typing.Dict[str, str]] = None) -> None:
    _install_deps(session, *_deps("publish"))
    # TODO: does this need to install .?
    _install_deps(session, ".", *_deps(constrain=True), first_call=False)

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
    _install_deps(session, *_deps("reformat"))
    session.run("black", *_config.top_level_targets)
    session.run("isort", *_config.top_level_targets)
    session.run("pycln", *_config.top_level_targets)

    tracked_files = list(_tracked_files(session, force_all=True))
    py_files = [path for path in tracked_files if re.fullmatch(r".+\.pyi?$", path)]

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
    _install_deps(session, *_config.extra_test_installs, *_deps("tests", constrain=True))
    # TODO: can import-mode be specified in the config.
    session.run("pytest", "-n", "auto", "--import-mode", "importlib")


@_filtered_session(name="test-coverage", reuse_venv=True)
def test_coverage(session: nox.Session) -> None:
    """Run this project's tests while recording test coverage."""
    project_name = _config.assert_project_name()
    _install_deps(session, *_config.extra_test_installs, *_deps("tests", constrain=True))
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


def _run_pyright(session: nox.Session, *args: str) -> None:
    session.run("python", "-m", "pyright", "--version")
    session.run("python", "-m", "pyright", *args)


@_filtered_session(name="type-check", reuse_venv=True)
def type_check(session: nox.Session) -> None:
    """Statically analyse and veirfy this project using Pyright."""
    _install_deps(session, *_deps("type-checking"))
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
    _install_deps(session, *_config.extra_test_installs, *_deps("type-checking", constrain=True))
    _run_pyright(session, "--verifytypes", project_name, "--ignoreexternal")


@_filtered_session(name="sync-piped")
def sync_piped(session: nox.Session) -> None:
    """Sync Piped from upstream."""
    session.run("git", "submodule", "update", "--remote", "piped", external=True)
    _copy_actions()
