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
"""Execute detected Just jobs which have the specified groups."""
import argparse
import itertools
import json
import logging
import os
import sys
import shutil
import subprocess

import constants

logging.basicConfig(level=constants.LOG_LEVEL)
_LOGGER = logging.getLogger("Piped.just_call_by_groups")

IGNORE_RECIPES = set(os.environ.get("IGNORE_RECIPES", "").split(","))
EXCLUDE_GROUPS = set(os.environ.get("EXCLUDE_GROUPS", "").split(","))
_JUST_LOCATION = shutil.which("just")

if _JUST_LOCATION is None:
    error_message = "Missing just executable"
    raise RuntimeError(error_message)


def just_call_by_groups(match_groups: set[str], excluded_groups: set[str], ignored_recipes: set[str]) -> None:
    """Execute Just recipes which have the specified match groups.

    Parameters
    ----------
    match_groups
        Execute recipes which have all of the match groups attached.
    excluded_groups
        Ignore recipes with any of these excluded groups attached.
    ignored_recipes
        Set of names of specific recipes to ignore.
    """
    failed = False
    _LOGGER.debug("Searching for just recipes tagged with the following groups: %s", match_groups)

    if ignored_recipes:
        _LOGGER.debug("With the following recipes being excluded: %s", ignored_recipes)

    else:
        _LOGGER.debug("With no recipes being excluded")

    assert _JUST_LOCATION is not None
    output = subprocess.run(  # noqa: S603 - check for execution of untrusted input
        [_JUST_LOCATION, "--dump", "--dump-format", "json"],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )

    for recipe_name, recipe in json.loads(output.stdout)["recipes"].items():
        groups = {attr["group"] for attr in recipe["attributes"] if "group" in attr}

        if missing_groups := match_groups - groups:
            _LOGGER.debug("Ignoring recipe %r, missing the following groups: %s", recipe_name, missing_groups)
            continue

        if excluded_groups := groups & excluded_groups:
            _LOGGER.debug("Ignroing recipe %r, it has the following excluded groups: %s", recipe_name, excluded_groups)

        if recipe_name in ignored_recipes:
            _LOGGER.debug("Ignoring recipe %r, it's excluded by name", recipe_name)
            continue

        _LOGGER.info("Running task %r", recipe_name)
        try:
            subprocess.run(  # noqa: S603 - check for execution of untrusted input
                [_JUST_LOCATION, recipe_name], check=True)

        except subprocess.CalledProcessError:
            failed = True

        print()  # Space out logging sections  # noqa: T201 print found

    sys.exit(int(failed))


def comma_split(value: str) -> list[str]:
    """Splits a string by commas and strips the values."""
    return [v.strip() for v in value.split(",")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser("just_by_prefix")
    parser.add_argument(
        "--ignore-recipes",
        help="Recipes to ignore by name (can be a comma separate list)",
        action="extend",
        nargs="+",
        type=comma_split,
    )
    parser.add_argument(
        "--exclude-groups",
        help="Groups to exclude by name (can be a comma separate list)",
        action="extend",
        nargs="+",
        type=comma_split,
    )
    parser.add_argument("groups", help="The prefix to match just tasks by", nargs="+")
    args = parser.parse_args()

    excluded_groups = set(args.exclude_groups or ()) | EXCLUDE_GROUPS
    ignored_recipes = set(itertools.chain.from_iterable(args.ignore_recipes or ())) | IGNORE_RECIPES

    just_call_by_groups(set(args.groups), excluded_groups=excluded_groups, ignored_recipes=ignored_recipes)
