# Optional portable routing

This file describes an optional, user-owned `models.json` that the skill can
read as instructions. It does not add a runtime or require Python, an executable,
Yggdrasil, or delegation. When ordinary optional configuration is absent, follow the
applicable prompt and project instructions and use the current host defaults; do
not claim that automatic model routing occurred.

The bundled [routing.example.json](routing.example.json) is a minimal template,
not active configuration and not a native settings schema for any host. Copy it
outside the skill installation only when the user wants persistent routing, and
never overwrite an existing file. Keeping configuration outside the installation
lets skill updates leave it intact.

## Locate configuration

If the user explicitly specifies a configuration file, use that exact file.
Otherwise select one directory, in this order, and append `models.json`:

1. `AGENT_WORKFLOW_CONFIG`, when set. This variable names a directory, not a file.
2. `$XDG_CONFIG_HOME/agent-workflow`, when `XDG_CONFIG_HOME` is set.
3. `~/.config/agent-workflow`.

This is location precedence, not a search through fallback files. Do not inspect
credential locations or dump the environment. If a user-specified file, or a
file selected through `AGENT_WORKFLOW_CONFIG`, is missing or unreadable, report
that problem instead of skipping to another location. Report any selected file
that exists but is unreadable, malformed JSON, invalid field shape, or invalid
referenced alias. If the ordinary XDG/default file is absent, treat routing
configuration as optional and continue with applicable instructions and host
defaults.

When a file is present, require a top-level object with nonempty `models` and
`roles` objects. Each model alias maps to an object containing nonempty string
`provider` and `model` fields and, when present, a nonempty string `effort`.
Require all seven roles below, with every role and optional route value naming an
alias in `models`. Optional route fields must be objects. Report validation
failures instead of partially applying the file.
Do not dispatch through a broken configuration or treat it as absent. Preserve
the assignment and request correction if it blocks the required route.

## Resolve a route

Classify bounded fact-finding as `lookup`, broader codebase investigation as
`explore`, routine changes as `implement`, design/planning as `plan`, diagnosis
as `debug`, difficult cross-cutting implementation as `complex`, and independent
assessment as `review`. For implementation routes, `specified` means settled
decisions with concrete acceptance checks, `local` means bounded implementation
judgment, and `architectural` means unresolved cross-cutting decisions.
For each assignment:

1. Classify the work into one role. Honor an explicit user choice of model,
   provider, integration, effort, or direct execution before configuration.
2. Unless an explicit model alias overrides routing, begin with `roles[role]`.
   For `implement`, replace it with the matching optional
   `implementation_routes` entry (`specified`, `local`, or `architectural`) when
   present. For `review`, if the prior worker's configured provider is known,
   replace it with the matching optional `review_routes[provider]` entry. After a
   failed attempt, and only within an authorized retry budget, replace the result
   with optional `escalation[role]`. Thus an explicit override wins over every
   route, and escalation wins over the other configured routes.
3. Resolve the selected alias in `models`. Every role and route must reference an
   existing alias. Read its `provider`, `model`, and optional `effort`.
4. Match that request to tools and controls actually exposed by the current host.
   Pass effort only when the selected tool supports it. If the provider, model,
   effort, or cross-provider integration is unavailable, report the unsupported
   request; do not silently substitute another selection and do not describe a
   worker invocation that did not happen.
5. Record the configured selection as requested. When the host reports the model
   actually used, inspect and report it separately as observed; otherwise label
   the observed model unknown. Host controls and organization policy can override
   a request.

`provider: "host"` means use the current host's native capability, and
`model: "inherit"` means retain the session or native worker's inherited model
default. Omit `effort` to retain inherited defaults. `host` and `inherit` are
portable skill-only sentinels; they are not valid values in `agent-run`
configuration.

The optional route maps need not be present. `implementation_routes` may contain
any of `specified`, `local`, and `architectural`; `review_routes` is keyed by a
known prior provider; and `escalation` is keyed by role. Configuration expresses
preferences but does not create tools, integrations, retries, or budgets.

## Host and runner compatibility

An existing runner `models.json` can provide the shared `models`, `roles`,
`implementation_routes`, `review_routes`, and `escalation` mappings to this
procedure. The runner remains responsible for its stricter provider and effort
validation and its own extra fields. Native hosts must not treat `binaries`,
`worker_packet_bytes`, `dispatch_limits`, or other process controls as controls
they implement. See the [optional agent-run reference](agent-run.md) when the
user has selected that runner.

For Claude Code, install or symlink the complete skill directory at
`~/.claude/skills/agent-workflow` and invoke `/agent-workflow`. Claude Code reads
the YAML-and-Markdown `SKILL.md` and its linked references; this JSON is read by
the skill instructions, not automatically loaded as Claude settings. Native
Claude workers can select supported Claude model aliases, full model IDs, or
inheritance, including a model selection per invocation when those controls are
exposed. Cross-provider routing requires an explicitly available, selected
external integration; it does not force `agent-run` or Yggdrasil. Subagent
definitions can request effort in frontmatter, but pass effort only when the
installed tool actually exposes that control.

Claude Code documents [skills, references, symlinks, and `/skill-name`
invocation](https://code.claude.com/docs/en/skills) and [subagent model and effort
controls](https://code.claude.com/docs/en/sub-agents). Keep routing
capability-based because exposed controls and organization policy can constrain
the requested selection.
