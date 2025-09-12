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
"""Cleanup any temporary files made in this project by its nox tasks."""
import logging
import pathlib
import shutil
import typing
from collections import abc as collections

_P = typing.ParamSpec("_P")

logging.basicConfig()
_LOGGER = logging.getLogger("Piped.cleanup")

RAW_PATHS = ["./artifacts", "./.nox", "./.pytest_cache", ".mypy_cache"]


def try_remove(
    path: pathlib.Path, callback: collections.Callable[_P, None], /, *args: _P.args, **kwargs: _P.kwargs
) -> None:
    try:
        callback(*args, **kwargs)

    except FileNotFoundError:
        _LOGGER.warning("[ SKIP ] '%s'", path)

    except Exception as exc:  # noqa: BLE001  # Do not catch blind exception: `Exception`
        _LOGGER.error("[ FAIL ] Failed to remove '%s': %s", path, exc)

    else:
        _LOGGER.info("[  OK  ] Removed '%s'")


def cleanup() -> None:
    """Cleanup temporary files created by CICD tasks."""
    for raw_path in RAW_PATHS:
        path = pathlib.Path(raw_path)
        try_remove(path, shutil.rmtree, str(path.absolute()))

    # Remove individual files
    for raw_path in ["./.coverage"]:
        path = pathlib.Path(raw_path)
        try_remove(path, path.unlink)

    # Remove egg info
    for path in pathlib.Path("./").glob("**/*.egg-info"):
        try_remove(path, path.unlink)


if __name__ == "__main__":
    cleanup()
