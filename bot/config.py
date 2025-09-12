# BSD 3-Clause License
#
# Copyright (c) 2020-2025, Faster Speeding
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
"""Utility library used by Piped."""

from __future__ import annotations

__all__ = []

import dataclasses
import enum
import pathlib
import re
import tomllib
import typing
from typing import Self

if typing.TYPE_CHECKING:
    from collections import abc as collections

_T = typing.TypeVar("_T")
_DefaultT = typing.TypeVar("_DefaultT")

ConfigEntryT = dict[str, str] | list[str] | str | None
ConfigT = dict[str, ConfigEntryT]


_DEFAULT_ACTIONS = ["Freeze PR dependency changes", "Resync piped", "Reformat PR code", "Run Rustfmt"]
_DEFAULT_DEP_SOURCES: list[pathlib.Path] = [pathlib.Path("./pyproject.toml")]


class _NoValueEnum(enum.Enum):
    VALUE = object()


_NoValue = typing.Literal[_NoValueEnum.VALUE]
_NO_VALUE: typing.Literal[_NoValueEnum.VALUE] = _NoValueEnum.VALUE


def _validate_list(path_to: str, array: list[typing.Any], expected_type: type[_T] | tuple[type[_T], ...]) -> list[_T]:
    for index, value in enumerate(array):
        if not isinstance(value, expected_type):
            error_message = f"Expected a {expected_type} for {path_to}[{index}] but found {type(value)}"
            raise TypeError(error_message)

    return typing.cast("list[_T]", array)


def _validate_list_entry(
    data: dict[str, typing.Any],
    key: str,
    expected_type: type[_T] | tuple[type[_T], ...],
    /,
    *,
    default_factory: collections.Callable[[], list[_T]] | None = None,
    path_to: str | None = None,
) -> list[_T]:
    try:
        found = data[key]

    except KeyError:
        if default_factory is not None:
            return default_factory()

        error_message = "Missing required key"
        raise RuntimeError(error_message) from None

    path_to = path_to or f"[{key!r}]"
    if not isinstance(found, list):
        error_message = f"Expected a list for {path_to}, found {type(found)}"
        raise TypeError(error_message)

    return _validate_list(path_to, found, expected_type)


@typing.overload
def _validate_entry(data: dict[str, typing.Any], key: str, expected_type: type[_T] | tuple[type[_T], ...], /) -> _T: ...


@typing.overload
def _validate_entry(
    data: dict[str, typing.Any], key: str, expected_type: type[_T] | tuple[type[_T], ...], /, *, default: _DefaultT
) -> _T | _DefaultT: ...


def _validate_entry(
    data: dict[str, typing.Any],
    key: str,
    expected_type: type[_T] | tuple[type[_T], ...],
    /,
    *,
    default: _NoValue | _DefaultT = _NO_VALUE,
) -> _T | _DefaultT:
    try:
        value = data[key]

    except KeyError:
        if default is not _NO_VALUE:
            return default

        error_message = f"Missing required key {key!r}"
        raise RuntimeError(error_message) from None

    if not isinstance(value, expected_type):
        error_message = f"Expected a {expected_type} for [{key!r}] but found {type(value)}"
        raise TypeError(error_message)

    return value


_DEFAULT_EXTRA_INSTALLS = {"slot_check": ["."], "test": ["."], "verify_types": ["."]}


@dataclasses.dataclass(kw_only=True, slots=True)
class Config:
    """Configuration class for the project config."""

    bot_actions: set[str]
    default_sessions: list[str]
    dep_sources: list[pathlib.Path]
    extra_installs: dict[str, list[str]]
    hide: list[str]
    mypy_allowed_to_fail: bool
    mypy_targets: list[str]
    path_ignore: re.Pattern[str] | None
    project_name: str | None = None
    top_level_targets: list[str]
    version_constraint: str | None

    def assert_project_name(self) -> str:
        if not self.project_name:
            error_message = "This CI cannot run without project_name"
            raise RuntimeError(error_message)

        return self.project_name

    @classmethod
    def read(cls, base_path: pathlib.Path, /) -> Self:
        for file_name, extractor in _TOML_PARSER.items():
            path = base_path / file_name
            if not path.exists():
                continue

            with path.open("rb") as file:
                data = extractor(tomllib.load(file))
                break

        else:
            error_message = "Couldn't find config file"
            raise RuntimeError(error_message)

        bot_actions = set(_validate_list_entry(data, "bot_actions", str, default_factory=_DEFAULT_ACTIONS.copy))
        default_sessions = _validate_list_entry(data, "default_sessions", str)

        if "dep_sources" in data:
            dep_sources = [pathlib.Path(path) for path in _validate_list_entry(data, "dep_sources", str)]

        else:
            dep_sources = _DEFAULT_DEP_SOURCES

        extra_installs = _DEFAULT_EXTRA_INSTALLS.copy()
        raw_extra_installs = _validate_entry(data, "extra_installs", dict, default=None) or {}
        for key in raw_extra_installs:
            path_to = "['extra_installs']"
            if not isinstance(key, str):
                error_message = f"Unexpected key found in {path_to}. Expected a string but found {key!r}"
                raise TypeError(error_message)

            extra_installs[key] = _validate_list_entry(raw_extra_installs, key, str, path_to=f"{path_to}[{key!r}]")

        hide = _validate_list_entry(data, "hide", str, default_factory=list)
        mypy_allowed_to_fail = _validate_entry(data, "mypy_allowed_to_fail", bool, default=False)
        mypy_targets = _validate_list_entry(data, "mypy_targets", str, default_factory=list)
        path_ignore = _validate_entry(data, "path_ignore", str, default=None)

        if path_ignore is not None:
            path_ignore = re.compile(path_ignore)

        project_name = _validate_entry(data, "project_name", str, default=None)
        top_level_targets = _validate_list_entry(data, "top_level_targets", str)
        version_constraint = _validate_entry(data, "version_constraint", str, default=None)
        return cls(
            bot_actions=bot_actions,
            default_sessions=default_sessions,
            dep_sources=dep_sources,
            extra_installs=extra_installs,
            hide=hide,
            mypy_allowed_to_fail=mypy_allowed_to_fail,
            mypy_targets=mypy_targets,
            path_ignore=path_ignore,
            project_name=project_name,
            top_level_targets=top_level_targets,
            version_constraint=version_constraint,
        )

    @classmethod
    async def read_async(cls, base_path: pathlib.Path, /) -> Self:
        import anyio.to_thread  # noqa: PLC0415  # `import` should be at the top-level of a file

        return await anyio.to_thread.run_sync(cls.read, base_path)

    def version(self, pyproject_toml: dict[str, typing.Any] | None, /) -> str:
        if self.version_constraint:
            return self.version_constraint

        try:
            if pyproject_toml:
                return pyproject_toml["project"]["requires-python"].lstrip(">=")

        except KeyError:
            pass

        return "3.11,<3.15"


_TOML_PARSER: dict[str, collections.Callable[[dict[str, typing.Any]], dict[str, typing.Any]]] = {
    "pyproject.toml": lambda data: data["tool"]["piped"],
    "piped.toml": lambda data: data,
}
