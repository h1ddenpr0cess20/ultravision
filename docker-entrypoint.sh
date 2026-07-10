#!/usr/bin/env sh
set -eu

if [ "$#" -gt 0 ] && [ "$1" = "web" ]; then
  shift
  exec ultravision-web "$@"
fi

exec ultravision "$@"
