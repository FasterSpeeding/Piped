import './global.just'


# Reformat this project's rust files to fit the standard style
[group("format")]
[group("rust")]
format-rust:
    just execute-bash-script fmt

# Freeze the Rust dependency locks
[group("freeze locks")]
[group("rust")]
freeze-locks-rust:
    just execute-bash-script generate-lockfile

# Run this project's rust files against the pre-defined clippy linters
[group("lint")]
[group("rust")]
lint-rust:
    just execute-bash-script clippy --all-features
