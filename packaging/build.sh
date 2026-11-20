#!/usr/bin/env bash
# 打包成 Linux 独立目录（onedir）
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONUTF8=1
PYTHON="${PYTHON:-.venv/bin/python}"
OUTPUT="${OUTPUT:-dist}"

"$PYTHON" -m nuitka --version >/dev/null || {
  echo "先安装 Nuitka: uv pip install nuitka" >&2
  exit 1
}

"$PYTHON" -m nuitka \
  --standalone \
  --assume-yes-for-downloads \
  --output-dir="$OUTPUT" \
  --output-filename=hoshi \
  --include-package=hoshi \
  --nofollow-import-to=pytest,tests \
  packaging/entry.py

echo "产物: $OUTPUT/entry.dist/hoshi"
