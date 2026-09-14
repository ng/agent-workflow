# Optional Yggdrasil coordination

Use this integration only when the user selected Yggdrasil and the `ygg` CLI is
configured. It is not required for the core skill and does not require using
the optional `agent-run` runner.

Use installed CLI help and project conventions to find or create the relevant
task, check dependencies, and coordinate shared resources. Acquire and release
appropriate locks when working alongside other agents. Record verified outcomes
and handoffs in the existing task instead of creating a parallel ledger. Close
tasks only when their acceptance is met.

Do not assume an installed version has a particular subcommand or automatically
start its scheduler: queued tasks may belong to unrelated work. If the selected
service is unavailable, report the limitation and preserve a portable handoff;
do not silently switch task ownership or synchronization backends.
