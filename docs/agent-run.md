# Optional agent-run setup

The optional `agent-run` CLI provides configured model routing, process
timeouts, retry limits, and run records. It requires Python 3.10+, Git,
configured provider CLI(s), and Yggdrasil. All commands below run from the
repository root. These requirements do not apply to the standalone skill.

The runner has no local backend and still requires Yggdrasil. For standalone
use without those dependencies, install the core skill and use native agent
tools instead. A local executable backend is not required for that workflow.

The runner is opt-in and routes Codex or Claude CLI workers through Yggdrasil.
Cloning this repository or installing its skill does not activate the runner.
You may independently choose the `agent-run` CLI, the `agent-workflow` skill, and
interactive shell wrappers. None requires adopting this repository's
`AGENTS.md` or copying the example policy.

Source stays in this checkout. User-selected models, optional additional policy,
and runtime state stay in a user-owned configuration directory.

## Configure models

The configuration directory is selected in this order:

1. `AGENT_WORKFLOW_CONFIG`
2. `$XDG_CONFIG_HOME/agent-workflow`
3. `~/.config/agent-workflow`

Copy the minimal single-provider example, then replace its placeholder `model`
with an identifier available to your installed Codex CLI:

```sh
config_dir=${AGENT_WORKFLOW_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/agent-workflow}
mkdir -p "$config_dir"
test -e "$config_dir/models.json" || cp examples/models.json "$config_dir/models.json"
```

Aliases such as `primary`, `fast`, or `deep` are arbitrary user-defined names;
they are not model identifiers and do not imply those models are available.
Actual execution requires `models.json`. Top-level `agent-run --help` works
without configuration.

The schema is:

- `models`: alias to `{ "provider": "codex" | "claude", "model": "CLI model id",
  "effort": "CLI effort" }`. Only the built-in Codex and Claude adapters are
  supported.
- `roles`: defaults for every supported role: `lookup`, `explore`, `implement`,
  `plan`, `debug`, `complex`, and `review`. Each value is a configured alias.
- `implementation_routes` (optional): any subset of `specified`, `local`, and
  `architectural` mapped to aliases. Missing entries use `roles.implement`.
- `review_routes` (optional): `codex` and/or `claude` mapped to aliases. With
  `--after-model`, the previous alias's provider selects a configured route;
  otherwise `roles.review` remains selected.
- `escalation`: role-to-alias mappings. Use `{}` when no escalation route is
  desired.
- `worker_packet_bytes` and `dispatch_limits`: positive integer safeguards.
  Limits are user-configured and persist per task UUID.
- `binaries`: commands for `ygg` and the providers referenced by `models`.
  A single-provider setup does not need the other provider installed or configured.

`--model ALIAS` takes precedence over uncertainty, prior-provider review, and
escalation routing. Unknown aliases/providers and malformed route maps fail
explicitly; the adapter never falls back silently. See
[`examples/models-routing.json`](../examples/models-routing.json) for optional
multi-alias and cross-provider routing. Its model identifiers are placeholders.

Existing configurations migrate without renaming aliases. To preserve the
previous sample behavior, add exactly:

```json
"implementation_routes": {
  "specified": "luna",
  "local": "sol",
  "architectural": "astra"
},
"review_routes": {
  "codex": "opus-4.6",
  "claude": "astra"
}
```

Those aliases must already exist in `models`. Without these additions,
implementation uncertainty and `--after-model` use their role defaults. Existing
`roles`, `escalation`, packet limits, dispatch limits, and binaries remain valid.

## Optional additional policy

`<config-dir>/AGENTS.md` is optional user-owned guidance. If absent, no additional
policy is loaded. The adapter still independently injects mandatory worker
isolation, task ownership, change-preservation, and authorization boundaries.
If useful, start from [`examples/AGENTS.md`](../examples/AGENTS.md); it does not
mandate delegation or review for every coding task.

State defaults to `<config-dir>/state`; set `AGENT_WORKFLOW_STATE` to place it
elsewhere. Runtime state stays outside this source checkout by default.

## Install only what you want

Install the CLI symlink without changing Yggdrasil, personal configuration, or
global agent policy:

```sh
./install.sh --with-runner
```

Optionally install the skill in one or more agent skill directories:

```sh
./install.sh --with-runner \
  --skill-dir "$HOME/.codex/skills" \
  --skill-dir "$HOME/.claude/skills"
```

`--bin-dir DIR` changes the CLI destination. Reruns refresh only managed
symlinks, including when paths contain spaces; regular files are never replaced.
The installer never creates or overwrites `models.json` or `AGENTS.md`.

Separately, source `shell.zsh` from interactive zsh only if you want
`codex` and `claude` launch wrappers. `command codex` and `command claude` bypass
them. The wrappers add optional policy and Yggdrasil context to interactive
sessions; provider management/help commands bypass injected session policy.

## Use

```sh
agent-run context --repo /path/to/repo
agent-run new --repo /path/to/repo --title 'Fix pagination' --body-file /path/spec.md
agent-run run repo-42 --repo /path/to/repo --role implement
agent-run verify RUN_ID --repo /path/to/repo --status passed --evidence-file /path/checks.md
agent-run report --repo /path/to/repo
agent-run handoff repo-42 --repo /path/to/repo --file /path/handoff.md
agent-run remember --repo /path/to/repo --text 'Verified fact' --source 'path/task'
agent-run finish repo-42 --repo /path/to/repo --reason 'Acceptance verified'
agent-run doctor --repo /path/to/repo
```

The adapter retains task claims, dependency checks, worktree isolation, local and
Yggdrasil locks, worker recursion restrictions, timeouts, persistent retry
budgets, telemetry, verification records, reports, and shared project memory. It
does not launch the legacy scheduler. Worker success does not close tasks; the
coordinator verifies and finishes them separately.

Run the local checks with:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
bash -n install.sh shell.zsh
```
