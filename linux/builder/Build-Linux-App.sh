#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
DOCS_DIR="../../docs"
LICENSE_FILE="../../LICENSE"
if [ ! -f "$DOCS_DIR/README.md" ]; then DOCS_DIR="docs"; fi
if [ ! -f "$LICENSE_FILE" ]; then LICENSE_FILE="LICENSE"; fi
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip pyinstaller
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile --windowed \
  --add-data "android_patch:android_patch" \
  --add-data "$DOCS_DIR:docs" \
  --add-data "$LICENSE_FILE:docs" \
  --name AVS03-Android-Builder avs03_wrapper_builder.py
printf '\nBuilt dist/AVS03-Android-Builder\n'
