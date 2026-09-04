#!/bin/zsh
set -eu

script_dir=${0:A:h}
repo_root=${script_dir:h}
kicad_python=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9

if [[ ! -x "$kicad_python" ]]; then
  print -u2 "KiCad Python wurde nicht gefunden: $kicad_python"
  exit 1
fi

export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"
exec "$kicad_python" -m partharbor.gui
