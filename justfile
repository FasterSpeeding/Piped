import './justfiles/python-base.just'

# Default command
default:
    just --list

# Run reformatting jobs over the project's files
format: format-python

