#!/usr/bin/env bash
# Build dist/Toolbox_Theme_Manager.zip, a project export importable on any 8.3
# gateway through Config -> Projects -> Import.
#
#   ./tools/package.sh                 as the repo stands
#   ./tools/package.sh --release [VER] VER defaults to the tag HEAD is on and
#                                      must match VERSION, which the generator
#                                      has already put in the Title, the end of
#                                      the Description and the page header.
#
# The project IS this repo's root, so the build tooling beside it is excluded
# by name. Regenerate first: python3 tools/build_manager.py
set -euo pipefail
# Repo gate (REPO-STANDARD.md). Blocking; bypass deliberately with --skip-readme-check.
if [[ " $* " != *" --skip-readme-check "* ]]; then
    _repo=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
    _gate=""; _d="$_repo"
    while [ "$_d" != / ]; do
        [ -x "$_d/modules/readme-gate.sh" ] && { _gate="$_d/modules/readme-gate.sh"; break; }
        _d=$(dirname "$_d")
    done
    if [ -n "$_gate" ]; then
        "$_gate" "$_repo" || { echo "repo gate failed: fix the README/tree or pass --skip-readme-check" >&2; exit 1; }
    else
        echo "readme-gate.sh not found above $_repo; gate skipped" >&2
    fi
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
PROJECT="."
PROJJSON="project.json"

VERSION=""
if [[ "${1:-}" == "--release" ]]; then
	VERSION="${2:-}"
	if [[ -z "$VERSION" ]]; then
		VERSION="$(git describe --tags --exact-match 2>/dev/null || true)"
		[[ -n "$VERSION" ]] || {
			echo "package.sh --release: no version given and HEAD is not exactly on a tag" >&2
			exit 2; }
	fi
	VERSION="${VERSION#v}"
fi

# A release is built from committed source. Building from a reverted tree once
# shipped a release with none of its fixes.
if [[ -n "$VERSION" ]]; then
	if ! git diff --quiet HEAD; then
		echo "package.sh --release: uncommitted changes. Commit them first." >&2
		git status --short >&2
		exit 2
	fi
fi

# The generator stamps VERSION everywhere it shows; a release only checks it.
if [[ -n "$VERSION" ]]; then
	[[ "$(cat VERSION)" == "$VERSION" ]] || {
		echo "package.sh --release: VERSION says $(cat VERSION), release is $VERSION" >&2; exit 2; }
	python3 tools/test_import.py >/dev/null || { echo "package.sh: tools/test_import.py failed" >&2; exit 1; }
	# Every build restamps resource.json timestamps, so those are not compared,
	# and the committed copies go back before packaging.
	python3 tools/build_manager.py >/dev/null
	_stale=0; git diff --quiet HEAD -- . ':!*resource.json' || _stale=1
	git checkout -q -- .
	[[ $_stale -eq 0 ]] || { echo "package.sh --release: the generated project is out of date; regenerate and commit" >&2; exit 2; }
	grep -q "\"title\": \"Toolbox Theme Manager $VERSION\"" "$PROJJSON"
	grep -q "v$VERSION\"" "$PROJJSON"
fi

# Accessibility gate (a11y.json, REPO-STANDARD.md). Blocking; bypass deliberately
# with --skip-a11y-check. The gate checks what is DEPLOYED, so this pushes the
# current tree to module-testing (this host's local docker gateway named in
# a11y.json) and scans it first, same as any other file-based deploy there.
if [[ " $* " != *" --skip-a11y-check "* ]]; then
	_a11y_gate=""; _d="$HERE"
	while [ "$_d" != / ]; do
		[ -x "$_d/modules/a11y-gate.sh" ] && { _a11y_gate="$_d/modules/a11y-gate.sh"; break; }
		_d=$(dirname "$_d")
	done
	if [ -n "$_a11y_gate" ]; then
		CONTAINER="ignition-module-testing"
		REMOTE_DIR="/usr/local/bin/ignition/data/projects/Toolbox_Theme_Manager"
		docker exec "$CONTAINER" mkdir -p "$REMOTE_DIR"
		tar -cf - --exclude='.git' --exclude='.gitignore' --exclude='.gitmodules' \
		    --exclude='README.md' --exclude='VERSION' --exclude='tools' \
		    --exclude='docs' --exclude='a11y.json' --exclude='.github' --exclude='dist' --exclude='__pycache__' . \
			| docker exec -i "$CONTAINER" tar -xf - -C "$REMOTE_DIR"
		node "${IGNITION_TOOLKIT:?set IGNITION_TOOLKIT to the ignition-claude-toolkit checkout}"/plugins/ignition/skills/scan/tool/scan.js --gateway module-testing >/dev/null
		sleep 3
		"$_a11y_gate" "$HERE" || { echo "a11y gate failed: fix the findings, or record a reasoned exception in a11y.json (--skip-a11y-check to bypass)" >&2; exit 1; }
	else
		echo "a11y-gate.sh not found above $HERE; gate skipped" >&2
	fi
fi

# Lint gate (REPO-STANDARD.md). Blocking; bypass deliberately with --skip-lint-check.
if [[ " $* " != *" --skip-lint-check "* ]]; then
	_lint_gate=""; _d="$HERE"
	while [ "$_d" != / ]; do
		[ -x "$_d/modules/lint-gate.sh" ] && { _lint_gate="$_d/modules/lint-gate.sh"; break; }
		_d=$(dirname "$_d")
	done
	if [ -n "$_lint_gate" ]; then
		"$_lint_gate" "$HERE" || { echo "lint gate failed: fix the errors, or record a reasoned exception in lint.json (--skip-lint-check to bypass)" >&2; exit 1; }
	else
		echo "lint-gate.sh not found above $HERE; gate skipped" >&2
	fi
fi

mkdir -p dist
ZIPNAME="Toolbox_Theme_Manager${VERSION:+-$VERSION}.zip"
rm -f "dist/$ZIPNAME"

# No global-props resource is carried, so the importing gateway keeps its own
# settings.
EXCLUDE=( -x '.git/*' '.gitignore' '.gitmodules' 'README.md' 'a11y.json' 'VERSION'
          'tools/*' 'docs/*' 'dist/*' '.github/*' '*__pycache__*' )
( cd "$HERE" && zip -qr "$HERE/dist/$ZIPNAME" . "${EXCLUDE[@]}" )

echo "dist/$ZIPNAME ($(du -h "dist/$ZIPNAME" | cut -f1), $(unzip -l "dist/$ZIPNAME" | tail -1 | awk '{print $2}') files)"
