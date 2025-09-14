set unstable := true
set shell := ["mise", "exec", "--", "bash", "-eu", "-c"]
set script-interpreter := ["mise", "exec", "--", "bash", "-eu"]

# The directory transient CICD artifacts are saved to

export ARTIFACTS_DIR := "./artifacts"

# "./gogo.patch" is deprecated
# Space separated list of files used to store diffs in CICD artifacts for the bot

export DIFF_FILE_PATHS := ARTIFACTS_DIR + "/gogo.patch ./gogo.patch"

# Check for a saved diff and error if one found
check-diff-file:
    just execute-bash-script check_diff_file

# Internal function used for executing bash script tasks
[private]
[script]
execute-bash-script script-name:
    path="{{ source_directory() }}/bash_scripts/{{ script-name }}.bash"
    echo "Execution bash script at $path"
    bash -eu "$path"

# Internal function used for executing Python script tasks
[private]
[script]
execute-python-script script-name:
    path="{{ source_directory() }}/py_scripts/{{ script-name }}.py"
    echo "Executing Pythons script at $path"
    python "$path"

# Internal function used to ensure the artifacts directory exists
[private]
@ensure-artifacts-dir:
    just execute-bash-script ensure_artifacts_dir

# Cleanup any temporary files made in this project by its nox tasks
cleanup:
    just execute-python-script cleanup

# Lint the project's markup files
[group("lint")]
[group("misc")]
lint-markup:
    just execute-bash-script lint_markup

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
    codespell

# Bump the end year of the project's licence to the current year
[group("misc")]
update-licence:
    just execute-python-script update_license

# Save the current package's diff to
save-diff: ensure-artifacts-dir
    just execute-bash-script save_diff

# Format this project's miscellaneous files
[group("format")]
[group("misc")]
format-misc: format-general format-markup

# Lint this project's miscellaneous files
[group("lint")]
[group("misc")]
lint-misc: lint-markup spell-check
