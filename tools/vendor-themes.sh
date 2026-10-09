#!/bin/sh
# Copy the ten built themes and the two copy-me switcher views from a sibling
# ignition-themes checkout into tools/themes/. That repo is where the themes
# are made; this one only carries them.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
src=${1:-$here/../../../ignition-themes}
[ -f "$src/out/themes.json" ] || { echo "no $src/out/themes.json -- pass the ignition-themes path" >&2; exit 1; }
rm -rf "$here/themes"
mkdir -p "$here/themes"
cp -r "$src/out/." "$here/themes/"
cp "$src/selector-popup/SelectorPopup.view.json" "$src/selector-popup/ThemeDropdown.view.json" "$here/themes/"
echo "vendored $(ls -d "$here"/themes/*/ | wc -l) themes from $src"
