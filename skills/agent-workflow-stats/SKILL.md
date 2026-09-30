---
name: agent-workflow-stats
description: Show agent-run routing, token, and cost stats as a panel. Only run when the user invokes it.
disable-model-invocation: true
argument-hint: "[--session] [--repo PATH] [--task REF] [--since 7d] [--baseline ALIAS]"
allowed-tools: Bash(agent-run stats:*)
---

!`agent-run stats --panel $ARGUMENTS`

Show the panel above to the user exactly as printed, inside a fenced code block,
with no commentary. If no panel appears above (hosts that do not run the command
first), run `agent-run stats --panel` with the user's arguments and show its
output the same way. If `agent-run` is not installed, say so.
