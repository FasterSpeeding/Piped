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
"""Utility library used by Piped."""

from __future__ import annotations

__all__ = []

import pathlib
import re
import typing
from collections import abc as collections

import pydantic

try:
    import tomli as tomllib

except ImportError:
    import tomllib

if typing.TYPE_CHECKING:
    from typing_extensions import Self

ConfigEntryT = typing.Union[dict[str, str], list[str], str, None]
ConfigT = dict[str, ConfigEntryT]


class Config(pydantic.BaseModel):
    """Configuration class for the project config."""

    bot_actions: set[str] = pydantic.Field(
        default_factory=lambda: {"Freeze PR dependency changes", "Resync piped", "Reformat PR code", "Run Rustfmt"}
    )
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
    version_constraint: typing.Optional[str] = None

    def assert_project_name(self) -> str:
        if not self.project_name:
            raise RuntimeError("This CI cannot run without project_name")

        return self.project_name

    def codespell_ignore_args(self) -> list[str]:
        if self.codespell_ignore:
            return ["--ignore-regex", self.codespell_ignore]

        return []

    @classmethod
    def read(cls, base_path: pathlib.Path, /) -> Self:
        for file_name, extractor in _TOML_PARSER.items():
            path = base_path / file_name
            if not path.exists():
                continue

            with path.open("rb") as file:
                return cls.parse_obj(extractor(tomllib.load(file)))

        raise RuntimeError("Couldn't find config file")

    @classmethod
    async def read_async(cls, base_path: pathlib.Path, /) -> Self:
        import anyio.to_thread

        return await anyio.to_thread.run_sync(cls.read, base_path)

    def version(self, pyproject_toml: typing.Optional[dict[str, typing.Any]], /) -> str:
        if self.version_constraint:
            return self.version_constraint

        try:
            if pyproject_toml:
                return pyproject_toml["project"]["requires-python"].lstrip(">=")

        except KeyError:
            pass

        return "3.9,<3.12"


_TOML_PARSER: dict[str, collections.Callable[[dict[str, typing.Any]], dict[str, typing.Any]]] = {
    "pyproject.toml": lambda data: data["tool"]["piped"],
    "piped.toml": lambda data: data,
}
