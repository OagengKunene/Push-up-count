#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec python3 setup_and_run.py "$@"
