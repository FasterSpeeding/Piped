set unstable

set shell := ["mise", "exec", "--", "bash", "-eu", "-c"]
set script-interpreter := ["mise", "exec", "--", "bash", "-eu"]

# The directory transient CICD artifacts are saved to
export ARTIFACTS_DIR := "./artifacts"

# "./gogo.patch" is deprecated
export DIFF_FILE_PATHS := ARTIFACTS_DIR + "/gogo.patch,./gogo.patch"

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

# Enternal function used to ensure the artifacts directory exists
@ensure-artifacts-dir:
    just execute-bash-script ensure_artifacts_dir

# Cleanup any temporary files made in this project by its nox tasks
cleanup:
    just execute-python-script cleanup

# Reformat this project's files to fit the standard style
[group("format")]
format-general:
    just execute-bash-script format_general

# Check this project's text-like files for common spelling mistakes
[group("lint")]
spell-check:
    codespell

# Bump the end year of the project's licence to the current year
[group("format")]
update-licence:
    just execute-python-script update_license

# Save the current package's diff to 
save-diff: ensure-artifacts-dir
    just execute-bash-script save_diff

# Check for a saved diff and error if one found
check-diff-file:
    just execute-bash-script check_diff_file
