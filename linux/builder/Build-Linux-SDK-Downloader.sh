#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
CONFIG_FILE="edition_config.py"
BACKUP_FILE="$(mktemp)"
cp "$CONFIG_FILE" "$BACKUP_FILE"
restore_config() {
  cp "$BACKUP_FILE" "$CONFIG_FILE"
  rm -f "$BACKUP_FILE"
}
trap restore_config EXIT
DOCS_DIR="../../docs"
LICENSE_FILE="../../LICENSE"
if [ ! -f "$DOCS_DIR/README.md" ]; then DOCS_DIR="docs"; fi
if [ ! -f "$LICENSE_FILE" ]; then LICENSE_FILE="LICENSE"; fi
python3 - <<'PY'
from pathlib import Path
p=Path('edition_config.py')
s=p.read_text(encoding='utf-8').replace('SDK_DOWNLOADER_EDITION = False','SDK_DOWNLOADER_EDITION = True')
p.write_text(s,encoding='utf-8')
PY
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install --upgrade pip pyinstaller
.venv/bin/python -m PyInstaller --noconfirm --clean --onefile --windowed \
  --add-data "android_patch:android_patch" \
  --add-data "$DOCS_DIR:docs" \
  --add-data "$LICENSE_FILE:docs" \
  --name AVS03-Android-Builder-SDK-Downloader avs03_wrapper_builder.py
printf '\nBuilt dist/AVS03-Android-Builder-SDK-Downloader\n'
