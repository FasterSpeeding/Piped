PATH="./dev-requirements/nox.txt"
if [ -f "$PATH" ]; then
    export NOX_DEP="$PATH"
else
    export NOX_DEP="./piped/python/base-requirements/nox.txt"
fi
