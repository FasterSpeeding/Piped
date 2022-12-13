Split up dev-dep files like publish.in into more atomic files.
Allow configuring whether mypy and pyright are allowed to fail.

```
Specifically from yuyo locally

nox > Command python -m pip install --upgrade -r 'dev-requirements\constraints.txt' -c 'dev-requirements\constraints.txt' -r 'dev-requirements\type-checking.txt' failed with exit code 1:
DEPRECATION: Constraints are only allowed to take the form of a package name and a version specifier. Other forms were originally permitted as an accident of the implementation, but were undocumented. The new implementation of the resolver no longer supports these forms. A possible replacement is replacing the constraint with a requirement. Discussion can be found at https://github.com/pypa/pip/issues/8210
ERROR: Constraints cannot have extras
```
