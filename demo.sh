#!/usr/bin/env sh
set -eu

action="${1:-up}"
compose_files="-f compose.yaml -f compose.runtime.yaml -f compose.demo.yaml"

if ! docker info >/dev/null 2>&1; then
  printf 'Docker is installed, but its daemon is not running. Start Docker and retry.\n' >&2
  exit 1
fi

case "$action" in
  up)
    docker compose $compose_files up --detach --build
    printf '\nIncident Investigator is starting.\n'
    printf '1. Open http://127.0.0.1:8501\n'
    printf '2. Wait for the runtime-demo incident to appear.\n'
    printf "3. Review the evidence and click 'Allow action'.\n"
    printf '4. Watch the agent verify service recovery automatically.\n'
    ;;
  down)
    docker compose $compose_files down
    ;;
  status)
    docker compose $compose_files ps
    ;;
  *)
    printf 'Usage: ./demo.sh [up|down|status]\n' >&2
    exit 2
    ;;
esac
