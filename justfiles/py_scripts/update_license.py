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
"""Update the license files in a project to be marked as current year."""
import datetime
import logging
import pathlib
import re
import shutil
import subprocess
from collections import abc as collections

logging.basicConfig(level=logging.INFO)

_LOGGER = logging.getLogger("update license")
_LICENCE_PATTERN = re.compile(r"(Copyright \(c\) (\d+-?\d*))")


def _update_licence(match: re.Match[str]) -> str:
    licence_str, date_range = match.groups()
    start = date_range.split("-", 1)[0]
    current_year = str(datetime.datetime.now(tz=datetime.UTC).year)

    if start == current_year:
        return licence_str

    return f"{licence_str.removesuffix(date_range)}{start}-{current_year}"


_LICENCE_FILE_PATTERN = re.compile(r".*(rs|py)|LICENSE")
_GIT_LOCATION = shutil.which("git")

if _GIT_LOCATION is None:
    error_message = "Missing Git executable"
    raise RuntimeError(error_message)


def _tracked_files() -> collections.Iterable[str]:
    """Get an iterable of the local changes currently tracked by GIT."""
    assert _GIT_LOCATION is not None
    output = subprocess.run(  # noqa: S603 - check for execution of untrusted input
        [_GIT_LOCATION, "--no-pager", "grep", "--threads=1", "-l", ""],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return output.stdout.splitlines()


def update_licence() -> None:
    """Bump the end year of the project's licence to the current year."""
    for path in map(pathlib.Path, _tracked_files()):
        if not _LICENCE_FILE_PATTERN.fullmatch(path.name):
            continue

        data = path.read_text()
        new_data = _LICENCE_PATTERN.sub(_update_licence, data)

        if new_data != data:
            _LOGGER.info("Updating %s", path)
            path.write_text(new_data)

        else:
            _LOGGER.info("Skipping %s (already up-to-date)", path)


if __name__ == "__main__":
    update_licence()
