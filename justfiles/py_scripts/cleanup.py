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
import os
import pathlib
import shutil

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("Piped.cleanup")


CLEANUP_PATHS = [
    pathlib.Path(os.environ["ARTIFACTS_DIR"]),
    pathlib.Path("./.nox"),
    pathlib.Path("./.pytest_cache"),
    pathlib.Path(".mypy_cache"),
    pathlib.Path("./.coverage"),
]
"""Array of the paths to cleanup if found."""

if DIFF_FILE_PATHS := os.environ.get("DIFF_FILE_PATHS"):
    CLEANUP_PATHS.extend(map(pathlib.Path, DIFF_FILE_PATHS.split(",")))


def try_remove(path: pathlib.Path) -> None:
    """Try to remove a path and error log any failures.

    Parameters
    ----------
    path
        The path to delete.
    """
    if path.is_dir():

        def callback() -> None:
            shutil.rmtree(path)

    else:

        def callback() -> None:
            path.unlink()

    try:
        callback()

    except FileNotFoundError:
        _LOGGER.warning("[ SKIP ] '%s'", path)

    except Exception as exc:
        _LOGGER.exception("[ FAIL ] Failed to remove '%s'", path, exc_info=exc)

    else:
        _LOGGER.info("[  OK  ] Removed '%s'", path)


def cleanup() -> None:
    """Cleanup temporary files created by CICD tasks."""
    # Remove all files and with static links.
    for path in CLEANUP_PATHS:
        try_remove(path)

    # Remove egg info
    for path in pathlib.Path("./").glob("**/*.egg-info"):
        try_remove(path)


if __name__ == "__main__":
    cleanup()
