#!/usr/bin/env bash set -eu

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
source $(dirname "$0")/shared.bash

mise_install python uv pipx:pre-commit-hooks

json_paths=()
toml_paths=()
xml_paths=()
yaml_paths=()
just_paths=()

while read -rd $'\0' file_path
do
    if [[ ! -f "$file_path" ]]
    then
        continue
    fi

    case "$(basename $file_path)" in
        *.json) json_paths+=("$file_path") ;;
        *.toml) toml_paths+=("$file_path") ;;
        *.xml) xml_paths+=("$file_path") ;;
        *.yaml|*.yml) yaml_paths+=("$file_path") ;;
        *.just|justfile) just_paths+=("$file_path") ;;
    esac
done < <(git grep --cached -Ilze '')


EXIT_CODES=()

echo "Running pre-commit-hooks.check-json over ${#json_paths[@]} files"
echo "${json_paths[@]}" | xargs -n1 check-json || EXIT_CODES+=($?)

echo "Running pre-commit-hooks.check-toml over ${#toml_paths[@]} files"
echo "${toml_paths[@]}" | xargs -n1 check-toml || EXIT_CODES+=($?)

echo "Running pre-commit-hooks.check-xml over ${#xml_paths[@]} files"
echo "${xml_paths[@]}" | xargs -n1 check-xml || EXIT_CODES+=($?)

echo "Running pre-commit-hooks.check-yaml over ${#yaml_paths[@]} files"
echo "${yaml_paths[@]}" | xargs -n1 check-yaml || EXIT_CODES+=($?)

echo "Running just --fmt --check --unsafe over ${#just_paths[@]} files"
echo "${just_paths[@]}" | xargs -n1 just --fmt --check --unstable -f || EXIT_CODES+=($?)


decide_exit ${EXIT_CODES[@]}
