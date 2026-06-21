# Source from other scripts: load local.env from agent dir (LaunchAgent) or repo config/.
load_local_env() {
  local env_file=""
  if [[ -n "${AUTBOOKER_AGENT_DIR:-}" && -f "${AUTBOOKER_AGENT_DIR}/local.env" ]]; then
    env_file="${AUTBOOKER_AGENT_DIR}/local.env"
  else
    local script_dir root
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]:-$0}")" && pwd)"
    root="$(cd "$script_dir/.." && pwd)"
    if [[ -f "$root/config/local.env" ]]; then
      env_file="$root/config/local.env"
    fi
  fi
  if [[ -n "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$env_file"
    set +a
  fi
}
