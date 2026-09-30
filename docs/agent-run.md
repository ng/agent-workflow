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
- `models.<alias>.price` (optional): `{ "input", "output", "cached_input",
  "cache_write" }` in USD per 1M tokens; `input` and `output` are required and
  the cache rates default to `input`. Used only by `agent-run stats`, and only
  needed to override the shipped `pricing.json` baseline (for example with
  negotiated rates).
- `prices` (optional): the same price objects keyed by model ID, for models no
  longer assigned to an alias, so lifetime stats can still price their runs.
- `baseline` (optional): the quality model that `agent-run stats` compares
  against ("same tokens on this model for everything"). Defaults to
  `roles.complex`.
- `quality_roles` (optional): roles that pay for a stronger model on purpose.
  Defaults to `plan`, `debug`, `complex`, `review`; the other roles are cost
  roles, which are expected to cost less than the baseline.
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
  "codex": "opus-5.5",
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
agent-run log [--repo /path/to/repo] [--limit 20] [--json]
agent-run prices [--json]
agent-run stats [--session [ID]] [--repo PATH] [--task REF] [--since 7d] [--baseline ALIAS] [--panel | --plain] [--brief] [--json]
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

`agent-run run` prints `agent-run: <role> → <alias> (<model>) · run <id>` to
stderr when it dispatches, and a warning if the provider reports a different
model than the one requested (the context-window suffix such as `[1m]` is
ignored, and bare family aliases such as `sonnet` match any model in that
family). `agent-run log` shows recent runs across all projects, newest first,
with requested and served models, state, tokens, cost, and run ID. Codex does
not currently report the served model, so those rows show `-`.

`agent-run stats` answers four questions:

- **Is anything wrong?** Checks list what needs attention: a cost role that
  costs more than the baseline would for the same tokens (with cheaper models
  from other cost roles as alternatives), a route with at least 5 runs and under
  80% success or 80% verification passes, runs missing usage (over 5%), stale or
  missing prices, and model mismatches. Passing checks fold into one line.
- **Is routing working?** Per role → model: succeeded/runs, success rate,
  coordinator verification results from `agent-run verify`, cost per
  successful run, and escalations.
- **Where does the money go?** Estimated cost per alias at list prices, with
  cost per run, runs, and tokens (model-ID variants of one alias combined).
- **Did cheaper models save money?** Each role's cost compared with the same
  tokens on the baseline model, split into cost roles (expected to save) and
  quality roles (stronger models by design, never flagged), then the total.

Estimates assume identical token counts and do not measure quality; runs
without usage or a price are excluded and counted.

Scope is lifetime across all projects by default. `--session` limits it to the
coordinating session: the `codex`/`claude` wrappers set
`AGENT_WORKFLOW_SESSION` when they launch, and every `agent-run run` records
it (Claude Code's own `CLAUDE_CODE_SESSION_ID` is the fallback). Runs from
before session tracking, or from sessions started with `command codex`, have no
session. `--brief` prints one line; with `--session` it adds a lifetime line.

Prices come from `pricing.json` next to `agent_run.py`: standard API list
prices as of its `as_of` date, with source URLs and notes (Claude cache writes
use the 1-hour rate; OpenAI prompts over 272K tokens cost more, which the
estimate cannot see). Lookup order is `prices` in `models.json`, then an alias's
`price`, then `pricing.json`; model IDs match ignoring `[1m]` and snapshot-date
suffixes. `agent-run prices` lists the baseline's age and sources and flags
unpriced aliases; stats marks prices stale after `stale_after_days` (30). Set
`AGENT_WORKFLOW_PRICING` to use a different file.

In a terminal, `agent-run stats` draws a boxed panel with usage bars (colour
unless `NO_COLOR` is set); piped output, which is what agents read, stays plain.
`--panel` and `--plain` force either view. In Claude Code, `/agent-workflow-stats
[args]` runs the panel and shows it verbatim; colour does not survive the chat
view.

Run the local checks with:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
bash -n install.sh shell.zsh
```
