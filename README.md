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

Use your host's skill directory (for example `~/.claude/skills`) as appropriate.
Keep the checkout in place if you use a symlink. Preserve an existing installation
before replacing it.

An optional Bash helper installs only the skill by default:

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

No model names, providers, review pipeline, or configuration schema are imposed.
The skill guides behavior; hard process limits and distributed locking require
support from the host or an optional integration.

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
