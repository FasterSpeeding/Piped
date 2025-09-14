import './justfiles/python-base.just'

# Default command
default:
    just --list

# Run reformatting jobs over the project's files
[group("format")]
format: format-python

# Run linting checks over the project's files
[group("lint")]
lint: lint-misc lint-python
