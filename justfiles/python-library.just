import './python-base.just'

# Build this project using flit
[group("build")]
[group("build python")]
[group("python")]
build-python: ensure-artifacts-dir
    just execute-bash-script build_python

# Publish this project to pypi
[group("python")]
publish-python:
    just execute-bash-script publish_python

# Publish this project to test pypi
[group("python")]
publish-test-python:
    PYPI_TARGET="https://test.pypi.org/legacy/" just publish-python

# Check this project's slotted classes for common mistakes
[group("lint")]
[group("python")]
slot-check:
    just execute-bash-script slot_check

# Verify the type-completeness of types and objects exported by a library.
[group("lint")]
[group("python")]
verify-types:
    just execute-bash-script verify_types

# Run Python linting checks against this project's code
lint-python: base-lint-python slot-check verify-types
