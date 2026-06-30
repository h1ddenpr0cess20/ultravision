#!/usr/bin/env sh
# `pipefail` is not POSIX and breaks under dash (the image's /bin/sh); there are
# no pipelines here anyway, so plain `-eu` is sufficient.
set -eu

if [ "$#" -gt 0 ] && [ "$1" = "web" ]; then
  shift
  exec ultravision-web "$@"
fi

exec ultravision "$@"
