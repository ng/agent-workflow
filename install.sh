#!/usr/bin/env bash
set -eu

workflow_source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
workflow_bin_dir=${HOME:?HOME must be set}/.local/bin
workflow_skill_dirs=()
workflow_with_runner=false

usage() {
  printf '%s\n' \
    'Usage: install.sh [--skill-dir DIR]... [--with-runner [--bin-dir DIR]]' \
    '' \
    'Installs only the skill by default (~/.codex/skills).' \
    '--with-runner also installs the optional Python agent-run CLI.' \
    'Personal configuration and policy files are never created or changed.'
}

while (($#)); do
  case $1 in
    --with-runner)
      workflow_with_runner=true
      shift
      ;;
    --bin-dir)
      (($# >= 2)) || { printf '%s\n' 'install.sh: --bin-dir requires a value' >&2; exit 2; }
      workflow_bin_dir=$2
      shift 2
      ;;
    --skill-dir)
      (($# >= 2)) || { printf '%s\n' 'install.sh: --skill-dir requires a value' >&2; exit 2; }
      workflow_skill_dirs+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'install.sh: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

install_link() {
  local workflow_source=$1
  local workflow_destination=$2
  mkdir -p -- "$(dirname -- "$workflow_destination")"
  if [[ -e $workflow_destination && ! -L $workflow_destination ]]; then
    printf 'install.sh: refusing to overwrite existing file: %s\n' "$workflow_destination" >&2
    return 1
  fi
  ln -sfn -- "$workflow_source" "$workflow_destination"
}

if ((${#workflow_skill_dirs[@]} == 0)); then
  workflow_skill_dirs+=("${HOME:?HOME must be set}/.codex/skills")
fi
if [[ $workflow_with_runner == true ]]; then
  install_link "$workflow_source_dir/agent_run.py" "$workflow_bin_dir/agent-run"
fi
for workflow_skill_dir in "${workflow_skill_dirs[@]}"; do
  install_link "$workflow_source_dir/skills/agent-workflow" \
    "$workflow_skill_dir/agent-workflow"
done

printf 'Installed Agent Workflow skill from %s\n' "$workflow_source_dir"
if [[ $workflow_with_runner != true ]]; then
  exit 0
fi
workflow_config_dir=${AGENT_WORKFLOW_CONFIG:-${XDG_CONFIG_HOME:-${HOME:?HOME must be set}/.config}/agent-workflow}
printf 'Installed agent-run from %s\n' "$workflow_source_dir"
printf 'Configuration remains user-managed at %s\n' "$workflow_config_dir"
if [[ ! -f $workflow_config_dir/models.json ]]; then
  printf '%s\n' 'Setup required before execution: copy and customize examples/models.json.'
fi
