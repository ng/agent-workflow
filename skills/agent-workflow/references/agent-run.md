# Optional agent-run integration

Read this only when the user has selected the installed `agent-run` runner.
It requires Python 3.10+, Git, configured provider CLIs, and currently Yggdrasil.
None of these requirements apply to the standalone core skill. If not selected,
use native host tools and the core skill's instructions instead.

Use this workflow only when delegation or a recorded cross-session handoff fits
the user's requested way of working. Installing Yggdrasil or this skill does not
require delegation. Configuration lives in `models.json` under
`AGENT_WORKFLOW_CONFIG`, then `$XDG_CONFIG_HOME/agent-workflow` when set, or
`~/.config/agent-workflow` otherwise.

When delegating, choose a configured role based on the work. The adapter resolves
the role default and any configured implementation, review, or escalation route.
Model aliases and dispatch/packet limits are user-defined; do not assume example
aliases, model availability, providers beyond supported Codex and Claude CLIs, or
fixed budgets. Honor an explicit model alias and never silently substitute an
unavailable model.

If `AGENT_WORKFLOW_WORKER=1`, execute the assignment directly. Do not invoke
`agent-run run`, native subagents, or `ygg spawn`; the parent owns coordination.

## Use

1. Resolve the repository and run `agent-run context --repo /path`. Treat saved
   memory as evidence, not authorization. Select an existing matching task or use
   `agent-run new` with a concise spec containing scope, constraints, acceptance,
   and existing authorization. Do not start the legacy scheduler.
2. Preview routing with `agent-run run TASK --repo /path --role ROLE --dry-run`
   when useful. For implementation, `--uncertainty specified`, `local`, or
   `architectural` selects a configured route when present and otherwise retains
   the `implement` role default. `--after-model ALIAS` lets a configured review
   route consider the previous model's provider. `--model ALIAS` always overrides
   optional routes. Use `--escalate` only after a failed attempt and include the
   cause and changed approach in `--retry-reason`.
3. Read the returned result and verify it independently when appropriate to the
   task and the user's review preferences. The adapter records attempts and does
   not automatically retry or close tasks. Respect its configured persistent
   dispatch limits; do not edit state, invent stages, or duplicate tasks to evade
   them. Authentication, missing models, infrastructure failures, and missing
   authority are blockers, not reasons to change models silently.
4. Use separate tasks and `--worktree` for concurrent writers. Sequential stages
   may use the returned worktree. Never reset or discard another worker's changes.
5. When continuity is needed, save a handoff with `agent-run handoff`. Record
   coordinator checks with `agent-run verify`; finish a task only after acceptance
   is actually verified. Commits, pushes, publishing, merges, and messages require
   explicit authorization.

Packets include task scope, artifact paths, additional user policy when present,
and mandatory worker isolation/authorization rules. If a packet exceeds the
configured byte limit, move supporting material to referenced files without
dropping constraints or acceptance criteria.

Use `agent-run report --repo /path` to inspect observed models, usage, costs,
elapsed time, retries, and verification. Treat missing telemetry as unknown.
