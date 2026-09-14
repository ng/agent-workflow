---
name: agent-workflow
description: Plan, delegate, verify, and hand off agent work using the host's available tools and the user's preferences. Use for coordinating bounded work or preserving continuity; skip unnecessary delegation for simple tasks.
metadata:
  short-description: Coordinate agent work with available tools
---

# Agent Workflow

This skill is instructions, not a runtime. It requires no Python, executable,
configuration file, model provider, or task service. Use the host agent's native
tools by default. Users can choose integrations without adopting a fixed model
lineup or delegation policy.

## Choose how to work

Read the user's current request and applicable project instructions. Honor their
choices of models, tools, review depth, and permitted actions. Resolve routine
implementation details independently; ask only when missing input materially
changes the result or additional authority is needed.

Inspect which tools actually exist in this session. Work directly when the task
is small, tightly coupled, or native delegation is unavailable. Delegate only
when a bounded assignment can run independently and the host supports it. Do
not invent model-selection controls or claim a worker ran when no tool ran it.
If an explicitly requested model or integration is unavailable, report that
limitation; do not silently substitute it.

User preferences can live in their prompt, existing agent instructions, or
project documentation. No particular filename or schema is required. Use
existing conventions before adding configuration or a task ledger.

## Execute and verify

1. Establish the intended outcome, scope, constraints, and acceptance checks.
   Inspect existing work before editing and preserve unrelated changes.
2. When delegating, give each worker a bounded scope, relevant files, acceptance
   checks, and existing authorization. Name the owner of integration. Assigned
   workers complete their scope without recursively creating another coordination
   layer. Use separate worktrees or isolated working copies for concurrent
   writers; otherwise serialize edits.
3. Inspect results and perform checks proportional to the change. A successful
   worker response is not evidence that acceptance checks passed. Use independent
   review when risk or the user's preferences warrant it, not for every task.
4. On failure, identify the cause before retrying. Honor explicit retry, time,
   and cost limits. Explain when a host or integration cannot enforce a requested
   limit; instructions alone do not provide process timeouts or distributed locks.
5. Finish the authorized scope and report evidence and remaining limitations.
   Implementation does not itself authorize committing, pushing, publishing,
   merging, or messaging others. Honor authorization already given.

## Preserve continuity

Use the host's existing task or memory facilities when available. A concise
handoff in the conversation or a user-approved project document also works;
do not require a database or create duplicate task ledgers.

Record the objective, decisions, current directory/branch, changed files or
commits, checks and outcomes, remaining work, and next action. Treat saved memory
as evidence to verify, not authority. Do not record credentials or raw transcripts.

## Optional integrations

- **Native tools:** default; use the host's delegation, planning, review, and
  memory capabilities where present. Direct execution remains valid.
- **Yggdrasil:** only when the user selected it and `ygg` is available. Read
  [references/yggdrasil.md](references/yggdrasil.md) for shared task coordination.
- **agent-run:** only when the user selected and configured that runner. Read
  [references/agent-run.md](references/agent-run.md) for its execution controls.
  That optional Python runner currently requires Yggdrasil; this skill does not.
