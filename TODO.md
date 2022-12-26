Split up dev-dep files like publish.in into more atomic files.
Allow configuring whether pyright is allowed to fail.
Make the actions dir if it doesn't exist.
Have more copy handling (plus a skip_copy)config,
Add a non-template system for partially updating yaml and toml files.
verify-markup isn't actually failing when it fails
Verify piper config (that all the names work)
random idea could i add license handling to me CI
Allow for multiple constraint files
PR in a fix for Starlette's uses of typing.Callable without args in type hints.
Handle reauthing when a token returns a 403 to make sure if the token is ever externally revoked we handle that.
Probably listen for being removed from an installation to remove its tokens. # I think this might also need to cover when an installation is updated?
Ensure gogo.patch is in git ignore
