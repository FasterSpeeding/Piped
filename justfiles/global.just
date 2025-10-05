set unstable := true
set shell := ["bash", "-eu", "-c"]
set script-interpreter := ["bash", "-eu"]
set allow-duplicate-variables := true

# The directory transient CICD artifacts are saved to

export ARTIFACTS_DIR := "./artifacts"
export JUST_TASKS_VERBOSE := env('JUST_TASKS_VERBOSE', '')

# "./gogo.patch" is deprecated
# Space separated list of files used to store diffs in CICD artifacts for the bot

export DIFF_FILE_PATHS := ARTIFACTS_DIR + "/gogo.patch ./gogo.patch"
export PYTHONUNBUFFERED := "true"
export BASH_SCRIPTS_DIR := source_directory() + '/bash_scripts'
export PY_SCRIPTS_DIR := source_directory() + '/py_scripts'

# Check for a saved diff and error if one found
check-diff-file:
    just execute-bash-script check_diff_file

# Default command
[default]
default:
    just --list

# Internal function used for executing bash script tasks
[private]
[script]
execute-bash-script $SCRIPT_NAME *FLAGS:
    bash -eu "$BASH_SCRIPTS_DIR/execute_bash_script.bash" {{ FLAGS }}

# Internal function used for executing Python script tasks
[private]
[script]
execute-python-script $SCRIPT_NAME *FLAGS:
    bash -eu "$BASH_SCRIPTS_DIR/execute_py_script.bash" {{ FLAGS }}

# Internal function used to ensure the artifacts directory exists
[private]
@ensure-artifacts-dir:
    just execute-bash-script ensure_artifacts_dir

# Lint the project's markup files
[group("lint")]
[group("misc")]
lint-markup:
    just execute-bash-script lint_markup

# Lint Renovate's config ("renovate.json5")
[group("lint")]
[group("misc")]
lint-renovate:
    just execute-bash-script lint_renovate

# Run general (not file type specific) formatters over all the project's files
[group("format")]
[group("misc")]
format-general:
    just execute-bash-script format_misc

# Format the project's markup files
[group("format")]
[group("misc")]
format-markup:
    just execute-bash-script format_markup

# Check this project's text-like files for common spelling mistakes
[group("lint")]
[group("misc")]
[script]
spell-check:
    just execute-bash-script spell_check

# Bump the end year of the project's licence to the current year
[group("misc")]
update-licence:
    just execute-python-script update_license

# Save the current package's diff to
save-diff: ensure-artifacts-dir
    just execute-bash-script save_diff

# Cleanup any temporary files made in this project by its nox tasks
[group("cleanup")]
cleanup:
    just execute-python-script cleanup
    just execute-python-script just_call_by_groups cleanup --ignore-recipes="cleanup"

# Run reformatting jobs over the project's files
[group("format")]
format:
    just execute-python-script just_call_by_groups format --ignore-recipes="format"

# Freeze this project's dependency locks
[group("freeze locks")]
freeze-locks:
    just execute-python-script just_call_by_groups '"freeze locks"' --ignore-recipes="freeze-locks"

# Run linting checks over the project's files
[group("lint")]
lint:
    just execute-python-script just_call_by_groups lint --ignore-recipes="lint,lint-python"
