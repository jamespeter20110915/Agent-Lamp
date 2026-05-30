#!/usr/bin/env sh
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
exec python3 "$ROOT/host/hook_status.py" --agent claude
