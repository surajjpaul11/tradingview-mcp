#!/usr/bin/env bash
# Forward to start.command
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/start.command" "$@"
