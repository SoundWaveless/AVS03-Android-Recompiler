#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec python3 avs03_wrapper_builder.py
