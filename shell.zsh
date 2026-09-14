# Optional interactive wrappers. `command codex` and `command claude` bypass them.
function codex() {
  command agent-run launch codex "$@"
}

function claude() {
  command agent-run launch claude "$@"
}
