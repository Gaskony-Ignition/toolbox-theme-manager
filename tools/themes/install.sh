#!/bin/sh
# install.sh -- deploy the Ignition Themes pack onto an Ignition 8.3 gateway's
# config resources.
#
# POSIX sh (no bashisms) so it runs the same from a plain shell, inside an
# Ignition docker image's minimal userland, or piped over ssh.
#
# WHAT THIS DOES
#   Copies each theme directory sitting next to this script into:
#     <data-dir>/config/resources/core/com.inductiveautomation.perspective/themes/<id>/
#   replacing any existing directory of the same name (idempotent -- safe to
#   re-run). It tries to match ownership to the gateway's own shipped variant
#   theme directories (uid:gid of "light-cool"); if it can't determine that,
#   it leaves ownership alone rather than guess.
#
#   It does NOT touch light/dark or the four shipped variants
#   (light-cool/light-warm/dark-cool/dark-warm) -- ever, even if one somehow
#   ended up sitting next to this script.
#
#   It does NOT run a gateway config scan for you -- see the final message
#   this script prints. That step is documented in RELEASE-README.md's
#   "Installing on a gateway" section AND in the parent repo's own
#   README.md (the same section, kept in both places
#   deliberately -- see package.sh's header comment for why, and touch both
#   if this changes).
#
# USAGE
#   ./install.sh --data-dir /path/to/ignition/data
#       Local filesystem -- e.g. a mounted docker volume, or a data
#       directory on the machine this script runs on directly.
#
#   ./install.sh --docker <container-name>
#       Copies via `docker exec`/`docker cp` into a running Ignition
#       container. Assumes the standard image layout,
#       /usr/local/bin/ignition/data -- override with
#       IGNITION_DATA_DIR=/other/path ./install.sh --docker <container>
#       if your image differs.
#
#   ./install.sh --ssh <host> --data-dir /path/to/ignition/data
#       Remote gateway over ssh (key-based auth assumed -- this script never
#       prompts for or accepts a password). <path> is the data directory ON
#       THE REMOTE HOST.
#
# Exits non-zero on any usage error or copy failure. Never touches a
# gateway's Projects -- config resources only.

set -eu

THEMES_SUBPATH="config/resources/core/com.inductiveautomation.perspective/themes"
FORBIDDEN="light dark light-cool light-warm dark-cool dark-warm"

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

MODE=""
DATA_DIR=""
CONTAINER=""
SSH_HOST=""

usage() {
    echo "Usage:" >&2
    echo "  $0 --data-dir <path>              (local filesystem)" >&2
    echo "  $0 --docker <container>           (docker exec/cp)" >&2
    echo "  $0 --ssh <host> --data-dir <path> (remote via ssh)" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --data-dir)
            [ $# -ge 2 ] || usage
            DATA_DIR="$2"
            shift 2
            ;;
        --docker)
            [ $# -ge 2 ] || usage
            MODE="docker"
            CONTAINER="$2"
            shift 2
            ;;
        --ssh)
            [ $# -ge 2 ] || usage
            MODE="ssh"
            SSH_HOST="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "install.sh: unrecognised argument: $1" >&2
            usage
            ;;
    esac
done

if [ "$MODE" = "docker" ]; then
    [ -n "$CONTAINER" ] || usage
    IGNITION_DATA_DIR="${IGNITION_DATA_DIR:-/usr/local/bin/ignition/data}"
elif [ "$MODE" = "ssh" ]; then
    [ -n "$SSH_HOST" ] || usage
    [ -n "$DATA_DIR" ] || { echo "install.sh: --ssh requires --data-dir too" >&2; usage; }
elif [ -n "$DATA_DIR" ]; then
    MODE="local"
else
    usage
fi

# ---------------------------------------------------------------------------
# Discover the theme directories sitting next to this script: any
# subdirectory that carries a config.json and is NOT one of the forbidden
# built-in names. themes.json and RELEASE-README.md are not directories, so
# they're naturally excluded.
# ---------------------------------------------------------------------------

THEME_NAMES=""
for d in "$SCRIPT_DIR"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    is_forbidden=0
    for f in $FORBIDDEN; do
        [ "$name" = "$f" ] && is_forbidden=1
    done
    if [ "$is_forbidden" = "1" ]; then
        echo "install.sh: REFUSING to touch reserved/built-in theme name '$name' -- skipped" >&2
        continue
    fi
    [ -f "$d/config.json" ] || continue
    THEME_NAMES="$THEME_NAMES $name"
done

if [ -z "$THEME_NAMES" ]; then
    echo "install.sh: no theme directories found next to this script (looked in $SCRIPT_DIR)" >&2
    exit 1
fi

echo "install.sh: found theme(s):$THEME_NAMES"

# ---------------------------------------------------------------------------
# Local filesystem mode
# ---------------------------------------------------------------------------

install_local() {
    target_root="$DATA_DIR/$THEMES_SUBPATH"
    [ -d "$target_root" ] || { echo "install.sh: not found: $target_root (wrong --data-dir?)" >&2; exit 1; }

    owner=""
    if [ -d "$target_root/light-cool" ]; then
        if command -v stat >/dev/null 2>&1; then
            owner=$(stat -c '%u:%g' "$target_root/light-cool" 2>/dev/null) || \
            owner=$(stat -f '%u:%g' "$target_root/light-cool" 2>/dev/null) || owner=""
        fi
    fi
    if [ -n "$owner" ]; then
        echo "install.sh: matching ownership to light-cool ($owner)"
    else
        echo "install.sh: could not detect light-cool's ownership -- leaving ownership alone"
    fi

    for name in $THEME_NAMES; do
        dest="$target_root/$name"
        [ -d "$dest" ] && { echo "install.sh: replacing existing $dest"; rm -rf "$dest"; }
        cp -R "$SCRIPT_DIR/$name" "$dest"
        if [ -n "$owner" ]; then
            chown -R "$owner" "$dest" 2>/dev/null || \
                echo "install.sh: WARNING: chown $owner $dest failed (needs root?) -- ownership left as copied" >&2
        fi
        echo "install.sh: installed $name -> $dest"
    done
}

# ---------------------------------------------------------------------------
# Docker mode
# ---------------------------------------------------------------------------

install_docker() {
    target_root="$IGNITION_DATA_DIR/$THEMES_SUBPATH"
    docker exec "$CONTAINER" test -d "$target_root" || \
        { echo "install.sh: not found in container: $target_root (wrong IGNITION_DATA_DIR?)" >&2; exit 1; }

    owner=$(docker exec "$CONTAINER" sh -c "stat -c '%u:%g' '$target_root/light-cool' 2>/dev/null" 2>/dev/null) || owner=""
    if [ -n "$owner" ]; then
        echo "install.sh: matching ownership to light-cool ($owner)"
    else
        echo "install.sh: could not detect light-cool's ownership in the container -- leaving ownership alone"
    fi

    for name in $THEME_NAMES; do
        dest="$target_root/$name"
        docker exec "$CONTAINER" sh -c "[ -d '$dest' ] && rm -rf '$dest'; mkdir -p '$dest'"
        # docker cp copies the SOURCE DIR itself; drop it straight into the
        # parent so the result is target_root/<name>/... not target_root/<name>/<name>/...
        docker cp "$SCRIPT_DIR/$name/." "$CONTAINER:$dest"
        if [ -n "$owner" ]; then
            # -u 0 first, and it is not belt-and-braces. `docker exec` without it
            # runs as the image's default user (ignition), which cannot chown
            # files docker cp has just written as root/uid-1000 -- it fails with
            # "Operation not permitted". The plain form is kept as a fallback for
            # a container that is already running as root.
            docker exec -u 0 "$CONTAINER" chown -R "$owner" "$dest" 2>/dev/null || \
            docker exec "$CONTAINER" chown -R "$owner" "$dest" 2>/dev/null || true
        fi
        echo "install.sh: installed $name -> $CONTAINER:$dest"
    done

    verify_ownership_docker "$target_root" "$owner"
}

# Wrong ownership is not a cosmetic problem here and it does not announce itself.
# A theme directory the gateway cannot read as its own is not skipped and does not
# error: the next config scan RENAMES it to <theme-id>.deleted-<n> and drops the
# resource, so the scan reports success and the themes 404 afterwards. Two separate
# sessions lost theme resources to this before it was understood, so the install
# refuses to report success it cannot stand behind.
verify_ownership_docker() {
    _root="$1"; _want="$2"
    [ -n "$_want" ] || return 0
    _bad=$(docker exec "$CONTAINER" sh -c \
        "find '$_root' -mindepth 1 -maxdepth 1 -type d ! -name '*.deleted-*' \
         -exec stat -c '%u:%g %n' {} \; 2>/dev/null | grep -v '^$_want ' | head -5")
    if [ -n "$_bad" ]; then
        echo "" >&2
        echo "install.sh: FAILED -- these are not owned by $_want:" >&2
        echo "$_bad" | sed 's/^/  /' >&2
        echo "" >&2
        echo "  A gateway config scan will RENAME each of these to <id>.deleted-<n>" >&2
        echo "  and drop the resource, reporting success as it does so. Fix the" >&2
        echo "  ownership before scanning:" >&2
        echo "" >&2
        echo "    docker exec -u 0 $CONTAINER chown -R $_want $_root" >&2
        echo "" >&2
        return 1
    fi
    _dropped=$(docker exec "$CONTAINER" sh -c "ls '$_root' 2>/dev/null | grep '\.deleted-' | head -5")
    if [ -n "$_dropped" ]; then
        echo "install.sh: NOTE: a previous scan already dropped these; they are dead" >&2
        echo "$_dropped" | sed 's/^/  /' >&2
        echo "  Remove them, re-run this installer, then scan." >&2
    fi
    echo "install.sh: ownership verified ($_want) -- safe to run a config scan"
}

# ---------------------------------------------------------------------------
# SSH mode -- tar over ssh, no scp dependency, one round trip per theme.
# ---------------------------------------------------------------------------

install_ssh() {
    target_root="$DATA_DIR/$THEMES_SUBPATH"
    ssh "$SSH_HOST" "test -d '$target_root'" || \
        { echo "install.sh: not found on $SSH_HOST: $target_root (wrong --data-dir?)" >&2; exit 1; }

    owner=$(ssh "$SSH_HOST" "stat -c '%u:%g' '$target_root/light-cool' 2>/dev/null || stat -f '%u:%g' '$target_root/light-cool' 2>/dev/null") || owner=""
    if [ -n "$owner" ]; then
        echo "install.sh: matching ownership to light-cool ($owner)"
    else
        echo "install.sh: could not detect light-cool's ownership on $SSH_HOST -- leaving ownership alone"
    fi

    for name in $THEME_NAMES; do
        dest="$target_root/$name"
        ssh "$SSH_HOST" "[ -d '$dest' ] && rm -rf '$dest'; mkdir -p '$dest'"
        (cd "$SCRIPT_DIR/$name" && tar -cf - .) | ssh "$SSH_HOST" "tar -xf - -C '$dest'"
        if [ -n "$owner" ]; then
            ssh "$SSH_HOST" "chown -R '$owner' '$dest'" 2>/dev/null || \
                echo "install.sh: WARNING: chown $owner $dest failed on $SSH_HOST -- ownership left as copied" >&2
        fi
        echo "install.sh: installed $name -> $SSH_HOST:$dest"
    done
}

case "$MODE" in
    local) install_local ;;
    docker) install_docker ;;
    ssh) install_ssh ;;
esac

echo ""
echo "============================================================"
echo " Files are copied. ONE step remains and this script cannot"
echo " do it for you:"
echo ""
echo "   Gateway web UI -> Config -> Platform -> Overview ->"
echo "   \"Scan File System\" (the CONFIG scan -- NOT the Projects"
echo "   one; themes are gateway config, not project resources)."
echo ""
echo " No gateway restart is required -- confirmed on Ignition"
echo " 8.3.8: a brand-new theme becomes selectable immediately"
echo " after that scan. See docs/THEMES-EVALUATION.md for how"
echo " this was verified."
echo "============================================================"
