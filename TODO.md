Split up dev-dep files like publish.in into more atomic files.
Look for a matching file in whatever project is calling this' dev-requirements dir and default back to well the defaults while installing requirements.
Split type-check session into separate mypy and pyright sessions
Allow configuring whether mypy and pyright are allowed to fail.
