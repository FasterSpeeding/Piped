import pathlib
import sys

import nox

sys.path.insert(1, str(pathlib.Path("./python").absolute()))

from noxfile import *


@nox.session(name="freeze-dev-deps", reuse_venv=True)
def freeze_dev_deps(session: nox.Session) -> None:
    import noxfile

    noxfile.freeze_dev_deps(session)

    for path in pathlib.Path("./dev-requirements/").glob("*.in"):
        if not valid_urls or path.resolve() in valid_urls:
            target = path.with_name(path.name[:-3] + ".txt")
            target.unlink(missing_ok=True)
            session.run("pip-compile-cross-platform", "-o", str(target), "--min-python-version", "3.9,<3.12", str(path))
