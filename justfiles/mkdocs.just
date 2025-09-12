import './global.just'

# Generate docs for this project using Mkdoc.
generate-docs: ensure-artifacts-dir
    just execute-bash-script generate_docs
