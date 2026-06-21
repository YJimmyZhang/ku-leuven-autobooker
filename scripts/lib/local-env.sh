# Source from other scripts: load config/local.env if present.
load_local_env() {
  local script_dir root
  script_dir="$(cd "$(dirname "${BASH_SOURCE[1]:-$0}")" && pwd)"
  root="$(cd "$script_dir/.." && pwd)"
  if [[ -f "$root/config/local.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$root/config/local.env"
    set +a
  fi
}
