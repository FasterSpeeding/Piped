import './global.just'

# The project name (e.g. top-level code file name for a Python project) used by some CICD tasks.

export PYTHON_PROJECT_NAME := env('PYTHON_PROJECT_NAME', '')

# Reformat this project's python files to fit the standard style
[group("format")]
[group("python")]
format-python:
    just execute-bash-script format_python

# Freeze the Python dependency locks
[group("freeze locks")]
[group("python")]
freeze-locks-python:
    just execute-bash-script freeze_python_locks

# Run this project's python files against the pre-defined ruff linters
[group("lint")]
[group("python")]
run-ruff:
    just execute-bash-script run_ruff

# Type-check the python project's code
[group("lint")]
[group("python")]
type-check-python:
    just execute-bash-script type_check_python

# Run all of this project's Python-specific linting checks
[group("lint")]
[group("python")]
lint-python:
    just execute-python-script just_call_by_groups lint python --ignore-recipes=freeze-locks
