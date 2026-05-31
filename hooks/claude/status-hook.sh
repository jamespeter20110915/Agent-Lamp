#!/usr/bin/env sh
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export AGENT_LAMP_QUEUE="${AGENT_LAMP_QUEUE:-/private/tmp/agent-lamp-queue.tsv}"
exec python3 "$ROOT/host/hook_status.py" --agent claude
