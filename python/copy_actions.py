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
"""Copy over the github actions from Piped without updating the git reference."""

from __future__ import annotations

__all__ = []

import piped_shared.config as config

import pathlib
from collections import abc as collections
import itertools
import os
import jinja2


_DEFAULT_COMMITER_USERNAME = "always-on-duty[bot]"
_ACTION_DEFAULTS = {
    "ACTION_COMMITTER_EMAIL": f"120557446+{_DEFAULT_COMMITER_USERNAME}@users.noreply.github.com",
    "ACTION_COMMITTER_USERNAME": _DEFAULT_COMMITER_USERNAME,
    "DEFAULT_PY_VER": "3.11",
    "NOX_DEP_PATH": "./piped/python/base-requirements/nox.txt",
}


_config = config.Config.read(pathlib.Path("./"))
_RESYNC_FILTER = os.environ["RESYNC_FILTER"].split(",")
_VERIFY_FILTER = os.environ["VERIFY_FILTER"].split(",")

class _Action:
    __slots__ = ("defaults", "required_names")

    def __init__(
        self, *, required: collections.Sequence[str] = (), defaults: config.ConfigT | None = None
    ) -> None:
        self.defaults: config.ConfigT = dict(_ACTION_DEFAULTS)
        self.defaults.update(defaults or ())
        self.required_names = frozenset(required or ())

    def process_config(self, config: config.ConfigT, /) -> config.ConfigT:
        output: config.ConfigT = dict(self.defaults)
        output.update(**config)
        return output

_ACTIONS: dict[str, _Action] = {
    "clippy": _Action(),
    "docker-publish": _Action(defaults={"DOCKER_DEPLOY_CONTEXT": ".", "SIGN_IMAGES": "true"}),
    "freeze-for-pr": _Action(defaults={"EXTEND_FILTERS": [], "FILTERS": _RESYNC_FILTER}),
    "lint": _Action(),
    "pr-docs": _Action(),
    "publish": _Action(),
    "py-test": _Action(
        required=["PYTHON_VERSIONS"],
        defaults={
            "CODECLIMATE_TOKEN": "",
            "OSES": "[ubuntu-latest, macos-latest, windows-latest]",
            "REQUIRES_RUST": "",
        },
    ),
    "reformat": _Action(),
    "release-docs": _Action(defaults={"BRANCH_PUSHES": None}),
    "resync-piped": _Action(defaults={"FILTERS": ["piped", "piped.toml", "pyproject.toml"]}),
    "rustfmt": _Action(),
    "type-check": _Action(defaults={"REQUIRES_RUST": ""}),
    "update-licence": _Action(),
    "upgrade-locks": _Action(),
    "verify-locks": _Action(defaults={"EXTEND_FILTERS": [], "FILTERS": _VERIFY_FILTER}),
    "verify-types": _Action(defaults={"REQUIRES_RUST": ""}),
}


def main() -> None:
    env = jinja2.Environment(  # noqa: S701
        keep_trailing_newline=True,
        loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent.parent / "github" / "actions"),
    )

    env.filters["quoted"] = '"{}"'.format  # noqa: FS002

    to_write: dict[pathlib.Path, str] = {}
    if isinstance(_config.github_actions, dict):
        actions = iter(_config.github_actions.items())
        wild_card: collections.ItemsView[str, config.ConfigEntryT] = (
            _config.github_actions.get("*") or {}
        ).items()

    else:
        actions: collections.Iterable[tuple[str, config.ConfigT]] = (
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
        template = env.get_template(file_name)

        full_config = action.process_config(config)
        to_write[pathlib.Path("./.github/workflows") / file_name] = template.render(**full_config, config=_config)

    pathlib.Path("./.github/workflows").mkdir(exist_ok=True, parents=True)

    for path, value in to_write.items():
        with path.open("w+") as file:
            file.write(value)


if __name__ == "__main__":
    main()
