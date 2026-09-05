#!/usr/bin/env bash
set -euo pipefail

RUNTIME_BASE="${RUNTIME_BASE:-/opt/hiddenoasis/staff-payroll}"
RELEASES_DIR="$RUNTIME_BASE/releases"
CURRENT_LINK="$RUNTIME_BASE/current"
KEEP_COUNT="${STAFF_PAYROLL_RELEASE_KEEP_COUNT:-3}"

fail() {
  echo "Fatal: $*" >&2
  exit 1
}

[[ "$(id -u)" == "0" ]] || fail "release pruning must run as root"
[[ "$KEEP_COUNT" =~ ^[0-9]+$ ]] || fail "STAFF_PAYROLL_RELEASE_KEEP_COUNT must be an integer"
(( KEEP_COUNT >= 2 )) || fail "release retention must keep at least 2 releases"
[[ -d "$RELEASES_DIR" ]] || fail "release directory missing: $RELEASES_DIR"

current_release="$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)"
[[ -n "$current_release" && -d "$current_release" ]] || fail "current release symlink is missing or invalid"
[[ "$current_release" == "$RELEASES_DIR"/* ]] || fail "current release is outside managed release directory"

mapfile -t releases < <(
  find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
    | sort -nr \
    | awk '{print $2}'
)

if (( ${#releases[@]} <= KEEP_COUNT )); then
  echo "Release retention: ${#releases[@]} release(s) present; nothing to prune."
  exit 0
fi

declare -A keep=()
keep["$current_release"]=1

kept=1
for release in "${releases[@]}"; do
  [[ "$release" == "$current_release" ]] && continue
  keep["$release"]=1
  kept=$((kept + 1))
  (( kept >= KEEP_COUNT )) && break
done

for release in "${releases[@]}"; do
  [[ -n "${keep[$release]:-}" ]] && {
    echo "KEEP   $(basename "$release")"
    continue
  }
  [[ "$release" == "$RELEASES_DIR"/* ]] || fail "refusing to delete path outside managed release directory: $release"
  echo "DELETE $(basename "$release")"
  rm -rf --one-file-system "$release"
done

echo "Release retention complete. Kept $KEEP_COUNT managed release(s), including current."
