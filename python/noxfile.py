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
    "verify_deps",
    "verify_markup",
    "verify_types",
]

import itertools
import pathlib
import re
import shutil
import typing
from collections import abc as collections

import nox
import pydantic
import tomli

_CallbackT = typing.TypeVar("_CallbackT", bound=collections.Callable[..., typing.Any])
ConfigEntryT = typing.Union[dict[str, str], list[str], str]
ConfigT = dict[str, ConfigEntryT]


def _default_version():
    requires: typing.Optional[str]
    if (project := _pyproject_toml.get("project")) and (requires := project.get("requires-python")):
        return requires.lstrip(">=")

    return "3.9,<3.12"


class _Config(pydantic.BaseModel):
    """Configuration class for the project config."""

    codespell_ignore: typing.Optional[str] = None
    default_sessions: list[str]
    dep_locks: list[pathlib.Path] = pydantic.Field(default_factory=lambda: [pathlib.Path("./dev-requirements/")])
    extra_test_installs: list[str] = pydantic.Field(default_factory=list)
    github_actions: typing.Union[dict[str, ConfigT], list[str]] = pydantic.Field(
        default_factory=lambda: ["resync-piped"]
    )
    hide: list[str] = pydantic.Field(default_factory=list)
    mypy_allowed_to_fail: bool = False
    mypy_targets: list[str] = pydantic.Field(default_factory=list)

    # Right now pydantic fails to recognise Pattern[str] so we have to hide this
    # at runtime.
    if typing.TYPE_CHECKING:
        path_ignore: typing.Optional[re.Pattern[str]] = None

    else:
        path_ignore: typing.Optional[re.Pattern] = None

    project_name: typing.Optional[str] = None
    top_level_targets: list[str]
    version_constraint: str = pydantic.Field(default_factory=_default_version)

    def assert_project_name(self) -> str:
        if not self.project_name:
            raise RuntimeError("This CI cannot run without project_name")

        return self.project_name

    def codespell_ignore_args(self) -> list[str]:
        if self.codespell_ignore:
            return ["--ignore-regex", self.codespell_ignore]

        return []


with pathlib.Path("pyproject.toml").open("rb") as _file:
    _pyproject_toml = tomli.load(_file)
    _config = _Config.parse_obj(_pyproject_toml["tool"]["piped"])


nox.options.sessions = _config.default_sessions
_DEPS_DIR = pathlib.Path("./dev-requirements")
_SELF_INSTALL_REGEX = re.compile(r"^\.\[.+\]$")


def _exists(path: pathlib.Path) -> typing.Optional[pathlib.Path]:
    return path if path.exists() else None


def _dev_path(value: str, /) -> pathlib.Path:
    return _exists(_DEPS_DIR / f"{value}.txt") or pathlib.Path(__file__).parent / "base-requirements" / f"{value}.txt"


def _constraints_txt() -> typing.Optional[pathlib.Path]:
    return _exists(_DEPS_DIR / "constraints.txt")


def _runtime_deps() -> list[str]:
    path = _constraints_txt()
    if path:
        actual_file = _exists(_DEPS_DIR / "constraints.txt")
        if not actual_file:
            raise RuntimeError("Couldn't find constraints.txt")

        return ["-r", str(actual_file), "-c", str(path)]

    return []


def _deps(*dev_deps: str, constrain: bool = False) -> collections.Iterator[str]:
    if constrain and (path := _constraints_txt()):
        return itertools.chain(["-c", str(path)], _deps(*dev_deps))

    return itertools.chain.from_iterable(("-r", str(_dev_path(value))) for value in dev_deps)


def _tracked_files(session: nox.Session, *, force_all: bool = False) -> collections.Iterable[str]:
    output = session.run("git", "--no-pager", "grep", "--threads=1", "-l", "", external=True, log=False, silent=True)
    assert isinstance(output, str)

    if _config.path_ignore and not force_all:
        return (path for path in output.splitlines() if not _config.path_ignore.search(path))

    return output.splitlines()


def _install_deps(session: nox.Session, *requirements: str, first_call: bool = True) -> None:
    if not requirements:
        return

    # --no-install --no-venv leads to it trying to install in the global venv
    # as --no-install only skips "reused" venvs and global is not considered reused.
    if not _try_find_option(session, "--skip-install", when_empty="True"):
        if first_call:
            session.install("--upgrade", "wheel")

        session.install("--upgrade", *map(str, requirements))

    elif any(map(_SELF_INSTALL_REGEX.fullmatch, requirements)):
        session.install("--upgrade", "--force-reinstall", "--no-dependencies", ".")


def _try_find_option(
    session: nox.Session, name: str, /, *other_names: str, when_empty: typing.Optional[str] = None
) -> typing.Optional[str]:
    args_iter = iter(session.posargs)
    names = {name, *other_names}

    for arg in args_iter:
        if arg in names:
            return next(args_iter, when_empty)


def _filtered_session(
    *,
    python: typing.Union[str, collections.Sequence[str], bool, None] = None,
    py: typing.Union[str, collections.Sequence[str], bool, None] = None,
    reuse_venv: typing.Optional[bool] = None,
    name: typing.Optional[str] = None,
    venv_backend: typing.Any = None,
    venv_params: typing.Any = None,
    tags: typing.Optional[list[str]] = None,
) -> collections.Callable[[_CallbackT], typing.Union[_CallbackT, None]]:
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
    for raw_path in ["./.coverage", "./coverage_html.xml", "./gogo.patch"]:
        path = pathlib.Path(raw_path)
        try:
            path.unlink()

        except Exception as exc:
            session.warn(f"[ FAIL ] Failed to remove '{raw_path}': {exc!s}")

        else:
            session.log(f"[  OK  ] Removed '{raw_path}'")


_DEFAULT_COMMITER_USERNAME = "always-on-duty[bot]"

_ACTION_DEFAULTS = {
    "ACTION_COMMITTER_EMAIL": f"120557446+{_DEFAULT_COMMITER_USERNAME}@users.noreply.github.com",
    "ACTION_COMMITTER_USERNAME": _DEFAULT_COMMITER_USERNAME,
    "DEFAULT_PY_VER": "3.9",
    "NOX_DEP_PATH": "./piped/python/base-requirements/nox.txt",
}
_resync_filter: list[str] = ["piped", "pyproject.toml"]
_verify_filter: list[str] = []
_dep_locks: list[pathlib.Path] = []


if _config.dep_locks:
    for _path in _config.dep_locks:
        if _path.is_absolute():
            _path = _path.relative_to(pathlib.Path.cwd())

        _str_path = str(_path).replace("\\", "/").strip("/")

        if _path.is_file():
            _resync_filter.append(_str_path)
            _verify_filter.append(_str_path.replace(".in", ".txt"))
            _dep_locks.append(_path.with_name(_path.name.replace(".in", ".txt")))

        else:
            _resync_filter.append(f"{_str_path}/*.in")
            _resync_filter.append(f"!{_str_path}/constraints.in")
            _verify_filter.append(f"{_str_path}/*.txt")
            _dep_locks.append(_path)


class _Action:
    __slots__ = ("defaults", "required_names")

    def __init__(self, *, required: collections.Sequence[str] = (), defaults: typing.Optional[ConfigT] = None) -> None:
        self.defaults: ConfigT = dict(_ACTION_DEFAULTS)
        self.defaults.update(defaults or ())
        self.required_names = frozenset(required or ())

    def process_config(self, config: ConfigT, /) -> ConfigT:
        output: ConfigT = dict(self.defaults)
        output.update(**config)
        return output


_ACTIONS: dict[str, _Action] = {
    "freeze-for-pr": _Action(defaults={"EXTEND_FILTERS": [], "FILTERS": _resync_filter}),
    "lint": _Action(),
    "pr-docs": _Action(),
    "publish": _Action(),
    "py-test": _Action(
        required=["PYTHON_VERSIONS"],
        defaults={"CODECLIMATE_TOKEN": "", "OSES": "[ubuntu-latest, macos-latest, windows-latest]"},
    ),
    "reformat": _Action(),
    "release-docs": _Action(),
    "resync-piped": _Action(defaults={"FILTERS": ["piped", "pyproject.toml"]}),
    "type-check": _Action(),
    "upgrade-locks": _Action(),
    "verify-locks": _Action(defaults={"EXTEND_FILTERS": [], "FILTERS": _verify_filter}),
    "verify-types": _Action(),
}


@nox.session(name="copy-actions")
def copy_actions(_: nox.Session) -> None:
    """Copy over the github actions from Piped without updating the git reference."""
    import jinja2

    env = jinja2.Environment(  # noqa: S701
        keep_trailing_newline=True,
        loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent.parent / "github" / "actions"),
    )

    env.filters["quoted"] = '"{}"'.format  # noqa: FS002

    to_write: dict[pathlib.Path, str] = {}
    if isinstance(_config.github_actions, dict):
        actions = iter(_config.github_actions.items())
        wild_card: collections.ItemsView[str, ConfigEntryT] = (_config.github_actions.get("*") or {}).items()

    else:
        actions: collections.Iterable[tuple[str, ConfigT]] = ((name, {}) for name in _config.github_actions)
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
        template = env.get_template(file_name)

        full_config = action.process_config(config)
        to_write[pathlib.Path("./.github/workflows") / file_name] = template.render(**full_config, config=_config)

    for path, value in to_write.items():
        with path.open("w+") as file:
            file.write(value)


def _to_valid_urls(session: nox.Session) -> typing.Optional[set[pathlib.Path]]:
    if session.posargs:
        return set(map(pathlib.Path.resolve, map(pathlib.Path, session.posargs)))


def _freeze_file(session: nox.Session, path: pathlib.Path, /) -> None:
    if not path.is_symlink():
        target = path.with_name(path.name[:-3] + ".txt")
        target.unlink(missing_ok=True)
        session.run(
            "pip-compile-cross-platform",
            "-o",
            str(target),
            "--min-python-version",
            _config.version_constraint,
            str(path),
        )


_EXTRAS_FILTER = re.compile(r"\[.+\]")


@nox.session(name="freeze-locks", reuse_venv=True)
def freeze_locks(session: nox.Session) -> None:
    """Freeze the dependency locks."""
    _install_deps(session, *_deps("freeze-locks"))
    valid_urls = _to_valid_urls(session)
    constraints_lock = pathlib.Path("./dev-requirements/constraints.txt")

    if not valid_urls:
        project = _pyproject_toml.get("project") or {}
        deps: list[str] = project.get("dependencies") or []
        if optional := project.get("optional-dependencies"):
            deps.extend(itertools.chain(*optional.values()))

        tl_requirements = pathlib.Path("./requirements.in")
        if tl_requirements.exists():
            with tl_requirements.open("r") as file:
                deps.extend(file.read().splitlines())

        constraints_in = pathlib.Path("./dev-requirements/constraints.in")
        if deps:
            with constraints_in.open("w+") as file:
                file.write("\n".join(deps) + "\n")

        else:
            constraints_in.unlink(missing_ok=True)
            constraints_lock.unlink(missing_ok=True)

    for lock_path in _config.dep_locks:
        if lock_path.is_file():
            _freeze_file(session, lock_path)
            continue

        for path in itertools.filterfalse(pathlib.Path.is_symlink, lock_path.glob("*.in")):
            _freeze_file(session, path)

    # We use this file as a constraints file and constraint files can't have extra
    # params according to the spec so these must be removed.
    # See https://github.com/pypa/pip/issues/8210 for more information.
    if constraints_lock.exists():
        with constraints_lock.open("r") as file:
            constraints_value = file.read()

        with constraints_lock.open("w") as file:
            file.write(_EXTRAS_FILTER.sub("", constraints_value))


@_filtered_session(name="verify-deps", reuse_venv=True)
def verify_deps(session: nox.Session) -> None:
    """Verify the dependency locks by installing them."""
    for path in itertools.chain.from_iterable(path.glob("*.txt") if path.is_dir() else (path,) for path in _dep_locks):
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
    # TODO: don't require installing .?
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, *_runtime_deps(), *_deps("lint"))
    _install_deps(session, "--no-deps", *_config.extra_test_installs, first_call=False)
    session.run("slotscheck", "-m", _config.assert_project_name())


@_filtered_session(reuse_venv=True, name="spell-check")
def spell_check(session: nox.Session) -> None:
    """Check this project's text-like files for common spelling mistakes."""
    _install_deps(session, *_deps("lint"))
    session.log("Running codespell")
    session.run("codespell", *_tracked_files(session), *_config.codespell_ignore_args(), log=False)


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


def _publish(session: nox.Session, /, *, env: typing.Optional[dict[str, str]] = None) -> None:
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, *_runtime_deps(), *_deps("publish"))
    # TODO: does this need to install .?
    _install_deps(session, "--no-deps", ".", first_call=False)

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
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, *_deps("tests"))
    _install_deps(session, *_config.extra_test_installs, first_call=False)
    # TODO: can import-mode be specified in the config.
    session.run("pytest", "-n", "auto", "--import-mode", "importlib")


@_filtered_session(name="test-coverage", reuse_venv=True)
def test_coverage(session: nox.Session) -> None:
    """Run this project's tests while recording test coverage."""
    project_name = _config.assert_project_name()
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, *_deps("tests"))
    _install_deps(session, *_config.extra_test_installs, first_call=False)
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
    # https://github.com/pypa/pip/issues/10362
    _install_deps(session, *_runtime_deps(), *_deps("type-checking"))
    _install_deps(session, *_config.extra_test_installs, first_call=False)
    _run_pyright(session, "--verifytypes", project_name, "--ignoreexternal")


@nox.session(name="copy-piped", reuse_venv=True)
def sync_piped(session: nox.Session) -> None:
    """Copy over Piped's configuration without fetching."""
    copy_actions(session)


@_filtered_session(name="fetch-piped", reuse_venv=True)
def fetch_piped(session: nox.Session) -> None:
    """Fetch Piped from upstream and resync."""
    session.run("git", "submodule", "update", "--remote", "piped", external=True)
    _install_deps(session, *_deps("nox"))
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
