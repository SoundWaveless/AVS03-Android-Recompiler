#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ -x AVS03-Compiler-Updater ]; then
  exec ./AVS03-Compiler-Updater
fi
if [ -f avs03_compiler_updater.py ]; then
  exec python3 avs03_compiler_updater.py
fi
exec python3 avs03_wrapper_builder.py
