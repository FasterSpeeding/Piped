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

target_xml="$ARTIFACTS_DIR/coverage.xml"
target_html="$ARTIFACTS_DIR/coverage_html"
target_report="$ARTIFACTS_DIR/.coverage"

if [[ -n "${TEST_PYTHON_VERSION:-}" ]]
then
    debug_echo "Installing Python $TEST_PYTHON_VERSION"
    mise_install "python@$TEST_PYTHON_VERSION" uv
else
    debug_echo "Installing project default Python version"
    mise_install python uv
fi

if [[ -n "${TRACK_COVERAGE:-}" ]]
then
    echo "Running pyright with coverage"

    uv run --group=test pytest \
        -n auto \
        --cov "$PYTHON_PROJECT_NAME" \
        --cov-report term \
        --cov-report "xml:$target_xml" \
        --cov-report "html:$target_html"

    rm -f "$target_report"
    mv "./.coverage" "$target_report"

    debug_echo "XML coverage report saved to $target_xml"
    debug_echo "HTML coverage report saved to $target_html"
    debug_echo ".coverage file saved to $target_report"
else
    echo "Running pyright"
    uv run --group=test pytest -n auto --import-mode importlib
fi
