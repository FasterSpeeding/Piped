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

import itertools
import pathlib
import typing

import jinja2
import piped_shared

if typing.TYPE_CHECKING:
    from collections import abc as collections


_DEFAULT_COMMITER_USERNAME = "always-on-duty[bot]"
_ACTION_DEFAULTS = {
    "ACTION_COMMITTER_EMAIL": f"120557446+{_DEFAULT_COMMITER_USERNAME}@users.noreply.github.com",
    "ACTION_COMMITTER_USERNAME": _DEFAULT_COMMITER_USERNAME,
    "DEFAULT_PY_VER": "3.11",
    "PIPED_PATH": "./piped",
}


_CONFIG = piped_shared.Config.read(pathlib.Path("./"))


class _Action:
    __slots__ = ("defaults", "required_names", "requires")

    def __init__(
        self,
        *,
        required: collections.Sequence[str] = (),
        defaults: piped_shared.ConfigT | None = None,
        requires: collections.Sequence[str] = (),
    ) -> None:
        self.defaults: piped_shared.ConfigT = dict(_ACTION_DEFAULTS)
        self.defaults.update(defaults or ())
        self.required_names = frozenset(required or ())
        self.requires = frozenset(requires)

    def process_config(self, config: piped_shared.ConfigT, /) -> piped_shared.ConfigT:
        output: piped_shared.ConfigT = dict(self.defaults)
        output.update(**config)
        return output


_RESYNC_FILTER = ["piped"]
_RESYNC_FILTER.extend(str(path.absolute().relative_to(pathlib.Path.cwd())) for path in _CONFIG.dep_sources)

_SETUP_PY = "setup-py"
_ACTIONS: dict[str, _Action] = {
    "clippy": _Action(),
    "docker-publish": _Action(defaults={"CRON": "25 14 1 * *", "DOCKER_DEPLOY_CONTEXT": ".", "SIGN_IMAGES": "true"}),
    "freeze-for-pr": _Action(defaults={"EXTEND_FILTERS": [], "FILTERS": _RESYNC_FILTER}, requires=[_SETUP_PY]),
    "lint": _Action(requires=[_SETUP_PY]),
    "pr-docs": _Action(requires=[_SETUP_PY]),
    "publish": _Action(requires=[_SETUP_PY]),
    "py-test": _Action(
        required=["PYTHON_VERSIONS"],
        defaults={
            "CODECLIMATE_TOKEN": "",
            "OSES": "[ubuntu-latest, macos-latest, windows-latest]",
            "REQUIRES_RUST": "",
        },
        requires=[_SETUP_PY],
    ),
    "reformat": _Action(requires=[_SETUP_PY]),
    "release-docs": _Action(defaults={"BRANCH_PUSHES": None}, requires=[_SETUP_PY]),
    "resync-piped": _Action(defaults={"FILTERS": ["piped", "piped.toml", "pyproject.toml"]}, requires=[_SETUP_PY]),
    "rustfmt": _Action(requires=[_SETUP_PY]),
    "type-check": _Action(defaults={"REQUIRES_RUST": ""}, requires=[_SETUP_PY]),
    "update-licence": _Action(default={"CRON": "0 7 1 1 *"}, requires=[_SETUP_PY]),
    "upgrade-locks": _Action(default={"CRON": "0 12 1 * *"}, requires=[_SETUP_PY]),
    "verify-types": _Action(defaults={"REQUIRES_RUST": ""}, requires=[_SETUP_PY]),
}


def _normalise_path(path: str, /) -> str:
    return path.replace("_", "-").strip()


def _copy_composable_action(name: str, config: piped_shared.ConfigT) -> None:
    env = jinja2.Environment(  # noqa: S701
        keep_trailing_newline=True,
        loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent.parent / "github" / "actions" / name),
    )

    template = env.get_template("action.yml")
    env.filters["quoted"] = '"{}"'.format

    dest = pathlib.Path(".github/actions/") / name
    dest.mkdir(exist_ok=True, parents=True)
    (dest / "action.yml").write_text(template.render(**config, config=_CONFIG))


def main() -> None:
    env = jinja2.Environment(  # noqa: S701
        keep_trailing_newline=True,
        loader=jinja2.FileSystemLoader(pathlib.Path(__file__).parent.parent / "github" / "workflows"),
    )

    env.filters["quoted"] = '"{}"'.format

    dependencies: set[str] = set()
    to_write: dict[pathlib.Path, str] = {}
    wild_card = _CONFIG.github_actions.get("*") or {}

    for raw_file_name, raw_config in _CONFIG.github_actions.items():
        if raw_file_name == "*":
            continue

        file_name = _normalise_path(raw_file_name)
        action = _ACTIONS[file_name]
        config = {key.upper(): value for key, value in itertools.chain(wild_card.items(), raw_config.items())}
        if missing := action.required_names.difference(config.keys()):
            raise RuntimeError(f"Missing the following required fields for {file_name} actions: " + ", ".join(missing))

        file_path = f"{file_name}.yml"
        template = env.get_template(file_path)

        config = action.process_config(config)
        to_write[pathlib.Path("./.github/workflows") / file_path] = template.render(**config, config=_CONFIG)
        dependencies.update(action.requires)

    pathlib.Path("./.github/workflows").mkdir(exist_ok=True, parents=True)

    for path, value in to_write.items():
        path.write_text(value)

    if _SETUP_PY in dependencies:
        _copy_composable_action(_SETUP_PY, {**_ACTION_DEFAULTS, **wild_card})


if __name__ == "__main__":
    main()
