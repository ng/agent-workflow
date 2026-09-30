# Agent Workflow

A standalone skill for planning, delegation, verification, and handoffs using
the tools your agent already provides.

**The skill needs no Python, executable, configuration file, or Yggdrasil.**
Native agent tools are the default. If delegation isn't available or useful,
the agent works directly.

## Install the skill

Copy the [`skills/agent-workflow`](skills/agent-workflow) directory into your
agent's skills directory. That's the entire installation; the other repository
files are optional tooling or development files.

For a local checkout, you can instead create a symlink:

```sh
mkdir -p "$HOME/.codex/skills"
ln -s "$PWD/skills/agent-workflow" "$HOME/.codex/skills/agent-workflow"
```

Use your host's skill directory as appropriate. For Claude Code, copy or symlink
the complete directory to `~/.claude/skills/agent-workflow`, then invoke
`/agent-workflow`. Keep the checkout in place if you use a symlink. Preserve an
existing installation before replacing it. Claude Code's official documentation
covers [skill directories, references, symlinks, and invocation](https://code.claude.com/docs/en/skills).

The optional [`skills/agent-workflow-stats`](skills/agent-workflow-stats) skill
adds `/agent-workflow-stats` in Claude Code. It renders `agent-run stats --panel`
(checks, route quality, cost by model, and whether cheaper models saved money) and needs the optional runner.
Arguments pass through, for example `/agent-workflow-stats --session`.

An optional Bash helper installs the skills by default:

```sh
./install.sh --skill-dir "$HOME/.codex/skills"
./install.sh --skill-dir "$HOME/.claude/skills"
```

With no arguments, the helper uses `~/.codex/skills`. It does not launch Python,
install `agent-run`, or create model configuration. Manual copying doesn't
require Bash either.

## Use and customize

Invoke `$agent-workflow` in a host that supports named skills, or ask the agent
to follow its instructions. Use existing agent instructions or your prompt to
choose how you work, for example:

> Work directly on small changes. Delegate independent investigations when
> native workers are available. Use independent review for risky changes and
> keep a short handoff in the conversation.

No model names, providers, or review pipeline are imposed. The skill guides
behavior; hard process limits and distributed locking require support from the
host or an optional integration.

Model routing is also optional. The bundled
[`routing.example.json`](skills/agent-workflow/references/routing.example.json)
is a minimal single-model template, never active configuration. If you choose to
use it, copy it without overwriting an existing file to a user-owned
`models.json`. The skill reads an explicitly named file first; otherwise it uses
`models.json` under `AGENT_WORKFLOW_CONFIG` (a directory), then
`$XDG_CONFIG_HOME/agent-workflow`, then `~/.config/agent-workflow`. Missing
ordinary optional configuration leaves current host defaults in place. Explicit
missing, unreadable, or malformed configuration is reported rather than skipped.
See the [portable routing procedure](skills/agent-workflow/references/routing.md).
An existing user-owned file at that location opts into routing; the skill checks
it unless you disable file-based routing. Installation never creates or replaces it.

This JSON is instruction data read by the skill, not a Claude Code settings
schema or autoloaded native configuration. Claude's native model and effort
controls are used only when actually exposed; cross-provider selection requires
an explicitly available external integration. See Claude Code's official
[subagent documentation](https://code.claude.com/docs/en/sub-agents).

## Optional integrations

| Choice | Adds | Requirements |
| --- | --- | --- |
| Native agent tools | Existing host delegation and continuity | No extra runtime; direct work also supported |
| Yggdrasil | Shared tasks, locks, and coordination | Installed/configured `ygg` service |
| `agent-run` | Model routing, process controls, retry budgets, and run records | Python 3.10+, Git, provider CLI(s), and currently Yggdrasil |

These integrations are independent choices, not prerequisites for the skill.
The bundled runner still requires Yggdrasil; a local runner backend has not been
implemented. This does not limit standalone use of the skill.

To opt into the existing runner as well as the skill:

```sh
./install.sh --with-runner
```

See [runner setup and configuration](docs/agent-run.md). Existing runner
installations and external personal configuration remain supported.

## Development

Python is used for the optional runner and its tests, not to install or use the
skill. Run its regression checks with:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
bash -n install.sh shell.zsh
```
