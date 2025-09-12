import './global.just'

# The project name (e.g. top-level code file name for a Python project) used by some CICD tasks.
export PYTHON_PROJECT_NAME := env('PYTHON_PROJECT_NAME', '')

# Reformat this project's modules to fit the standard style
[group("format")]
[group("python")]
format-python:
    just execute-bash-script format_python

# Freeze the Python dependency locks
[group("python")]
freeze-python-locks:
    just execute-bash-script freeze_python_locks

# Run this project's modules against the pre-defined ruff linters
[group("lint")]
[group("python")]
run-ruff:
    just execute-bash-script run_ruff

# Type-check the python project's code
[group("lint")]
[group("python")]
type-check-python:
    just execute-bash-script type_check_python

set allow-duplicate-recipes := true

# The lint python jobs implemented for all Python projects
[private]
base-lint-python: run-ruff type-check-python

# Run Python linting checks against this project's code
lint-python: base-lint-python

unexport allow-duplicate-recipes
