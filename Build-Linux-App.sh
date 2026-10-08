#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip pyinstaller
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile --windowed \
  --add-data "android_patch:android_patch" \
  --add-data "DISCLAIMER-ACKNOWLEDGMENT.md:." \
  --add-data "README.md:." \
  --add-data "LICENSE:." \
  --name AVS03-Android-Builder avs03_wrapper_builder.py
printf '\nBuilt dist/AVS03-Android-Builder\n'
