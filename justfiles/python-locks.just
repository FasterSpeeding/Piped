import './global.just'

# Freeze the Python dependency locks
[group("freeze locks")]
[group("python")]
freeze-locks-python:
    just execute-bash-script freeze_python_locks
