#!/usr/bin/env python3
"""Generate the Toolbox Theme Manager project at the repo root.

Reads tools/themes/out/ (the ten themes, built by tools/themes/build_theme.py),
the two copy-me switcher views in tools/themes/selector-popup/, the
hand-authored tools/*_code.py appended to the themepack script, and VERSION.
Rewrites project.json, com.inductiveautomation.perspective/ and ignition/ at
the repo root -- the git module makes the repo root the project folder.

Usage:
    python3 tools/build_manager.py
"""

import datetime
import re
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
THEMES_DIR = os.path.join(HERE, "themes")
OUT_DIR = os.path.join(THEMES_DIR, "out")
VERSION_FILE = os.path.join(REPO, "VERSION")
PROJECT_DIR = REPO
# Only these are generated; everything else at the root is the repo's own.
GENERATED = ["project.json", "com.inductiveautomation.perspective", "ignition"]
TITLE = "Toolbox Theme Manager"

# The copy-me switcher views -- hand-adapted, NOT generated; copied verbatim.
# The two are independent on purpose: a project takes whichever it wants.
SELECTOR_POPUP_SRC = os.path.join(THEMES_DIR, "selector-popup", "SelectorPopup.view.json")
THEME_DROPDOWN_SRC = os.path.join(THEMES_DIR, "selector-popup", "ThemeDropdown.view.json")

# Hand-authored gateway functions appended to themepack's generated code.py.
INSIGHT_SRC = os.path.join(HERE, "insight_code.py")
EDITOR_SRC = os.path.join(HERE, "editor_code.py")
IMPORT_SRC = os.path.join(HERE, "import_code.py")

THEME_FILES = ["config.json", "index.css", "variables.css", "globals.css", "resource.json"]

NOW = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_version():
    if not os.path.isfile(VERSION_FILE):
        print("build_manager.py: VERSION file not found: %s" % VERSION_FILE)
        sys.exit(1)
    with open(VERSION_FILE) as fh:
        version = fh.read().strip()
    if not version:
        print("build_manager.py: VERSION file is empty")
        sys.exit(1)
    return version


def read_themes():
    themes_json = os.path.join(OUT_DIR, "themes.json")
    if not os.path.isdir(OUT_DIR) or not os.path.isfile(themes_json):
        print("build_manager.py: tools/themes/out/themes.json not found -- run "
              "tools/themes/build_theme.py first")
        sys.exit(1)
    with open(themes_json) as fh:
        meta = json.load(fh)

    themes = []
    for entry in meta:
        theme_id = entry["id"]
        theme_dir = os.path.join(OUT_DIR, theme_id)
        files = {}
        for name in THEME_FILES:
            path = os.path.join(theme_dir, name)
            if not os.path.isfile(path):
                print("build_manager.py: missing tools/themes/out/%s/%s" % (theme_id, name))
                sys.exit(1)
            with open(path) as fh:
                files[name] = fh.read()
        themes.append({
            "id": theme_id,
            "label": entry["label"],
            "dark": bool(entry["dark"]),
            "source_pack": entry["source_pack"],
            "files": files,
        })
    return themes


def write_json(path, data):
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def write_text(path, text):
    with open(path, "w") as fh:
        fh.write(text)


def resource_json(files, description=None):
    """A project-resource resource.json.

    `lastModification` goes INSIDE `attributes`, which is where Ignition
    reads it from -- checked against a resource the gateway wrote itself.
    At the top level it parses as an unknown key and is silently dropped,
    so the imported project shows a blank Author and Last Modified in the
    Projects grid and the Designer. It looks like nothing is wrong until
    someone compares the row with another project's.

    Still deliberately NO lastModificationSignature: a hand-written
    signature that doesn't match the content makes the scan silently skip
    the resource. The gateway stamps it on first scan.
    """
    doc = {
        "scope": "G",
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": files,
        "attributes": {
            "lastModification": {
                "actor": "external",
                "timestamp": NOW,
            },
        },
    }
    if description:
        doc["description"] = description
    return doc


def build_project_json(version, themes):
    # Workspace rule: released projects carry their version in the Title AND
    # at the end of the Description (the Projects grid shows only the
    # Description; the Title shows in the Edit drawer and on launch surfaces).
    # The theme list is derived, never hand-listed -- a hardcoded list went
    # stale once already (said 9, omitted newsprint-dark).
    ids = ", ".join(t["id"] for t in themes)
    return {
        "title": "%s %s" % (TITLE, version),
        "description": (
            "Install, remove, customise and import Perspective gateway "
            "themes. Carries %d (%s); installs all or any of them, and "
            "imports a theme zip from someone else after checking it. "
            "Writes gateway config resources under "
            "com.inductiveautomation.perspective/themes/ and runs a config "
            "scan, no restart. · v%s" % (len(themes), ids, version)
        ),
        "enabled": True,
        "inheritable": False,
        "parent": "",
    }


def additions_css(dark):
    """The optional stock-theme additions: ONLY what every stock theme lacks
    (a color-scheme declaration and themed scrollbars), never a colour or
    layout change -- an updated stock theme must look identical. Matches the
    scrollbar block the custom themes carry in their globals.css, except the
    thumb reads the theme's own var(--border) so one file fits any variant."""
    scheme = "dark" if dark else "light"
    return (
        "/* theme-additions.css -- written by the Theme Installer\n"
        " * (ignition-themes). ADDITIONS ONLY, the stock look is untouched:\n"
        " *   - color-scheme declaration (without it Chrome's auto dark mode\n"
        " *     repaints SVG fills client-side)\n"
        " *   - scrollbars follow the theme (stock themes leave them at the\n"
        " *     browser default)\n"
        " * Restore = delete this file and the import line at the end of\n"
        " * index.css -- the Restore button does exactly that. */\n"
        ":root { color-scheme: %s; }\n"
        "* {\n"
        "  scrollbar-color: var(--border) transparent;\n"
        "  scrollbar-width: thin;\n"
        "}\n"
        "::-webkit-scrollbar { width: 10px; height: 10px; }\n"
        "::-webkit-scrollbar-track, ::-webkit-scrollbar-corner { background: transparent; }\n"
        "::-webkit-scrollbar-thumb {\n"
        "  background: var(--border);\n"
        "  border-radius: 6px;\n"
        "  border: 2px solid transparent;\n"
        "  background-clip: content-box;\n"
        "}\n" % scheme
    )


def build_themepack_code(themes, version):
    """ignition/script-python/themepack/code.py -- gateway-scope module
    embedding every theme's file contents plus install/uninstall/status.

    Jython 2.7 (workspace rule): `except (Exception, Throwable) as e:` syntax,
    catching java.lang.Throwable because Ignition system calls raise Java
    Throwables that a plain `except Exception` does not see.
    """
    lines = []
    lines.append('"""themepack -- embeds %d curated Perspective' % len(themes))
    lines.append('gateway themes as data and installs/uninstalls them as')
    lines.append('gateway config resources.')
    lines.append('')
    lines.append('GENERATED by tools/build_manager.py from tools/themes/out/')
    lines.append('-- DO NOT EDIT BY HAND. Regenerate with:')
    lines.append('    python3 tools/build_manager.py')
    lines.append('')
    lines.append('Version %s. Gateway scope only -- install()/install_all() write' % version)
    lines.append('files under <dataDir>/config/resources/core/')
    lines.append('com.inductiveautomation.perspective/themes/<id>/ and request a')
    lines.append('config scan; uninstall()/uninstall_all() go through')
    lines.append('system.config.delete() instead, which removes the resource AND')
    lines.append('its files in one call (no scan needed for a delete). Every write')
    lines.append('path is a WHITELIST: custom installs against THEMES below (which can')
    lines.append('never name a stock theme), the OPTIONAL stock update against')
    lines.append('STOCK_UPDATABLE -- and that path only ever adds/removes the one')
    lines.append('additions file and its @import line (stock_update_all() /')
    lines.append('stock_restore_all()); it cannot replace stock content, and light/dark')
    lines.append('have no on-disk files at all. No code path touches any name this')
    lines.append('module was not built to know about.')
    lines.append('"""')
    lines.append('')
    lines.append('import json')
    lines.append('import os')
    lines.append('import re')
    lines.append('')
    lines.append('from java.lang import Throwable')
    lines.append('from com.inductiveautomation.ignition.gateway import IgnitionGateway')
    lines.append('')
    lines.append('')
    lines.append('# id -> {label, dark, source_pack, files: {filename: content}}')
    lines.append('# Content is plain ASCII text (verified at generation time), so a')
    lines.append('# straight repr() round-trips exactly -- no escaping surprises.')
    lines.append('THEMES = {')
    for theme in themes:
        lines.append('    %s: {' % py_repr(theme["id"]))
        lines.append('        "label": %s,' % py_repr(theme["label"]))
        lines.append('        "dark": %s,' % ("True" if theme["dark"] else "False"))
        lines.append('        "source_pack": %s,' % py_repr(theme["source_pack"]))
        lines.append('        "files": {')
        for name in THEME_FILES:
            lines.append('            %s: %s,' % (py_repr(name), py_repr(theme["files"][name])))
        lines.append('        },')
        lines.append('    },')
    lines.append('}')
    lines.append('')
    lines.append('# Display order -- matches out/themes.json / the table on the Installer')
    lines.append('# view. THEMES itself is keyed for O(1) lookup and whitelisting; this is')
    lines.append('# the order things get installed/listed in.')
    lines.append('THEME_ORDER = [')
    for theme in themes:
        lines.append('    %s,' % py_repr(theme["id"]))
    lines.append(']')
    lines.append('')
    lines.append('')
    lines.append('def _data_dir():')
    lines.append('    # Resolved dynamically -- verified live on 8.3.8. Never hardcode an')
    lines.append('    # install path; different gateways mount data/ in different places.')
    lines.append('    return str(IgnitionGateway.get().getSystemManager().getDataDir())')
    lines.append('')
    lines.append('')
    lines.append('def _themes_root():')
    lines.append('    return os.path.join(')
    lines.append('        _data_dir(), "config", "resources", "core",')
    lines.append('        "com.inductiveautomation.perspective", "themes")')
    lines.append('')
    lines.append('')
    lines.append('def _rescan():')
    lines.append('    # Config scan -- picks up newly written theme directories. Themes are')
    lines.append('    # gateway CONFIG resources, not project resources: this is the same')
    lines.append('    # scan as Config -> Platform -> Overview -> "Scan File System", not the')
    lines.append('    # Projects page one.')
    lines.append('    # requestScan() is async (returns a CompletableFuture); BLOCK on it so the')
    lines.append('    # status read that follows a click sees the registered themes, not a stale')
    lines.append('    # in-flight state. 30s cap; a timeout just means status lags a moment.')
    lines.append('    from_future = IgnitionGateway.get().getConfigurationManager().requestScan()')
    lines.append('    try:')
    lines.append('        from java.util.concurrent import TimeUnit')
    lines.append('        from_future.get(30, TimeUnit.SECONDS)')
    lines.append('    except (Exception, Throwable):')
    lines.append('        pass  # scan still runs; only the wait failed')
    lines.append('')
    lines.append('')
    lines.append('def _write_theme_files(name):')
    lines.append('    theme = THEMES[name]')
    lines.append('    theme_dir = os.path.join(_themes_root(), name)')
    lines.append('    if not os.path.isdir(theme_dir):')
    lines.append('        os.makedirs(theme_dir)')
    lines.append('    for filename, content in theme["files"].items():')
    lines.append('        path = os.path.join(theme_dir, filename)')
    lines.append('        handle = open(path, "wb")')
    lines.append('        try:')
    lines.append('            handle.write(content.encode("utf-8"))')
    lines.append('        finally:')
    lines.append('            handle.close()')
    lines.append('')
    lines.append('')
    lines.append('def install(name):')
    lines.append('    """Write one theme\'s files and request a scan. Refuses any name not')
    lines.append('    in the embedded THEMES set -- never touches an IA built-in theme."""')
    lines.append('    if name not in THEMES:')
    lines.append('        raise ValueError("Unknown theme id \'%s\' -- refusing to write" % name)')
    lines.append('    _write_theme_files(name)')
    lines.append('    _rescan()')
    lines.append('    return True')
    lines.append('')
    lines.append('')
    lines.append('def install_all():')
    lines.append('    """Write every embedded theme\'s files, then ONE scan at the end (not')
    lines.append('    one per theme -- a scan is not free and 9 of them in a row is no more')
    lines.append('    correct than 1)."""')
    lines.append('    for name in THEME_ORDER:')
    lines.append('        _write_theme_files(name)')
    lines.append('    _rescan()')
    lines.append('    return list(THEME_ORDER)')
    lines.append('')
    lines.append('')
    lines.append('def uninstall(name):')
    lines.append('    """Delete one theme\'s config resource (and its files) via')
    lines.append('    system.config.delete(). Returns False if it was not installed rather')
    lines.append('    than raising -- getResource() raises on missing, which is exactly how')
    lines.append('    "not installed" is detected."""')
    lines.append('    if name not in THEMES:')
    lines.append('        raise ValueError("Unknown theme id \'%s\' -- refusing to touch" % name)')
    lines.append('    try:')
    lines.append('        res = system.config.getResource(')
    lines.append('            moduleId="com.inductiveautomation.perspective",')
    lines.append('            typeId="themes", name=name)')
    lines.append('    except (Exception, Throwable):')
    lines.append('        return False')
    lines.append('    system.config.delete(')
    lines.append('        moduleId="com.inductiveautomation.perspective",')
    lines.append('        typeId="themes", name=name,')
    lines.append('        signature=res.getSignature(), actor="theme-manager")')
    lines.append('    return True')
    lines.append('')
    lines.append('')
    lines.append('def uninstall_all():')
    lines.append('    """Delete every embedded theme\'s config resource that is currently')
    lines.append('    installed. Returns the list of ids actually removed."""')
    lines.append('    removed = []')
    lines.append('    for name in THEME_ORDER:')
    lines.append('        if uninstall(name):')
    lines.append('            removed.append(name)')
    lines.append('    return removed')
    lines.append('')
    lines.append('')
    lines.append('def install_some(names):')
    lines.append('    """Install the named themes with one scan. Names outside THEMES are')
    lines.append('    skipped, not raised: the selection can hold stock or user rows."""')
    lines.append('    done = [n for n in THEME_ORDER if n in (names or [])]')
    lines.append('    for name in done:')
    lines.append('        _write_theme_files(name)')
    lines.append('    if done:')
    lines.append('        _rescan()')
    lines.append('    return done')
    lines.append('')
    lines.append('')
    lines.append('def uninstall_some(names):')
    lines.append('    """Remove the named themes. Same whitelist as install_some()."""')
    lines.append('    return [n for n in THEME_ORDER if n in (names or []) and uninstall(n)]')
    lines.append('')
    lines.append('')
    lines.append('# ---- optional stock-theme update ----------------------------------------')
    lines.append('# Installing the custom themes NEVER touches a stock theme. Separately and')
    lines.append('# optionally, the four ON-DISK stock variants can take a small additions')
    lines.append('# file (color-scheme + themed scrollbars) appended via one @import line at')
    lines.append('# the end of their index.css -- their look is unchanged, and restoring is')
    lines.append('# deleting that file and that line. light and dark live INSIDE the')
    lines.append('# Perspective module jar: there are no files on disk to update, so they')
    lines.append('# are never touched (pick light-cool / dark-cool to get the additions).')
    lines.append('')
    lines.append('STOCK_BUILTIN = ["light", "dark"]')
    lines.append('STOCK_UPDATABLE = ["light-cool", "light-warm", "dark-cool", "dark-warm"]')
    lines.append('STOCK_ORDER = ["light", "light-cool", "light-warm",')
    lines.append('               "dark", "dark-cool", "dark-warm"]')
    lines.append('STOCK_DARK = {"light": False, "light-cool": False, "light-warm": False,')
    lines.append('              "dark": True, "dark-cool": True, "dark-warm": True}')
    lines.append('ADDITIONS_FILE = "theme-additions.css"')
    lines.append("ADDITIONS_IMPORT = '@import \"./theme-additions.css\";'")
    lines.append('# Written under a different name before v1.7.1. A gateway that ran')
    lines.append('# "Update stock themes" on an older build still carries it, so both the')
    lines.append('# file and its @import line are recognised and removed -- otherwise the')
    lines.append('# rename strands a file that Restore can no longer see and stock_state')
    lines.append('# reports "stock" for a theme that is still carrying additions.')
    lines.append('LEGACY_ADDITIONS = ["gaskony-additions.css"]')
    lines.append("LEGACY_IMPORTS = ['@import \"./%s\";' % n for n in LEGACY_ADDITIONS]")
    lines.append('ADDITIONS_CSS = {')
    lines.append('    False: %s,' % py_repr(additions_css(False)))
    lines.append('    True: %s,' % py_repr(additions_css(True)))
    lines.append('}')
    lines.append('')
    lines.append('')
    lines.append('def _read(path):')
    lines.append('    fh = open(path, "rb")')
    lines.append('    try:')
    lines.append('        return fh.read().decode("utf-8")')
    lines.append('    finally:')
    lines.append('        fh.close()')
    lines.append('')
    lines.append('')
    lines.append('def _write(path, text):')
    lines.append('    fh = open(path, "wb")')
    lines.append('    try:')
    lines.append('        fh.write(text.encode("utf-8"))')
    lines.append('    finally:')
    lines.append('        fh.close()')
    lines.append('')
    lines.append('')
    lines.append('def _stock_rewrite_manifest(theme_dir):')
    lines.append('    """resource.json must list the files actually in the directory (and')
    lines.append('    the now-stale signature must go, the same unstamped way the custom')
    lines.append('    themes ship -- the scan re-stamps it). The description survives."""')
    lines.append('    path = os.path.join(theme_dir, "resource.json")')
    lines.append('    doc = {"scope": "G", "version": 1, "restricted": False,')
    lines.append('           "overridable": True, "attributes": {}}')
    lines.append('    try:')
    lines.append('        old = json.loads(_read(path))')
    lines.append('        if old.get("description"):')
    lines.append('            doc["description"] = old["description"]')
    lines.append('    except (Exception, Throwable):')
    lines.append('        pass')
    lines.append('    doc["files"] = [n for n in sorted(os.listdir(theme_dir))')
    lines.append('                    if n != "resource.json"]')
    lines.append('    _write(path, json.dumps(doc, indent=2))')
    lines.append('')
    lines.append('')
    lines.append('def stock_state(name):')
    lines.append('    """\'builtin\' (jar-served, never touched) | \'missing\' (not on this')
    lines.append('    gateway) | \'updated\' (carries the additions) | \'stock\'."""')
    lines.append('    if name in STOCK_BUILTIN:')
    lines.append('        return "builtin"')
    lines.append('    d = os.path.join(_themes_root(), name)')
    lines.append('    idx = os.path.join(d, "index.css")')
    lines.append('    if not os.path.isfile(idx):')
    lines.append('        return "missing"')
    lines.append('    try:')
    lines.append('        text = _read(idx)')
    lines.append('    except (Exception, Throwable):')
    lines.append('        return "missing"')
    lines.append('    for filename, marker in ([(ADDITIONS_FILE, ADDITIONS_IMPORT)] +')
    lines.append('                            zip(LEGACY_ADDITIONS, LEGACY_IMPORTS)):')
    lines.append('        if marker in text and os.path.isfile(os.path.join(d, filename)):')
    lines.append('            return "updated"')
    lines.append('    return "stock"')
    lines.append('')
    lines.append('')
    lines.append('def _stock_drop_legacy(d):')
    lines.append('    """Remove a pre-1.7.1 additions file and its @import. Returns whether')
    lines.append('    anything was there."""')
    lines.append('    changed = False')
    lines.append('    idx_path = os.path.join(d, "index.css")')
    lines.append('    for filename in LEGACY_ADDITIONS:')
    lines.append('        path = os.path.join(d, filename)')
    lines.append('        if os.path.isfile(path):')
    lines.append('            os.remove(path)')
    lines.append('            changed = True')
    lines.append('    if os.path.isfile(idx_path):')
    lines.append('        idx = _read(idx_path)')
    lines.append('        kept = [l for l in idx.splitlines()')
    lines.append('                if l.strip() not in LEGACY_IMPORTS]')
    lines.append('        if len(kept) != len(idx.splitlines()):')
    lines.append('            _write(idx_path, "\\n".join(kept) + "\\n")')
    lines.append('            changed = True')
    lines.append('    return changed')
    lines.append('')
    lines.append('')
    lines.append('def _stock_update_files(name):')
    lines.append('    if name not in STOCK_UPDATABLE:')
    lines.append('        raise ValueError("\'%s\' is not an updatable stock theme" % name)')
    lines.append('    d = os.path.join(_themes_root(), name)')
    lines.append('    if not os.path.isfile(os.path.join(d, "index.css")):')
    lines.append('        return False    # variant absent on this gateway -- skip, not an error')
    lines.append('    _stock_drop_legacy(d)')
    lines.append('    _write(os.path.join(d, ADDITIONS_FILE), ADDITIONS_CSS[STOCK_DARK[name]])')
    lines.append('    idx_path = os.path.join(d, "index.css")')
    lines.append('    idx = _read(idx_path)')
    lines.append('    if ADDITIONS_IMPORT not in idx:')
    lines.append('        # index.css is @import lines only, so one more AT THE END is valid')
    lines.append('        # css and the gateway flattener inlines it after everything stock.')
    lines.append('        if not idx.endswith("\\n"):')
    lines.append('            idx += "\\n"')
    lines.append('        _write(idx_path, idx + ADDITIONS_IMPORT + "\\n")')
    lines.append('    _stock_rewrite_manifest(d)')
    lines.append('    return True')
    lines.append('')
    lines.append('')
    lines.append('def _stock_restore_files(name):')
    lines.append('    if name not in STOCK_UPDATABLE:')
    lines.append('        raise ValueError("\'%s\' is not an updatable stock theme" % name)')
    lines.append('    d = os.path.join(_themes_root(), name)')
    lines.append('    idx_path = os.path.join(d, "index.css")')
    lines.append('    changed = False')
    lines.append('    add_path = os.path.join(d, ADDITIONS_FILE)')
    lines.append('    if os.path.isfile(add_path):')
    lines.append('        os.remove(add_path)')
    lines.append('        changed = True')
    lines.append('    if _stock_drop_legacy(d):')
    lines.append('        changed = True')
    lines.append('    if os.path.isfile(idx_path):')
    lines.append('        idx = _read(idx_path)')
    lines.append('        if ADDITIONS_IMPORT in idx:')
    lines.append('            kept = [l for l in idx.splitlines()')
    lines.append('                    if l.strip() != ADDITIONS_IMPORT]')
    lines.append('            _write(idx_path, "\\n".join(kept) + "\\n")')
    lines.append('            changed = True')
    lines.append('    if changed:')
    lines.append('        _stock_rewrite_manifest(d)')
    lines.append('    return changed')
    lines.append('')
    lines.append('')
    lines.append('def stock_update_all():')
    lines.append('    """Add the additions to every on-disk stock variant, then ONE scan.')
    lines.append('    Safe to re-run (idempotent); their look does not change."""')
    lines.append('    updated = [n for n in STOCK_UPDATABLE if _stock_update_files(n)]')
    lines.append('    if updated:')
    lines.append('        _rescan()')
    lines.append('    return updated')
    lines.append('')
    lines.append('')
    lines.append('def stock_restore_all():')
    lines.append('    """Put every updated stock variant back exactly as stock."""')
    lines.append('    restored = [n for n in STOCK_UPDATABLE if _stock_restore_files(n)]')
    lines.append('    if restored:')
    lines.append('        _rescan()')
    lines.append('    return restored')
    lines.append('')
    lines.append('')
    lines.append('def status():')
    lines.append('    """Custom rows ({kind: "custom", installed}) in THEME_ORDER, then')
    lines.append('    stock rows ({kind: "stock", stock: stock_state}) in STOCK_ORDER,')
    lines.append('    for the Installer view\'s table."""')
    lines.append('    installed = set()')
    lines.append('    try:')
    lines.append('        for res in system.config.getResources(')
    lines.append('                moduleId="com.inductiveautomation.perspective", typeId="themes"):')
    lines.append('            installed.add(str(res.getName()))')
    lines.append('    except (Exception, Throwable):')
    lines.append('        pass')
    lines.append('    out = []')
    lines.append('    for name in THEME_ORDER:')
    lines.append('        theme = THEMES[name]')
    lines.append('        out.append({')
    lines.append('            "id": name,')
    lines.append('            "label": theme["label"],')
    lines.append('            "dark": theme["dark"],')
    lines.append('            "kind": "custom",')
    lines.append('            "installed": name in installed,')
    lines.append('        })')
    lines.append('    for name in STOCK_ORDER:')
    lines.append('        out.append({')
    lines.append('            "id": name,')
    lines.append('            "label": name.replace("-", " ").capitalize(),')
    lines.append('            "dark": STOCK_DARK[name],')
    lines.append('            "kind": "stock",')
    lines.append('            "stock": stock_state(name),')
    lines.append('        })')
    lines.append('    # Themes somebody made on the Customise page. Neither list')
    lines.append('    # knew about them, so creating one put it on no page at all.')
    lines.append('    imported = set(imported_themes())')
    lines.append('    for name in user_themes():')
    lines.append('        out.append({')
    lines.append('            "id": name,')
    lines.append('            "label": name,')
    lines.append('            "dark": user_base_of(name) == "dark",')
    lines.append('            "kind": "imported" if name in imported else "user",')
    lines.append('            "installed": name in installed,')
    lines.append('        })')
    lines.append('    return out')
    lines.append('')

    # The insight functions are hand-authored and commit-tracked rather than
    # emitted line by line -- 200 lines of lines.append() would be unreadable
    # and unreviewable, and unlike the THEMES data none of this is derived
    # from out/. Same precedent as selector-popup/: source in the repo, copied
    # in verbatim at build time. It is appended (not imported) so the shipped
    # project stays one self-contained script module.
    with open(INSIGHT_SRC) as handle:
        lines.append(handle.read().rstrip("\n"))
    lines.append('')

    # The editor functions, same deal. Appended AFTER insight so it can use
    # _read/_write/_rescan/_stock_rewrite_manifest and THEMES, all defined above.
    with open(EDITOR_SRC) as handle:
        editor = handle.read().rstrip("\n")
    # The page draws a fixed number of chips at fixed indexes and themepack
    # pads its answer to match. A mismatch is silent at runtime -- too few
    # values and every chip past the end is a binding in error -- so it is
    # caught here instead.
    declared = re.search(r'^EDITOR_SWATCH_COUNT\s*=\s*(\d+)', editor, re.M)
    if not declared or int(declared.group(1)) != SWATCH_COUNT:
        raise SystemExit("build_manager.py: SWATCH_COUNT is %d but "
                         "editor_code.py declares %s"
                         % (SWATCH_COUNT,
                            declared.group(1) if declared else "nothing"))
    lines.append(editor)
    lines.append('')
    # Import last: it uses theme_kind, user_themes, _vars_of, theme_css,
    # live_preview_uri and EDITOR_ID_RE from the two above.
    with open(IMPORT_SRC) as handle:
        lines.append(handle.read().rstrip("\n"))
    lines.append('')
    return "\n".join(lines)


def py_repr(text):
    """repr() a plain-ASCII str for embedding as a Jython 2 source literal.

    All out/ content was verified ASCII-only at generation time (build_theme.py
    / build_css.py never emit non-ASCII), so Python's own repr() round-trips
    exactly with no encoding surprises -- this is not hand-rolled escaping."""
    return repr(text)


# One padding for every page root: the tab strip must not shift when the
# page changes. A per-page padding (the Installer's root at 24px,
# Customise's at 14/18/16) puts the strip that is meant to be the SAME piece
# of furniture on both at a different offset on each page. A shared strip
# needs a shared origin; two literals in two builders is how they drift.
PAGE_PADDING = "14px 18px 16px"


def build_view_json(themes, version):
    # Property-binding transform scripts and component event scripts in this
    # workspace's Perspective views are stored as the BODY of an
    # Ignition-synthesised function, one leading tab per line (confirmed live
    # against access-manager/.../Roles/view.json and
    # toolbox-playbooks/.../Monitor/view.json, both of which use
    # self.view.custom.<x> the same way this view does).
    # The thumbnails, baked in at build time as one dict literal. They are
    # derived from out/ exactly like the gallery is, so a row's picture and the
    # files Install writes cannot drift apart -- and no gateway round-trip is
    # needed to draw them.
    previews_literal = json.dumps(preview_cell_map(themes), sort_keys=True)
    status_transform_code = (
        "\timport themepack\n"
        "\tPREVIEWS = " + previews_literal + "\n"
        "\tCELL_STYLE = " + json.dumps(PREVIEW_CELL_STYLE,
                                      sort_keys=True) + "\n"
        "\trows = themepack.status()\n"
        "\tSTOCK_STATE = {\n"
        "\t\t'stock': 'Stock - not modified',\n"
        "\t\t'updated': 'Updated (scrollbars + colour scheme)',\n"
        "\t\t'builtin': 'Inside the Perspective module - never touched',\n"
        "\t\t'missing': 'Not on this gateway',\n"
        "\t}\n"
        "\tfor row in rows:\n"
        "\t\tkind = row.get('kind')\n"
        "\t\trow['mode'] = 'Dark' if row['dark'] else 'Light'\n"
        "\t\trow['set'] = {'custom': 'Ours', 'user': 'Yours',\n"
        "\t\t\t'imported': 'Imported'}.get(kind, 'Stock')\n"
        "\t\tif kind == 'custom':\n"
        "\t\t\trow['state'] = 'Installed' if row['installed'] else 'Not installed'\n"
        "\t\telif kind == 'user':\n"
        "\t\t\trow['state'] = 'Made here -- edit or delete it on Customise'\n"
        "\t\telif kind == 'imported':\n"
        "\t\t\trow['state'] = 'Installed -- Remove ticked deletes it'\n"
        "\t\telse:\n"
        "\t\t\trow['state'] = STOCK_STATE.get(row.get('stock'), '?')\n"
        "\t\trow['preview'] = PREVIEWS.get(row['id'], '')\n"
        "\t\trow['pick'] = False\n"
        "\t\tif kind in ('user', 'imported'):\n"
        "\t\t\t# No baked thumbnail -- these did not exist when the\n"
        "\t\t\t# project was built. Draw it from what the gateway is\n"
        "\t\t\t# serving now, the same picture Customise previews.\n"
        "\t\t\ttry:\n"
        "\t\t\t\tstyle = dict(CELL_STYLE)\n"
        "\t\t\t\tstyle['backgroundImage'] = 'url(%s)' % (\n"
        "\t\t\t\t\tthemepack.live_preview_uri(row['id'], 148, 38))\n"
        "\t\t\t\trow['preview'] = {'value': '', 'style': style}\n"
        "\t\t\texcept Exception:\n"
        "\t\t\t\trow['preview'] = ''\n"
        "\treturn rows"
    )
    root = {
        "custom": {
            "tick": 0,
            "themes": [],
            "picked": [],
            # A table gets an explicit height or it renders as a header with
            # nothing under it, and the row count is no longer a constant now
            # that anyone can make a theme.
            "tblheight": "740px",
        },
        "params": {},
        "props": {
            "defaultSize": {"width": 900, "height": 720},
        },
        "propConfig": {
            "custom.themes": {
                "binding": {
                    "type": "property",
                    "config": {"path": "view.custom.tick"},
                    "transforms": [
                        {"type": "script", "code": status_transform_code}
                    ],
                }
            },
            "custom.tblheight": {
                "binding": {
                    "type": "property",
                    "config": {"path": "view.custom.themes"},
                    "transforms": [{"type": "script", "code": (
                        "\t# 38px a row -- the thumbnail sets it -- plus a\n"
                        "\t# 30px header and 2px of slack. Measured off\n"
                        "\t# the live table, not chosen: at 44 the box\n"
                        "\t# ran 104px past its own last row.\n"
                        "\treturn '%dpx' % (34 + 38 * len(value or []))")}],
                }
            }
        },
        "root": {
            "type": "ia.container.flex",
            "meta": {"name": "root"},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {
                "direction": "column",
                "style": {
                    "height": "100%",
                    "overflow": "auto",
                    "padding": PAGE_PADDING,
                    "gap": "16px",
                    "backgroundColor": "var(--containerRoot)",
                },
            },
            "children": [
                # Same nav as the insight pages. Without it those pages are
                # reachable only by typing the URL, which is not shipping them.
                _nav("Installer", version, "{view.custom.tick}"),
                _action_grid(themes),
                _ticked_bar(),
                {
                    "type": "ia.display.table",
                    "meta": {"name": "themes_table"},
                    # An EXPLICIT height, not grow 1 and not basis auto.
                    # This page scrolls now that the previews are on it: a
                    # grow-1 item in an overflowing column collapses to
                    # nothing, and a Perspective table does not size itself to
                    # its rows either, so basis auto gave a header and no body.
                    # 16 rows (10 custom + 6 stock) at ~31px plus the header.
                    # 16 rows at 44px (measured -- the thumbnail sets the row
                    # height and the table measures it from content) plus a
                    # 32px header. Not grow 1: this page scrolls, and a grow-1
                    # item in an overflowing column collapses to nothing.
                    "position": {"grow": 0, "shrink": 0, "basis": "680px"},
                    # position.basis is bindable, and it has to be: a fixed
                    # 740px was 16 rows exactly, so the first theme somebody
                    # made was a row you had to scroll a table to reach.
                    "props": {
                        "data": [],
                        "pager": {"top": False, "bottom": False},
                        # The tick is the selection; a row highlight as well
                        # would show the last click, not what is ticked.
                        "selection": {"enableRowSelection": False},
                        "columns": [
                            {
                                # Ticks, not row selection: Ctrl-click to pick
                                # several is not something anyone finds. Not
                                # an editable cell: that takes one click to
                                # enter edit mode and another to tick. The
                                # row click below toggles it instead.
                                "field": "pick",
                                # An empty title shows the field name instead.
                                "header": {"title": "Tick"},
                                "width": 44,
                                "strictWidth": True,
                                "render": "boolean",
                                "boolean": "checkbox",
                                "justify": "center",
                            },
                            {
                                # The picture first, so the table reads as the
                                # gallery it replaces rather than as a list
                                # with a decoration on the end.
                                "field": "preview",
                                "header": {"title": "Preview"},
                                "width": 168,
                                "strictWidth": True,
                            },
                            {
                                "field": "set",
                                "header": {"title": "Set"},
                                "width": 90,
                                "strictWidth": True,
                            },
                            {
                                "field": "label",
                                "header": {"title": "Theme"},
                            },
                            {
                                "field": "mode",
                                "header": {"title": "Mode"},
                                "width": 100,
                                "strictWidth": True,
                            },
                            {
                                "field": "state",
                                "header": {"title": "Status"},
                                "width": 320,
                                "strictWidth": True,
                            },
                        ],
                    },
                    "propConfig": {
                        "props.data": {
                            "binding": {
                                "type": "property",
                                "config": {"path": "view.custom.themes"},
                            }
                        },
                        "position.basis": {
                            "binding": {
                                "type": "property",
                                "config": {"path": "view.custom.tblheight"},
                            }
                        },
                    },
                    "events": {"component": {"onRowClick": {
                        "type": "script", "scope": "G", "config": {"script": (
                            "\trow = self.props.data[event.row]\n"
                            "\t# Only ours and imported themes can be acted on;\n"
                            "\t# a tick on any other row would do nothing.\n"
                            "\tif row['kind'] not in ('custom', 'imported'):\n"
                            "\t\treturn\n"
                            "\tself.props.data[event.row].pick = not row['pick']\n"
                            "\tself.view.custom.picked = [r['id'] for r in self.props.data if r['pick']]\n")}}}},
                },
            ],
        },
    }
    return root



# ---------------------------------------------------------------------------
# The two insight pages. Both are thin: every number on them comes from
# themepack's insight functions reading the live gateway, so these builders
# lay out components and nothing else -- there is no figure here to go stale.
# ---------------------------------------------------------------------------

# Only binding forms this project already proves are used: `expr` with a script
# transform (ThemeDropdown's options) and `property` with one (the Installer's
# status table). expr-struct appears nowhere in the estate, so a dependency on
# two properties is expressed as an expr binding that CONCATENATES them into
# one key, which the rows binding then watches. Guessing an unproven binding
# type here would fail the way they fail in Perspective: silently, with a blank
# table and no log line.
def _expr(expression, code):
    return {"type": "expr", "config": {"expression": expression},
            "transforms": [{"type": "script", "code": code}]}


def _prop(path, code=None):
    binding = {"type": "property", "config": {"path": path}}
    if code:
        binding["transforms"] = [{"type": "script", "code": code}]
    return binding


def _label(name, text, size="13px", colour="var(--label)", weight=None, grow=0):
    style = {"fontSize": size, "color": colour}
    if weight:
        style["fontWeight"] = weight
    return {"type": "ia.display.label", "meta": {"name": name},
            "position": {"grow": grow, "shrink": 0, "basis": "auto"},
            "props": {"text": text, "style": style}}


def _nav(active, version, refresh=None):
    """A tab strip across the top. These are separate PAGES, so this cannot be
    an ia.container.tab -- that switches views inside one view. It is a row of
    tabs drawn to look like one: the active tab carries the accent underline
    and does not offer to navigate to the page you are already on.

    It also carries the project's name and version: putting the identity in
    the strip, which already spans the page and has room, avoids a separate
    24px heading on every page that would repeat the tab you had just
    clicked and stamp the same version twice."""
    # Two pages. "The themes" is folded into the Installer -- seeing what
    # you are about to install, on the page that installs it, is better than
    # a gallery you have to navigate to. "How it works" is redundant once
    # that happens, and "For builders" belongs in the Editor, where the
    # token and class list is something you read WHILE editing rather than
    # a page of its own.
    # The route stays /editor even though the LABEL is not "file editor" --
    # the page is no longer only that.
    pages = [("Installer", "/"), ("Customise", "/editor"), ("Import", "/import")]
    # The name leads, the way an app bar does. Bottom-aligned with the tabs and
    # padded to match them, or it floats off the baseline they sit on.
    tabs = [{"type": "ia.display.label", "meta": {"name": "brand"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"text": TITLE + "  " + version,
                       "style": {"fontSize": "13.5px", "fontWeight": 600,
                                 "whiteSpace": "nowrap",
                                 "color": "var(--label)",
                                 "padding": "9px 18px 8px 2px",
                                 "borderBottomStyle": "solid",
                                 "borderBottomWidth": "2px",
                                 "borderBottomColor": "transparent"}}}]
    for title, path in pages:
        current = title == active
        style = {"fontSize": "13px", "padding": "9px 16px 8px",
                 "cursor": "default" if current else "pointer",
                 "whiteSpace": "nowrap",
                 "borderBottomStyle": "solid", "borderBottomWidth": "2px",
                 "borderBottomColor": ("var(--callToAction)" if current
                                       else "transparent"),
                 "color": ("var(--label)" if current
                           else "var(--neutral-70)"),
                 # The SAME weight either way. Bolding only the active tab
                 # made each tab change width when it became active, so the
                 # tabs after it slid sideways every time you changed page --
                 # a strip that is meant to be one fixed piece of furniture.
                 # Colour and the accent underline already say which is which.
                 "fontWeight": 600}
        tab = {"type": "ia.display.label",
               "meta": {"name": "tab_" + (path.strip("/") or "home")},
               "position": {"grow": 0, "shrink": 0, "basis": "auto"},
               "props": {"text": title, "style": style}}
        if not current:
            # DOM event, not component: onClick under events.component is
            # accepted, saved and never fires -- the tabs looked right and did
            # nothing. events.component is for a component's OWN events
            # (a button's onActionPerformed); onClick is the browser's.
            tab["events"] = {"dom": {"onClick": {
                "config": {"script":
                           "\tsystem.perspective.navigate(page='%s')" % path},
                "scope": "G", "type": "script"}}}
            _keyboard_click(tab)
        tabs.append(tab)
    # A spacer, then the switcher, hard right. It rides in the tab strip so a
    # reader can repaint the page from ANY page -- comparing the previews
    # against the theme you are actually running is the point of the gallery,
    # and having to come back to the Installer to change it broke that.
    # It is the same ThemeDropdown view a project would copy, embedded rather
    # than duplicated, so what is demonstrated is the real artefact.
    tabs.append({"type": "ia.container.flex", "meta": {"name": "spacer"},
                 "position": {"grow": 1, "shrink": 1, "basis": "0px"},
                 "props": {}})
    switcher = {"type": "ia.display.view", "meta": {"name": "theme_switcher"},
                "position": {"grow": 0, "shrink": 0, "basis": "230px"},
                "props": {"path": "ThemeDropdown", "params": {"refresh": 0},
                          "style": {"minHeight": "34px",
                                    "marginBottom": "4px"}}}
    # The theme list inside it is read when its options binding evaluates, so
    # passing the page's counter in is what makes a theme you just made appear
    # in the menu at once rather than on the view's own 30s floor. It works
    # only because ThemeDropdown declares paramDirection input for it; without
    # that the value is silently discarded (see the transform's note there).
    if refresh:
        switcher["propConfig"] = {"props.params.refresh": {
            "binding": {"type": "expr", "config": {"expression": refresh}}}}
    tabs.append(switcher)
    return {"type": "ia.container.flex", "meta": {"name": "tabs"},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {"direction": "row", "alignItems": "flex-end",
                      "style": {"gap": "2px", "marginBottom": "6px",
                                "borderBottomStyle": "solid",
                                "borderBottomWidth": "1px",
                                "borderBottomColor": "var(--border)"}},
            "children": tabs}


def _stat(key, caption):
    """One headline number AND its caption, both from view.custom.counts.

    The caption is bound, not literal: it has to say "differ from Nord Dark"
    when a comparison is chosen and "of Ignition's variables repainted" when
    one is not. A literal string was wrong in the first case.
    """
    return {
        "type": "ia.container.flex", "meta": {"name": "stat_" + key},
        "position": {"grow": 1, "shrink": 1, "basis": "0px"},
        "props": {"direction": "column",
                  "style": {"padding": "10px 12px", "borderRadius": "8px",
                            "backgroundColor": "var(--container)",
                            "border": "var(--containerBorder)"}},
        "children": [
            {"type": "ia.display.label", "meta": {"name": "n"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"style": {"fontSize": "24px", "fontWeight": 600,
                                 "color": "var(--label)"}},
             "propConfig": {"props.text": {"binding": {
                 "type": "expr",
                 "config": {"expression": "{view.custom.counts.%s}" % key}}}}},
            {"type": "ia.display.label", "meta": {"name": "caption"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"text": caption,
                       "style": {"fontSize": "12px",
                                 "color": "var(--neutral-70)"}},
             "propConfig": {"props.text": {"binding": {
                 "type": "expr",
                 "config": {"expression": "{view.custom.counts.cap_%s}" % key}}}}},
        ],
    }


def _table(name, columns, path):
    return {
        "type": "ia.display.table", "meta": {"name": name},
        "position": {"grow": 1, "shrink": 1, "basis": "0px"},
        # No pager, ever (workspace rule) -- these lists are meant to be
        # scrolled and read, not paged through twenty rows at a time.
        "props": {"pager": {"top": False, "bottom": False}, "columns": columns},
        "propConfig": {"props.data": {"binding": _prop(path)}},
    }


def _col(field, title, width=None, strict=False):
    col = {"field": field, "header": {"title": title}}
    if width:
        col["width"] = width
        col["strictWidth"] = strict
    return col


CHANGES_ROWS = (
    "\timport themepack\n"
    "\ttheme, against = (value + '|').split('|')[:2]\n"
    "\tif not theme:\n"
    "\t\treturn []\n"
    "\treturn themepack.compare(theme, against or None)"
)
CHANGES_COUNTS = (
    "\timport themepack\n"
    "\ttheme, against = (value + '|').split('|')[:2]\n"
    "\tif not theme:\n"
    "\t\treturn {}\n"
    "\treturn themepack.summary(theme, against or None)"
)
CHANGES_HEADLINE = (
    "\timport themepack\n"
    "\ttheme, against = (value + '|').split('|')[:2]\n"
    "\tif not theme:\n"
    "\t\treturn ''\n"
    "\treturn themepack.headline(theme, against or None)"
)
CHANGES_LAYERS = (
    "\timport themepack\n"
    "\tif not value:\n"
    "\t\treturn []\n"
    "\treturn themepack.layers(value)"
)
# EVERY theme present on this gateway, not just the ten this project installs
# -- examining a stock theme that has been given the optional additions is a
# question the page could not be asked if the left-hand list offered custom
# themes only.
INSTALLED_OPTIONS = (
    "\timport themepack\n"
    "\tstock, custom = [], []\n"
    "\tfor r in themepack.status():\n"
    "\t\tif r.get('kind') != 'custom':\n"
    "\t\t\tif r.get('stock') == 'missing':\n"
    "\t\t\t\tcontinue\n"
    "\t\t\tstock.append({'value': r['id'],\n"
    "\t\t\t'label': themepack.label_of(r['id'])})\n"
    "\t\telif r.get('installed'):\n"
    "\t\t\tcustom.append({'value': r['id'], 'label': r['label']})\n"
    "\treturn stock + custom"
)
# Ignition's own themes come FIRST and say so. Leaving them last and
# unlabelled at the bottom of a flat 17-item list makes the comparison a
# reader most wants ("what did you change from stock?") the one they have
# to scroll past ten custom themes to find, with nothing telling them which
# six are Ignition's -- easy to conclude they are not offered at all.
AGAINST_OPTIONS = (
    "\timport themepack\n"
    "\topts = [{'value': '', 'label': 'its own base theme'}]\n"
    "\tstock, custom = [], []\n"
    "\tfor r in themepack.status():\n"
    "\t\tif r.get('kind') != 'custom':\n"
    "\t\t\tlabel = r['label']\n"
    "\t\t\tif not label.startswith('Ignition'):\n"
    "\t\t\t\tlabel = 'Ignition ' + label[0].lower() + label[1:]\n"
    "\t\t\tstock.append({'value': r['id'], 'label': label})\n"
    "\t\telif r.get('installed'):\n"
    "\t\t\tcustom.append({'value': r['id'], 'label': r['label']})\n"
    "\treturn opts + stock + custom"
)
FIRST_INSTALLED = (
    "\timport themepack\n"
    "\tfor r in themepack.status():\n"
    "\t\tif r.get('kind') == 'custom' and r.get('installed'):\n"
    "\t\t\treturn r['id']\n"
    "\treturn ''"
)
CONTRACT_TOKENS = (
    "\timport themepack\n"
    "\tif not value:\n"
    "\t\treturn []\n"
    "\treturn themepack.contract(value)"
)
CONTRACT_CLASSES = (
    "\timport themepack\n"
    "\tif not value:\n"
    "\t\treturn []\n"
    "\treturn themepack.contract_classes(value)"
)


def _theme_picker(name, label, custom_path, options_code):
    return {
        "type": "ia.container.flex", "meta": {"name": name},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "column", "style": {"gap": "3px"}},
        "children": [
            _label("cap", label, size="12px", colour="var(--neutral-70)"),
            {"type": "ia.input.dropdown", "meta": {"name": "dd"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"allowClearing": False, "showSearch": False,
                       "style": {"height": "34px", "minWidth": "220px"}},
             "propConfig": {
                 "props.options": {"binding": _expr("1", options_code)},
                 # bidirectional goes INSIDE config or it is silently ignored
                 # and the dropdown never writes the selection back.
                 "props.value": {"binding": {
                     "type": "property",
                     "config": {"path": custom_path, "bidirectional": True}}},
             }},
        ],
    }





# ---------------------------------------------------------------------------
# The miniature screen, drawn with LITERAL colours at build time.
#
# This began as one parameterised view fed by a flex-repeater, and it did not
# work: view.params never resolved inside it, through a repeater OR a direct
# ia.display.view embed, with no error in the console, no gateway log line and
# every literal string still rendering -- so the gallery laid out perfectly in
# plain white twelve times. Property bindings, expression bindings and binding
# props.style as a whole object all failed identically.
#
# Baking the colours in is not a workaround, it is the more honest artefact:
# the installer already EMBEDS each theme's files, so a preview drawn from the
# same embedded copy shows exactly what pressing Install will produce -- and
# it renders with no bindings, no params and nothing that can silently fail.
# The measurement pages stay live; the picture is a picture.
# ---------------------------------------------------------------------------

STOCK_PALETTES = os.path.join(HERE, "stock-palettes.json")

# Ignition's light/dark define nearly everything as var(--neutral-NN); a
# preview holding a var() reference renders in the VIEWING page's colours,
# quietly showing the wrong thing rather than nothing.
_VARDEF = re.compile(r'^[ \t]*(--[A-Za-z0-9_-]+)[ \t]*:[ \t]*([^;]+);', re.M)


def theme_palette(theme):
    """The dozen colours one preview is painted with, from out/ at build time."""
    values = {}
    for filename in ("variables.css", "globals.css"):
        for match in _VARDEF.finditer(theme["files"].get(filename, "")):
            values[match.group(1)] = match.group(2).strip()

    def resolve(value, hops=0):
        while value.startswith("var(") and hops < 6:
            name = re.match(r'var\(\s*(--[A-Za-z0-9_-]+)', value)
            if not name:
                return ""
            value = values.get(name.group(1), "").strip()
            hops += 1
        return "" if value.startswith("var(") else value

    def pick(*names):
        for name in names:
            value = resolve(values.get(name, "").strip())
            if value and value != "transparent":
                return value
        return ""

    page = pick("--st-page-solid", "--containerRoot")
    return {
        "page": page,
        "sidebar": pick("--st-sidebar-solid", "--containerNested", "--container"),
        "card": pick("--st-card", "--container"),
        "text": pick("--st-fg", "--label"),
        "muted": pick("--label--disabled", "--label"),
        "chromeFg": pick("--st-chrome-fg", "--label"),
        "accent": pick("--st-accent", "--callToAction"),
        "onAccent": pick("--st-on-accent") or "#ffffff",
        "border": pick("--st-chrome-border", "--border"),
        "headBg": pick("--st-head-solid", "--containerNested", "--container"),
        "headFg": pick("--st-head-fg", "--label"),
        "rowBg": pick("--st-row-bg") or page,
        "cellFg": pick("--st-cell-fg", "--label"),
    }


def preview_svg(pal):
    """The mini screen again, as ONE SVG string, for the status table.

    Puts the theme images in the table. The gallery draws the
    same screen out of Perspective components, which cannot go in a table cell
    -- a view-render column takes ONE viewPath for every row, and a per-row
    preview would have to be parameterised, which this repo already records as
    failing silently (see the note above preview_node). An SVG needs none of
    that: it is a string, it goes in a custom cell's backgroundImage, and the
    swatch column already proves custom-cell styles work.

    Same palette, same layout as preview_node, drawn small enough to read at
    the ~64px a table row can give it.
    """
    def c(key, fallback="#888888"):
        return pal.get(key) or fallback

    W, H = 200, 60
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d">' % (W, H, W, H)]
    def rect(x, y, w, h, fill, rx=0):
        parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" '
                     'rx="%s"/>' % (x, y, w, h, fill, rx))

    rect(0, 0, W, H, c("page"))                       # the page
    rect(0, 0, W, 11, c("sidebar"), 0)                # top bar
    rect(0, 11, 26, H - 11, c("sidebar"), 0)          # nav rail
    # three nav lines
    for i in range(3):
        rect(5, 18 + i * 5, 16, 2, c("chromeFg"), 1)
    # the card
    rect(32, 16, 92, 26, c("card"), 2)
    rect(36, 20, 54, 3, c("text"), 1)
    rect(36, 26, 44, 2, c("muted"), 1)
    rect(36, 32, 30, 7, c("accent"), 2)
    rect(40, 35, 22, 2, c("onAccent"), 1)
    # the table
    rect(130, 16, 64, 26, c("headBg"), 2)
    rect(130, 16, 64, 7, c("headBg"), 2)
    rect(133, 19, 26, 2, c("headFg"), 1)
    for i in range(2):
        rect(130, 25 + i * 8, 64, 7, c("rowBg"))
        rect(133, 28 + i * 8, 30, 2, c("cellFg"), 1)
    # title text in the top bar
    rect(5, 4, 34, 3, c("chromeFg"), 1)
    # No outer stroke. At 148px wide in a table row the border lands on the
    # row divider and reads as the thumbnail being clipped; the page colour
    # already separates one preview from the next.
    parts.append("</svg>")
    return "".join(parts)


def preview_data_uri(pal):
    """base64 rather than percent-encoding: an SVG carries #rrggbb by the
    dozen, and a raw '#' inside a url() truncates it at the first colour."""
    import base64
    return "data:image/svg+xml;base64," + base64.b64encode(
        preview_svg(pal).encode("utf-8")).decode("ascii")


# One style for a thumbnail cell, shared by the ten baked at build time and by
# a user theme's picture drawn at request time -- two copies of these numbers
# is two rows of different heights in one table.
# The height fits INSIDE the 44px row the thumbnail itself creates, so the
# image is never cut by the row divider.
PREVIEW_CELL_STYLE = {
    "backgroundRepeat": "no-repeat",
    "backgroundPosition": "center",
    "backgroundSize": "contain",
    "height": "38px", "width": "148px",
}


def preview_cell_map(themes):
    """{theme id: custom cell} for every theme the status table can list --
    ours from out/, Ignition's own from the captured stock palettes."""
    cells = {}
    order, _labels, palettes = _stock_palettes()
    for theme_id in order:
        cells[theme_id] = palettes[theme_id]
    for theme in themes:
        cells[theme["id"]] = theme_palette(theme)
    def cell(pal):
        style = dict(PREVIEW_CELL_STYLE)
        style["backgroundImage"] = "url(%s)" % preview_data_uri(pal)
        return {"value": "", "style": style}

    return dict((k, cell(v)) for k, v in cells.items())


def _flex(name, children=None, direction="column", grow=0, basis="auto", style=None):
    node = {"type": "ia.container.flex", "meta": {"name": name},
            "position": {"grow": grow, "shrink": 0, "basis": basis},
            "props": {"direction": direction, "style": style or {}}}
    if children:
        node["children"] = children
    return node


def _txt(name, text, size, colour, weight=None):
    style = {"fontSize": size, "color": colour, "lineHeight": "1.25",
             "whiteSpace": "nowrap", "overflow": "hidden"}
    if weight:
        style["fontWeight"] = weight
    return {"type": "ia.display.label", "meta": {"name": name},
            "position": {"grow": 0, "shrink": 1, "basis": "auto"},
            "props": {"text": text, "style": style}}


def preview_node(name, pal, label, caption):
    """A whole screen in 230px: top bar, rail, a card with a button, a table."""
    c = lambda k, fallback="#888888": pal.get(k) or fallback
    topbar = _flex("topbar", direction="row", basis="24px", style={
        "backgroundColor": c("sidebar"), "alignItems": "center",
        "gap": "6px", "padding": "0 8px"}, children=[
            _flex("dot", basis="10px", style={
                "backgroundColor": c("accent"), "height": "10px",
                "borderRadius": "5px"}),
            _txt("apptitle", "My Plant", "9px", c("chromeFg"), 600)])
    rail = _flex("rail", basis="38px", style={
        "backgroundColor": c("sidebar"), "gap": "5px",
        "padding": "8px 6px"}, children=[
            _flex("nav%d" % i, basis="4px", style={
                "backgroundColor": c("chromeFg"), "height": "4px",
                "borderRadius": "2px",
                "opacity": "0.9" if i == 0 else "0.45"}) for i in range(3)])
    card = _flex("card", style={
        "backgroundColor": c("card"), "border": "1px solid " + c("border"),
        "borderRadius": "5px", "padding": "6px 8px", "gap": "3px"}, children=[
            _txt("t", "Pump 4 - running", "9px", c("text"), 600),
            _txt("s", "Flow steady at 42 L/s", "8px", c("muted")),
            _flex("btn", direction="row", style={
                "backgroundColor": c("accent"), "borderRadius": "4px",
                "padding": "3px 8px", "alignSelf": "flex-start",
                "marginTop": "3px"}, children=[
                    _txt("b", "Acknowledge", "8px", c("onAccent"), 600)])])
    table = _flex("table", style={
        "marginTop": "6px", "borderRadius": "4px", "overflow": "hidden",
        "border": "1px solid " + c("border")}, children=[
            _flex("th", direction="row", basis="15px", style={
                "backgroundColor": c("headBg"), "alignItems": "center",
                "padding": "0 6px"}, children=[
                    _txt("h", "Tag            Value", "8px", c("headFg"), 600)]),
            _flex("r0", direction="row", basis="14px", style={
                "backgroundColor": c("rowBg"), "alignItems": "center",
                "padding": "0 6px"}, children=[
                    _txt("v", "FT-101       42.0", "8px", c("cellFg"))]),
            _flex("r1", direction="row", basis="14px", style={
                "alignItems": "center", "padding": "0 6px"}, children=[
                    _txt("v", "PT-102        3.1", "8px", c("cellFg"))])])
    screen = _flex("screen", grow=1, basis="0px", style={
        "backgroundColor": c("page"), "border": "1px solid " + c("border"),
        "borderRadius": "6px", "overflow": "hidden"}, children=[
            topbar,
            _flex("body", direction="row", grow=1, basis="0px", children=[
                rail,
                _flex("main", grow=1, basis="0px", style={
                    "padding": "7px"}, children=[card, table])])])
    return _flex(name, basis="205px", style={"gap": "0px"}, children=[
        _flex("frame", basis="150px", children=[screen]),
        _txt("name", label, "12px", "var(--label)", 600),
        _txt("cap", caption, "11px", "var(--neutral-70)")])


def _layer_card(i):
    """One of the three build layers, as a card rather than a table row.

    This was a three-row table and it clipped twice: a table sizes to rows,
    and these are paragraphs. Cards wrap instead of truncating.
    """
    def bound(field, size, colour, weight=None):
        style = {"fontSize": size, "color": colour}
        if weight:
            style["fontWeight"] = weight
        return {"type": "ia.display.label", "meta": {"name": field},
                "position": {"grow": 0, "shrink": 0, "basis": "auto"},
                "props": {"style": style},
                "propConfig": {"props.text": {"binding": {
                    "type": "expr",
                    "config": {"expression": "{view.custom.layers[%d].%s}" % (i, field)}}}}}
    return {
        "type": "ia.container.flex", "meta": {"name": "layer%d" % i},
        "position": {"grow": 1, "shrink": 1, "basis": "0px"},
        "props": {"direction": "column",
                  "style": {"padding": "10px 12px", "gap": "5px",
                            "borderRadius": "8px",
                            "backgroundColor": "var(--container)",
                            "border": "var(--containerBorder)"}},
        "children": [
            bound("layer", "13px", "var(--label)", 600),
            bound("what", "12px", "var(--neutral-70)"),
            bound("here", "12px", "var(--label)"),
        ],
    }



# ---------------------------------------------------------------------------
# The two lay pages. "The themes" answers "what do they look like" with a
# gallery of painted screens; "How it works" answers "what is going on" with
# the same screen painted twice and three sentences. The measurement pages
# stay, demoted to "under the hood".
# ---------------------------------------------------------------------------


def _prose(name, text, size="13px", colour="var(--label)"):
    return {"type": "ia.display.label", "meta": {"name": name},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {"text": text,
                      "style": {"fontSize": size, "color": colour,
                                "lineHeight": "1.55", "maxWidth": "880px"}}}


def _gallery(name, cards):
    return {"type": "ia.container.flex", "meta": {"name": name},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {"direction": "row", "wrap": "wrap",
                      "style": {"gap": "16px", "rowGap": "18px"}},
            "children": cards}


def _stock_palettes():
    """(order, labels, palettes) for Ignition's own themes, as captured."""
    data = json.load(open(STOCK_PALETTES))
    return data["order"], data["labels"], data["palettes"]


def _action_scripts():
    """The button bodies, in one place: the grid builds the buttons now, and
    the popup note below is the most expensive comment in this file."""
    install_all_script = (
        "\timport themepack\n"
        "\tthemepack.install_all()\n"
        "\tself.view.custom.tick += 1"
    )
    remove_all_script = (
        "\timport themepack\n"
        "\tthemepack.uninstall_all()\n"
        "\tself.view.custom.tick += 1"
    )
    update_stock_script = (
        "\timport themepack\n"
        "\tthemepack.stock_update_all()\n"
        "\tself.view.custom.tick += 1"
    )
    restore_stock_script = (
        "\timport themepack\n"
        "\tthemepack.stock_restore_all()\n"
        "\tself.view.custom.tick += 1"
    )
    # Size is passed HERE, at the call, not as the popup view's own
    # props.defaultSize -- see tools/themes/selector-popup/README.md.
    #
    # NOTE ON THE FORM: the originally specified
    # height='min(460px, 88vh)', width='min(560px, 94vw)' kwargs do not exist
    # on this Ignition version's system.perspective.openPopup -- confirmed
    # both live (a Jython reflection probe against
    # PerspectiveScriptingFunctions.openPopup on module-testing showed no
    # top-level width/height parameter at all -- unknown kwargs are silently
    # swallowed, which is exactly what made the CSS-string form look like it
    # "did nothing" rather than erroring) and against IA's own 8.1/8.3
    # scripting-function reference (width/height are keys INSIDE the
    # `position` dict, typed Dictionary[String, Integer] -- pixels only, no
    # CSS calc()/min()/vw units). The size therefore goes in `position={...}`
    # -- still entirely at the call site, never `props.defaultSize` -- and
    # `viewportBound=True` still does the "never bigger than a short
    # viewport" job the min()/vw forms were reaching for (verified live at
    # 1440x530: the frame stays full-size and is shifted to sit fully
    # inside, rather than being shrunk or clipped).
    #
    # NOTE ON THE HEIGHT VALUE: 460 (the originally specified figure) left
    # the swatch grid 17px taller than the space available inside the frame
    # at EVERY viewport height tried (not a short-viewport-specific problem
    # -- confirmed by measuring scrollHeight vs clientHeight on the "rows"
    # container at both 900px and 530px viewports, identical overflow both
    # times), so the bottom row needed the rows container's own
    # `overflow: auto` to reach at all. 480 cleared it with the content of the
    # day (10 custom + 6 stock swatches, two section labels, one hint line)
    # with zero internal scroll, confirmed the same way.
    #
    # The popup has since grown an "Any theme on this gateway" dropdown below
    # the grid -- a bordered section worth 62px -- and an empty-state line
    # that only appears when no pack is installed, so the frame is 590,
    # checked the same way at both viewport heights.
    open_switcher_script = (
        "\tsystem.perspective.openPopup(\n"
        "\t\t'theme-installer-selector',\n"
        "\t\t'SelectorPopup',\n"
        "\t\ttitle='Theme switcher',\n"
        "\t\tmodal=True,\n"
        "\t\tdraggable=True,\n"
        "\t\tresizable=False,\n"
        "\t\toverlayDismiss=True,\n"
        "\t\tviewportBound=True,\n"
        "\t\tposition={'width': 560, 'height': 590})"
    )

    # view.custom.picked holds the ids ticked in the table; the table's
    # onEditCellCommit keeps it current. themepack filters again, so a stock
    # or user row can never be acted on.
    install_some_script = (
        "\timport themepack\n"
        "\tthemepack.install_some(list(self.view.custom.picked))\n"
        "\tself.view.custom.picked = []\n"
        "\tself.view.custom.tick += 1"
    )
    remove_some_script = (
        "\timport themepack\n"
        "\tnames = list(self.view.custom.picked)\n"
        "\tthemepack.uninstall_some(names)\n"
        "\tthemepack.remove_imported(names)\n"
        "\tself.view.custom.picked = []\n"
        "\tself.view.custom.tick += 1"
    )

    return {"install": install_all_script,
            "remove": remove_all_script,
            "install_some": install_some_script,
            "remove_some": remove_some_script,
            "update_stock": update_stock_script,
            "restore_stock": restore_stock_script,
            "switcher": open_switcher_script}


def _action_card(name, title, body, buttons, note=None):
    """One category: what it is, what it does to the gateway, and its buttons.

    The buttons sit at the BOTTOM of the card and the card is a column, so three
    cards with different amounts of prose still line their buttons up. Without
    that the row reads as three unrelated boxes.
    """
    children = [
        {"type": "ia.display.label", "meta": {"name": "title"},
         "position": {"grow": 0, "shrink": 0, "basis": "auto"},
         "props": {"text": title,
                   "style": {"fontSize": "15px", "fontWeight": 600,
                             "color": "var(--label)"}}},
        # Short bullets, one line each: the cards are read at a glance.
        {"type": "ia.display.label", "meta": {"name": "body"},
         "position": {"grow": 0, "shrink": 0, "basis": "auto"},
         "props": {"text": "\n".join("\u2022  " + line for line in body),
                   "style": {"fontSize": "12.5px", "lineHeight": "1.6",
                             "whiteSpace": "pre-line",
                             "color": "var(--neutral-70)"}}},
    ]
    if note:
        children.append(
            {"type": "ia.display.label", "meta": {"name": "note"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"text": note,
                       "style": {"fontSize": "12px", "lineHeight": "1.5",
                                 "color": "var(--neutral-70)",
                                 "fontStyle": "italic"}}})
    # The spacer is what pushes the buttons down. It is the card's only grower.
    children.append({"type": "ia.container.flex", "meta": {"name": "gap"},
                     "position": {"grow": 1, "shrink": 1, "basis": "0px"},
                     "props": {}})
    children.append(
        {"type": "ia.container.flex", "meta": {"name": "buttons"},
         "position": {"grow": 0, "shrink": 0, "basis": "auto"},
         "props": {"direction": "row", "wrap": "wrap",
                   "style": {"gap": "8px", "rowGap": "8px"}},
         "children": buttons})
    return {
        "type": "ia.container.flex", "meta": {"name": name},
        # Equal thirds: same basis, same growth, so the three cards are one
        # grid rather than three boxes sized by how much text each holds.
        "position": {"grow": 1, "shrink": 1, "basis": "0px"},
        "props": {"direction": "column",
                  "style": {"gap": "7px", "padding": "14px 15px",
                            "borderRadius": "4px",
                            "backgroundColor": "var(--container)",
                            "borderStyle": "solid", "borderWidth": "1px",
                            "borderColor": "var(--border)",
                            "minHeight": "0px"}},
        "children": children,
    }


def _act_button(name, text, script, kind="normal"):
    style = {"whiteSpace": "nowrap", "height": "32px"}
    if kind == "primary":
        pass                                   # the theme's own call-to-action
    elif kind == "quiet":
        style.update({"backgroundColor": "transparent",
                      "border": "1px solid var(--border)",
                      "color": "var(--label)"})
    else:
        style.update({"backgroundColor": "var(--containerNested)",
                      "color": "var(--label)"})
    return {"type": "ia.input.button", "meta": {"name": name},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {"text": text, "style": style},
            "events": {"component": {"onActionPerformed": {
                "config": {"script": script}, "scope": "G", "type": "script"}}}}


def _ticked_bar():
    """One line above the table: what is ticked, and the two buttons for it."""
    scripts = _action_scripts()
    count = "len({view.custom.picked})"
    caption = {"type": "ia.display.label", "meta": {"name": "ticked_caption"},
               "position": {"grow": 1, "shrink": 1, "basis": "0px"},
               "props": {"style": {"fontSize": "12.5px",
                                   "color": "var(--neutral-70)"}},
               "propConfig": {"props.text": {"binding": {"type": "expr",
                   "config": {"expression": (
                       "if(%s = 0, 'Tick themes in the table to install or "
                       "remove just those.', %s + ' ticked')" % (count, count))}}}}}
    buttons = []
    for name, text, key in (("install_ticked_btn", "Install ticked", "install_some"),
                            ("remove_ticked_btn", "Remove ticked", "remove_some")):
        button = _act_button(name, text, scripts[key])
        button["propConfig"] = {"props.enabled": {"binding": {"type": "expr",
            "config": {"expression": "%s > 0" % count}}}}
        buttons.append(button)
    return {"type": "ia.container.flex", "meta": {"name": "ticked"},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {"direction": "row", "alignItems": "center",
                      "style": {"gap": "8px", "marginBottom": "-6px"}},
            "children": [caption] + buttons}


def _action_grid(themes):
    """The top of the Installer: three cards of related buttons.

    Grouped into three cards rather than two paragraphs of prose followed by
    a flat row of five buttons, so each explanation sits next to the
    buttons it describes -- a caveat about stock themes above 'Install
    custom themes' would tell you nothing about which button it applies
    to -- and each card stays short enough to read.
    """
    scripts = _action_scripts()
    return {
        "type": "ia.container.flex", "meta": {"name": "top"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "column", "style": {"gap": "12px"}},
        "children": [
            # No heading. It said the name of the project on the page you were
            # already on, under a tab strip that now says it once.
            {"type": "ia.container.flex", "meta": {"name": "cards"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"direction": "row", "alignItems": "stretch",
                       "wrap": "wrap",
                       "style": {"gap": "12px", "rowGap": "12px"}},
             "children": [
                 _action_card(
                     "card_custom",
                     "Pre-Packaged Themes",
                     ["Install adds them to every project's Theme menu",
                      "No gateway restart; open sessions update on reload",
                      "Install again to repair them after an upgrade",
                      "Never touches Ignition's themes or your own"],
                     [_act_button("install_all_btn", "Install",
                                  scripts["install"], kind="primary"),
                      _act_button("remove_all_btn", "Remove",
                                  scripts["remove"])]),
                 _action_card(
                     "card_stock",
                     "Ignition's own themes",
                     ["Improvements to Stock Themes",
                      "Update: themed scrollbars and colour scheme only",
                      "Restore: puts them back exactly"],
                     [_act_button("update_stock_btn", "Update",
                                  scripts["update_stock"]),
                      _act_button("restore_stock_btn", "Restore",
                                  scripts["restore_stock"])]),
                 _action_card(
                     "card_try",
                     "Try one",
                     ["Popup repaints this page as you click",
                      "The Theme menu, top right, does the same",
                      "Both are views to copy into your own projects",
                      "Themes stay if you delete this project"],
                     [_act_button("theme_switcher_btn", "Theme switcher",
                                  scripts["switcher"], kind="quiet")]),
             ]},
        ],
    }


def _gallery_block(themes):
    """The previews as a wall of cards. NOT CURRENTLY USED.

    Moved off its own page once the theme images went INTO the status
    table: with every row carrying its own thumbnail, a second copy of the
    same sixteen pictures underneath is duplication rather than emphasis.
    Kept because the cards are considerably more readable than a 148px
    thumbnail and this is the only thing that draws them; delete it if it
    is still unused.
    """
    order, labels, palettes = _stock_palettes()
    stock = [preview_node("stock%d" % i, palettes[theme_id],
                          labels.get(theme_id, theme_id),
                          "dark" if "dark" in theme_id else "light")
             for i, theme_id in enumerate(order)]
    ours = [preview_node("t%d" % i, theme_palette(theme), theme["label"],
                         "dark" if theme["dark"] else "light")
            for i, theme in enumerate(sorted(themes, key=lambda t: t["label"]))]
    return {
        "type": "ia.container.flex", "meta": {"name": "previews"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "column", "style": {"gap": "12px",
                                                   "marginTop": "6px"}},
        "children": [
            _label("ours_h", "The %d themes this project installs" % len(themes),
                   size="15px", weight=600),
            _prose("ours_sub",
                   "Each little screen is the same imaginary plant page drawn "
                   "in that theme's colours. Install them, then pick one from "
                   "any project's Theme button.",
                   size="12px", colour="var(--neutral-70)"),
            _gallery("ours", ours),
            _label("stock_h", "What every gateway starts with", size="15px",
                   weight=600),
            _prose("stock_sub",
                   "Ignition's own six. Never modified by this project, and "
                   "they stay available alongside the ones it installs.",
                   size="12px", colour="var(--neutral-70)"),
            _gallery("stock", stock),
        ],
    }


def _bound_button(name, script, expression, primary=False):
    """A button whose label is an expression -- for a toggle, where the label
    is the only thing saying which state you are in."""
    node = _button(name, "", script, primary=primary)
    node["propConfig"] = {"props.text": {"binding": {
        "type": "expr", "config": {"expression": expression}}}}
    return node


def _bound_cap(name, expression, size="12px"):
    node = _cap(name, "", size=size)
    # It wraps: a caption that changes with the mode is not one length, and
    # nowrap turns the longer of the two into a line running off the page.
    node["position"] = {"grow": 1, "shrink": 1, "basis": "auto"}
    node["props"]["style"]["whiteSpace"] = "normal"
    node["propConfig"] = {"props.text": {"binding": {
        "type": "expr", "config": {"expression": expression}}}}
    return node


# ---------------------------------------------------------------------------
# THE EDITOR
#
# Built to operate the same or similar way to the Designer theme builder,
# rather than as a token TABLE with an edit strip -- fine for changing one
# colour, useless for the thing a theme editor is for, which is opening a
# file and working in it.
#
# So this is the shape Ectobox's Designer module has, in a browser: the files
# down the left, the file you picked filling the middle, and a toolbar that
# saves and scans. "For builders" is folded in on the right, because the
# --st-* tokens and st/... classes a theme publishes are something you read
# WHILE editing it, not on a page you navigate to.
#
# Perspective has no code editor and cannot be given one without a WebDev page
# in an iframe -- and an iframe cannot talk back to Perspective, so Save would
# have to become its own HTTP endpoint. That is a real dependency and a second
# way to write these files. The text box is a text box; everything else about
# the page is the editor.
# ---------------------------------------------------------------------------

EDITOR_THEME_OPTIONS = (
    "\timport themepack\n"
    "\t# Say what each one IS. The label was '(not ours)', which is true\n"
    "\t# of a theme you just made and reads as a disclaimer about it.\n"
    "\tsuffix = {'user': '  (yours)', 'stock': \"  (Ignition's)\"}\n"
    "\tout = []\n"
    "\tfor r in themepack.list_themes():\n"
    "\t\tkind = themepack.theme_kind(r['id'])\n"
    "\t\tout.append({'value': r['id'],\n"
    "\t'label': r['id'] + suffix.get(kind, '')})\n"
    "\treturn out"
)
EDITOR_FIRST_THEME = (
    "\timport themepack\n"
    "\tfor r in themepack.list_themes():\n"
    "\t\tif r['ours']:\n"
    "\t\t\treturn r['id']\n"
    "\trows = themepack.list_themes()\n"
    "\treturn rows[0]['id'] if rows else ''"
)
# The file rail. The 'edited' mark answers the question you actually have when
# you come back to a gateway you changed last week: which of these is not what
# the installer ships any more.
EDITOR_FILE_ROWS = (
    "\timport themepack\n"
    "\ttheme = (value + '|').split('|')[0]\n"
    "\tif not theme:\n"
    "\t\treturn []\n"
    "\ttry:\n"
    "\t\trows = themepack.list_files(theme)\n"
    "\texcept Exception:\n"
    "\t\treturn []\n"
    "\tout = []\n"
    "\tfor r in rows:\n"
    "\t\tif not r['editable']:\n"
    "\t\t\tcontinue\n"
    "\t\tmark = ''\n"
    "\t\ttry:\n"
    "\t\t\tif themepack.read_file(theme, r['name'])['modified']:\n"
    "\t\t\t\tmark = u'  \\u25cf'\n"
    "\t\texcept Exception:\n"
    "\t\t\tpass\n"
    "\t\t# The marker rides on the NAME. A column of its own needs a header,\n"
    "\t\t# and an empty header title falls back to the field name -- which is\n"
    "\t\t# how a 26px column came to be labelled 'sta'.\n"
    "\t\tout.append({'name': r['name'] + mark})\n"
    "\treturn out"
)
# The raw pane's file picker. Only the editable text files -- resource.json is
# the manifest and is rewritten on every save.
EDITOR_FILE_OPTIONS = (
    "\timport themepack\n"
    "\ttheme = (value + '|').split('|')[0]\n"
    "\tif not theme:\n"
    "\t\treturn []\n"
    "\ttry:\n"
    "\t\trows = themepack.list_files(theme)\n"
    "\texcept Exception:\n"
    "\t\treturn []\n"
    "\treturn [{'value': r['name'], 'label': r['name']}\n"
    "\tfor r in rows if r['editable']]"
)
EDITOR_TEXT = (
    "\timport themepack\n"
    "\ttheme, filename = (value + '|').split('|')[:2]\n"
    "\tif not theme or not filename:\n"
    "\t\treturn ''\n"
    "\ttry:\n"
    "\t\treturn themepack.read_file(theme, filename)['text']\n"
    "\texcept Exception as e:\n"
    "\t\treturn str(e)"
)
EDITOR_ABOUT = (
    "\timport themepack\n"
    "\ttheme = (value + '|').split('|')[0]\n"
    "\tif not theme:\n"
    "\t\treturn []\n"
    "\ttry:\n"
    "\t\treturn themepack.about_text(theme)\n"
    "\texcept Exception:\n"
    "\t\treturn ''"
)
EDITOR_PICK_FILE = (
    "\tdata = event.value or {}\n"
    "\t# Strip the edited marker back off -- the row carries it for display.\n"
    "\tname = (data.get('name', '') or '').split(' ')[0].strip()\n"
    "\tif name:\n"
    "\t\tself.view.custom.file = name\n"
    "\t\tself.view.custom.status = ''"
)
EDITOR_SAVE = (
    "\timport themepack\n"
    "\ttheme = self.view.custom.theme\n"
    "\tfilename = self.view.custom.file\n"
    "\tif not filename:\n"
    "\t\tself.view.custom.status = 'Pick a file first'\n"
    "\t\treturn\n"
    "\ttry:\n"
    "\t\tresult = themepack.write_file(theme, filename,\n"
    "\t\tself.view.custom.text)\n"
    "\t\tself.view.custom.status = ('Saved %s (%d bytes) and scanned'\n"
    "\t\t% (filename, result['bytes']))\n"
    "\t\tself.view.custom.nudge = self.view.custom.nudge + 1\n"
    "\texcept Exception as e:\n"
    "\t\tself.view.custom.status = str(e)"
)
EDITOR_REVERT = (
    "\timport themepack\n"
    "\tfilename = self.view.custom.file\n"
    "\tif not filename:\n"
    "\t\tself.view.custom.status = 'Pick a file first'\n"
    "\t\treturn\n"
    "\ttry:\n"
    "\t\tthemepack.revert_file(self.view.custom.theme, filename)\n"
    "\t\tself.view.custom.status = ('Put back what the installer ships for %s'\n"
    "\t\t% filename)\n"
    "\t\tself.view.custom.nudge = self.view.custom.nudge + 1\n"
    "\texcept Exception as e:\n"
    "\t\tself.view.custom.status = str(e)"
)
EDITOR_REFRESH = (
    "\timport themepack\n"
    "\ttry:\n"
    "\t\tthemepack.refresh()\n"
    "\t\t# Bump the key too, or the scan runs and every binding on this page\n"
    "\t\t# keeps showing what it read before it.\n"
    "\t\tself.view.custom.nudge = self.view.custom.nudge + 1\n"
    "\t\tself.view.custom.status = 'Scanned -- the gateway has re-read the themes'\n"
    "\texcept Exception as e:\n"
    "\t\tself.view.custom.status = str(e)"
)


# Managing themes of your own. The Installer's buttons refuse any id outside
# the ten this project carries -- that is what makes them safe to press -- so a
# theme somebody makes here needs its own create and delete, and those refuse
# the packaged and stock ids just as firmly in the other direction.
EDITOR_BASE_OPTIONS = (
    "\timport themepack\n"
    "\treturn [{'value': t, 'label': t} for t in themepack.base_options()]"
)
EDITOR_KIND = (
    "\timport themepack\n"
    "\ttheme = (value + '|').split('|')[0]\n"
    "\tif not theme:\n"
    "\t\treturn ''\n"
    "\treturn themepack.theme_kind(theme)"
)
# The badge answers "am I allowed to break this?", which is the first thing
# anyone wants to know on this page.
# What the page may offer for the selected theme. The ten are generated and
# Install overwrites them, so they are shown read-only with a copy offered
# instead -- see why_not_editable().
EDITOR_LOCKED = (
    "\timport themepack\n"
    "\ttheme = (value + '|').split('|')[0]\n"
    "\tif not theme:\n"
    "\t\treturn 'There is no theme selected.'\n"
    "\treturn themepack.why_not_editable(theme)"
)
EDITOR_PREVIEW = (
    "\timport themepack\n"
    "\ttheme = (value + '|').split('|')[0]\n"
    "\tif not theme:\n"
    "\t\treturn ''\n"
    "\ttry:\n"
    "\t\treturn 'url(%s)' % themepack.live_preview_uri(theme, 320, 96)\n"
    "\texcept Exception:\n"
    "\t\treturn ''"
)
# The colours, grouped by what they affect, from the file this theme actually
# declares -- you can only change what is written here.
EDITOR_TOKEN_ROWS = (
    "\timport themepack\n"
    "\tbits = (value + '|||').split('|')\n"
    "\ttheme = bits[0]\n"
    "\t# The filter rides in the key, so typing re-reads the list. 150\n"
    "\t# values is ten screens of scrolling to reach one token.\n"
    "\tneedle = bits[3].strip().lower()\n"
    "\tif not theme:\n"
    "\t\treturn []\n"
    "\ttry:\n"
    "\t\trows = themepack.all_tokens(theme)\n"
    "\texcept Exception:\n"
    "\t\treturn []\n"
    "\tif needle:\n"
    "\t\trows = [r for r in rows\n"
    "\t\tif needle in r['name'].lower()\n"
    "\t\tor needle in (r.get('what') or '').lower()\n"
    "\t\tor needle in (r.get('group') or '').lower()\n"
    "\t\tor needle in (r['value'] or '').lower()]\n"
    "\tout = []\n"
    "\tlast = None\n"
    "\tfor r in rows:\n"
    "\t\tgroup = r['group']\n"
    "\t\tout.append({'group': group if group != last else '',\n"
    "\t\t'name': r['name'],\n"
    "\t\t'what': r.get('what', ''),\n"
    "\t\t'swatch': r['swatch'],\n"
    "\t\t'value': r['value']})\n"
    "\t\tlast = group\n"
    "\treturn out"
)
EDITOR_SEL_OK = (
    "\timport themepack\n"
    "\t# The colour to paint the chip, or nothing. Never the raw value:\n"
    "\t# CSS ignores what it cannot parse, so an invalid one left the\n"
    "\t# chip showing the PREVIOUS colour and reading as success.\n"
    "\treturn value if themepack.looks_like_colour(value) else ''"
)
EDITOR_WARN = (
    "\timport themepack\n"
    "\tname, new = (value + '|').split('|')[:2]\n"
    "\tif not name or not new:\n"
    "\t\treturn ''\n"
    "\ttheme = self.view.custom.theme\n"
    "\ttry:\n"
    "\t\told = ''\n"
    "\t\tfor row in themepack.all_tokens(theme):\n"
    "\t\t\tif row['name'] == name:\n"
    "\t\t\t\told = row['value']\n"
    "\t\treturn themepack.value_problem(name, old, new)\n"
    "\texcept Exception:\n"
    "\t\treturn ''"
)
EDITOR_UNDO = (
    "\timport themepack\n"
    "\tname = self.view.custom.undo_name\n"
    "\twas = self.view.custom.undo_value\n"
    "\tif not name:\n"
    "\t\treturn\n"
    "\ttry:\n"
    "\t\tthemepack.set_any_token(self.view.custom.theme, name, was)\n"
    "\t\tself.view.custom.status = 'Put %s back to %s' % (name, was)\n"
    "\t\tself.view.custom.sel_name = name\n"
    "\t\tself.view.custom.sel_value = was\n"
    "\t\t# One level, and it is spent. Two Undos in a row putting the\n"
    "\t\t# same value back twice would be a button that lies.\n"
    "\t\tself.view.custom.undo_name = ''\n"
    "\t\tself.view.custom.undo_value = ''\n"
    "\t\tself.view.custom.nudge = self.view.custom.nudge + 1\n"
    "\texcept Exception as e:\n"
    "\t\tself.view.custom.status = str(e)"
)
EDITOR_START_OPTIONS = (
    "\timport themepack\n"
    "\treturn [{'value': r['id'], 'label': r['label']}\n"
    "\tfor r in themepack.start_points()]"
)
EDITOR_START_WARNING = (
    "\timport themepack\n"
    "\tif not value:\n"
    "\t\treturn ''\n"
    "\ttry:\n"
    "\t\treturn themepack.start_warning(value)\n"
    "\texcept Exception:\n"
    "\t\treturn ''"
)

# Chips in the palette row. Must match themepack.EDITOR_SWATCH_COUNT --
# asserted at build time, because a mismatch is silent at runtime.
SWATCH_COUNT = 16

EDITOR_SWATCHES = (
    "\timport themepack\n"
    "\t# Always SWATCH_COUNT entries, never a short list: each chip binds to a\n"
    "\t# fixed index, so [] puts all sixteen bindings in error and draws the\n"
    "\t# palette as sixteen red boxes.\n"
    "\tempty = [''] * %d\n"
    "\ttheme = (value + '|||').split('|')[0]\n"
    "\tif not theme:\n"
    "\t\treturn empty\n"
    "\ttry:\n"
    "\t\treturn themepack.swatches(theme) or empty\n"
    "\texcept Exception:\n"
    "\t\treturn empty" % SWATCH_COUNT
)


def _keyboard_click(component):
    """Give a clickable label the keyboard route its onClick lacks: Tab
    reaches it, and Enter or Space runs the same script."""
    component["meta"]["tabIndex"] = 0
    dom = component["events"]["dom"]
    body = "\n".join("\t" + line for line in dom["onClick"]["config"]["script"].splitlines())
    dom["onKeyDown"] = {"config": {"script": "\tif event.key in ('Enter', ' '):\n" + body},
                        "scope": "G", "type": "script"}
    return component


def _pick_swatch(index):
    """Filling sel_value IS the click: the hex field is bidirectional to it,
    and the confirmation chip repaints from the same property, so the colour
    lands in the box and is shown back before anything is saved."""
    return ("\tcolours = self.view.custom.swatches or []\n"
            "\tif len(colours) > %d and colours[%d]:\n"
            "\t\tself.view.custom.sel_value = colours[%d]\n"
            "\t\tself.view.custom.status = ''" % (index, index, index))


EDITOR_PICK_TOKEN = (
    "\tdata = event.value or {}\n"
    "\tself.view.custom.sel_name = data.get('name', '')\n"
    "\tself.view.custom.sel_value = data.get('value', '')\n"
    "\tself.view.custom.status = ''"
)
EDITOR_SAVE_TOKEN = (
    "\timport themepack\n"
    "\tname = self.view.custom.sel_name\n"
    "\tif not name:\n"
    "\t\tself.view.custom.status = 'Pick a value in the list first'\n"
    "\t\treturn\n"
    "\tvalue = self.view.custom.sel_value\n"
    "\ttry:\n"
    "\t\t# set_any_token finds the file: --st-* live in globals.css and\n"
    "\t\t# Ignition's own names in variables.css, and the page never showed\n"
    "\t\t# the user which is which. It also refuses a value that would\n"
    "\t\t# stop the token working, which is why this can fail loudly.\n"
    "\t\tresult = themepack.set_any_token(self.view.custom.theme,\n"
    "\t\tname, value)\n"
    "\t\t# Remember what it replaced. Nobody remembers the hex they\n"
    "\t\t# overwrote, and there was no way back from a wrong save.\n"
    "\t\tself.view.custom.undo_name = name\n"
    "\t\tself.view.custom.undo_value = result.get('was', '')\n"
    "\t\t# Report the VALUE, not just the name: 'Saved --st-accent' is\n"
    "\t\t# equally true of a save that wrote back what was already there.\n"
    "\t\tself.view.custom.status = 'Saved %s = %s' % (name, value)\n"
    "\t\tself.view.custom.nudge = self.view.custom.nudge + 1\n"
    "\texcept Exception as e:\n"
    "\t\tself.view.custom.status = str(e)"
)
EDITOR_TOGGLE_RAW = (
    "\tself.view.custom.raw = not self.view.custom.raw\n"
    "\tself.view.custom.status = ''"
)
IS_EDITABLE = "{view.custom.kind} = 'user'"
IS_LOCKED = "{view.custom.kind} != 'user'"
SHOW_RAW = "{view.custom.kind} = 'user' && {view.custom.raw}"
# The colour list is shown for ANY theme: reading what a theme sets is what
# you do before deciding to copy it. Only the strip that CHANGES one is gated.
SHOW_TOKENS = "{view.custom.kind} != '' && !{view.custom.raw}"


EDITOR_KIND_LABEL = (
    "\timport themepack\n"
    "\ttheme = (value + '|').split('|')[0]\n"
    "\tif not theme:\n"
    "\t\treturn ''\n"
    "\tkind = themepack.theme_kind(theme)\n"
    "\t# base_of() answers from the built-in tables, so for a theme made\n"
    "\t# here it falls through to 'light' -- and called every copy of a\n"
    "\t# dark theme light.\n"
    "\tbase = (themepack.user_base_of(theme) if kind == 'user'\n"
    "\telse themepack.base_of(theme))\n"
    "\t# Plain ASCII, and a sentence rather than dash-separated fragments.\n"
    "\t# A non-ASCII character in a Jython 2 str literal is BYTES, not a code\n"
    "\t# point: the separator here arrived on the page as mojibake.\n"
    "\twords = {\n"
    "\t\t'packaged': '%s is one of the ten pre-packaged themes, built "
    "on %s. Install on the first page puts it back.',\n"
    "\t\t'stock': \"%s is one of Ignition's own, built on %s. Editing "
    "it changes every project using it.\",\n"
    "\t\t'user': '%s is yours, built on %s. Nothing on the Installer "
    "page overwrites it.',\n"
    "\t}\n"
    "\t# The NAME leads: the badge always says which theme it describes,\n"
    "\t# so after a create -- when the picker is the only other thing\n"
    "\t# naming it -- the page still names it somewhere.\n"
    "\ttext = words.get(kind, kind)\n"
    "\tif '%s' in text:\n"
    "\t\ttext = text % (theme, base or 'a stock theme')\n"
    "\treturn text"
)
# The banner's button and the bar's button are the same door, deliberately:
# "Copy this one" and "New theme" look like alternatives but are not
# comparable.
EDITOR_START_NEW = (
    "\t# One door. It opens pre-set to the theme you are looking at,\n"
    "\t# which is the answer nine times out of ten.\n"
    "\tself.view.custom.making = 'make'\n"
    "\tself.view.custom.new_base = self.view.custom.theme\n"
    "\tself.view.custom.new_name = 'my-' + (self.view.custom.theme or 'theme')\n"
    "\tself.view.custom.status = ''"
)
EDITOR_COPY_THIS = EDITOR_START_NEW
EDITOR_CANCEL = (
    "\tself.view.custom.making = ''\n"
    "\tself.view.custom.new_name = ''\n"
    "\tself.view.custom.status = ''"
)
EDITOR_NEW = (
    "\timport themepack\n"
    "\tname = (self.view.custom.new_name or '').strip()\n"
    "\ttry:\n"
    "\t\t# make_theme copies one of ours, or builds on a bare Ignition\n"
    "\t\t# theme, depending on what was chosen -- one action, because\n"
    "\t\t# two buttons made them look like comparable alternatives.\n"
    "\t\tthemepack.make_theme(name, self.view.custom.new_base)\n"
    "\t\tself.view.custom.new_name = ''\n"
    "\t\tself.view.custom.making = ''\n"
    "\t\t# nudge FIRST: it is what re-reads the theme list, and a\n"
    "\t\t# selection the options do not contain yet shows as blank.\n"
    "\t\tself.view.custom.nudge = self.view.custom.nudge + 1\n"
    "\t\tself.view.custom.theme = name\n"
    "\t\tself.view.custom.file = 'variables.css'\n"
    "\t\tself.view.custom.status = ('Created %s from %s -- it looks exactly "
    "like it until you change something'\n"
    "\t\t% (name, self.view.custom.new_base))\n"
    "\texcept Exception as e:\n"
    "\t\tself.view.custom.status = str(e)"
)
EDITOR_COPY = (
    "\timport themepack\n"
    "\tname = (self.view.custom.new_name or '').strip()\n"
    "\tsource = self.view.custom.theme\n"
    "\ttry:\n"
    "\t\tthemepack.copy_theme(source, name)\n"
    "\t\tself.view.custom.new_name = ''\n"
    "\t\tself.view.custom.making = ''\n"
    "\t\tself.view.custom.nudge = self.view.custom.nudge + 1\n"
    "\t\tself.view.custom.theme = name\n"
    "\t\tself.view.custom.file = 'variables.css'\n"
    "\t\tself.view.custom.status = ('Copied %s to %s -- you are now "
    "editing the copy' % (source, name))\n"
    "\texcept Exception as e:\n"
    "\t\tself.view.custom.status = str(e)"
)
EDITOR_DELETE = (
    "\timport themepack\n"
    "\ttheme = self.view.custom.theme\n"
    "\ttry:\n"
    "\t\tif themepack.delete_theme(theme):\n"
    "\t\t\tself.view.custom.status = 'Deleted %s' % theme\n"
    "\t\telse:\n"
    "\t\t\tself.view.custom.status = 'There was no %s to delete' % theme\n"
    "\t\t# Land on another theme rather than on an empty picker: the\n"
    "\t\t# dropdown's default only evaluates once, so clearing it leaves\n"
    "\t\t# 'Select...' and an editor with nothing in it.\n"
    "\t\trows = themepack.list_themes()\n"
    "\t\tmine = [r['id'] for r in rows if r['ours']]\n"
    "\t\tself.view.custom.theme = (mine or [r['id'] for r in rows] or [''])[0]\n"
    "\t\tself.view.custom.file = 'variables.css'\n"
    "\t\tself.view.custom.nudge = self.view.custom.nudge + 1\n"
    "\texcept Exception as e:\n"
    "\t\tself.view.custom.status = str(e)"
)
# Delete is offered ONLY for a theme made here. A packaged theme's lifecycle
# belongs to the Installer's Remove button, and a stock one is never ours to
# remove -- delete_theme() refuses both, and hiding the button means nobody
# has to press it to find that out.
IS_USER_THEME = "{view.custom.kind} = 'user'"


def _button(name, text, script, primary=False):
    return {
        "type": "ia.input.button", "meta": {"name": name},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"text": text,
                  "style": {"height": "32px", "whiteSpace": "nowrap"}
                  if primary else
                  {"height": "32px", "whiteSpace": "nowrap",
                   "backgroundColor": "var(--containerBackground)",
                   "color": "var(--label)",
                   "borderStyle": "solid", "borderWidth": "1px",
                   "borderColor": "var(--border)"}},
        "events": {"component": {"onActionPerformed": {
            "config": {"script": script}, "scope": "G", "type": "script"}}},
    }


# ---------------------------------------------------------------------------
# THE EDITOR
#
# What the Installer page got right, applied here:
#   - every group of controls has a heading and ONE line saying what it does,
#   - a button sits with the thing it acts on rather than in a shared toolbar,
#   - and the page says what it is before it shows you a workspace.
#
# The three things you can do here are different in kind, so they are three
# places on the page rather than one row of seven buttons:
#   THEME level   pick one, make one, copy one, delete one you made
#   FILE level    open one, save it, put it back
#   REFERENCE     what this theme publishes for a project to build on
# Putting Save next to "Revert to shipped" and a theme dropdown mixes three
# scopes in one strip, which reads as unusable -- hence the separate places.
# ---------------------------------------------------------------------------

def _pane(name, title, hint, children, basis, body_pad="0px", hug=False):
    """A bordered column with a heading and one line of explanation.

    The hint is not decoration. Every pane on this page needed a sentence: a
    file list nobody has been told is clickable, and a token list nobody has
    been told is read-only reference, are both furniture.
    """
    head = [{"type": "ia.display.label", "meta": {"name": "h"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"text": title,
                       "style": {"fontSize": "11px", "fontWeight": 600,
                                 "letterSpacing": "0.06em",
                                 "textTransform": "uppercase",
                                 "color": "var(--label)"}}}]
    if hint:
        head.append({"type": "ia.display.label", "meta": {"name": "hint"},
                     "position": {"grow": 0, "shrink": 0, "basis": "auto"},
                     "props": {"text": hint,
                               "style": {"fontSize": "11.5px",
                                         "lineHeight": "1.45",
                                         "color": "var(--neutral-70)"}}})
    # hug: the pane is as tall as what is in it. A pane given a fixed height
    # is a guess that goes wrong the moment its own caption wraps one more
    # line -- which is how the preview came to have a scrollbar in a box that
    # holds one 96px picture.
    return {
        "type": "ia.container.flex", "meta": {"name": name},
        "position": {"grow": 0 if hug else (1 if basis == "0px" else 0),
                     "shrink": 0 if hug else 1,
                     "basis": "auto" if hug else basis},
        "props": {"direction": "column",
                  "style": {"gap": "0px", "minHeight": "0px",
                            "borderRadius": "4px",
                            "backgroundColor": "var(--container)",
                            "borderStyle": "solid", "borderWidth": "1px",
                            "borderColor": "var(--border)",
                            "overflow": "hidden"}},
        "children": [
            {"type": "ia.container.flex", "meta": {"name": "head"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"direction": "column",
                       "style": {"gap": "3px", "padding": "9px 11px 8px",
                                 "borderBottomStyle": "solid",
                                 "borderBottomWidth": "1px",
                                 "borderBottomColor": "var(--border)"}},
             "children": head},
            {"type": "ia.container.flex", "meta": {"name": "body"},
             # A hugging pane's body must be auto too: at basis 0px there is
             # nothing to give the contents height and the pane renders as a
             # header over an empty box.
             "position": ({"grow": 0, "shrink": 0, "basis": "auto"} if hug
                          else {"grow": 1, "shrink": 1, "basis": "0px"}),
             "props": {"direction": "column",
                       "style": {"gap": "0px", "minHeight": "0px",
                                 "padding": body_pad}},
             "children": children},
        ],
    }


def _cap(name, text, size="12px"):
    return {"type": "ia.display.label", "meta": {"name": name},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {"text": text,
                      "style": {"fontSize": size,
                                "color": "var(--neutral-70)",
                                "whiteSpace": "nowrap"}}}


def _spacer(name="gap"):
    return {"type": "ia.container.flex", "meta": {"name": name},
            "position": {"grow": 1, "shrink": 1, "basis": "0px"},
            "props": {}}


def _theme_bar():
    """Everything that acts on a WHOLE theme, in one labelled row."""
    return {
        "type": "ia.container.flex", "meta": {"name": "themebar"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "row", "alignItems": "center", "wrap": "wrap",
                  "style": {"gap": "9px", "rowGap": "8px",
                            "padding": "10px 12px", "borderRadius": "4px",
                            "backgroundColor": "var(--container)",
                            "borderStyle": "solid", "borderWidth": "1px",
                            "borderColor": "var(--border)"}},
        "children": [
            _cap("cap", "Editing theme"),
            {"type": "ia.input.dropdown", "meta": {"name": "theme"},
             "position": {"grow": 0, "shrink": 0, "basis": "225px"},
             "props": {"allowClearing": False, "showSearch": True,
                       "style": {"height": "32px"}},
             "propConfig": {
                 # NOT expr "1". A constant expression evaluates once, so a
                 # theme you had just made was absent from the list its own
                 # Create had selected -- the picker went blank and the page
                 # stopped saying which theme you were editing. nudge is
                 # bumped by every create, copy and delete.
                 "props.options": {"binding": _expr("{view.custom.nudge}",
                                                    EDITOR_THEME_OPTIONS)},
                 # bidirectional lives INSIDE config or the dropdown never
                 # writes the selection back, silently.
                 "props.value": {"binding": {
                     "type": "property",
                     "config": {"path": "view.custom.theme",
                                "bidirectional": True}}}}},
            # The badge is the answer to "am I allowed to break this?", which
            # is the first thing anyone wants to know on this page.
            {"type": "ia.display.label", "meta": {"name": "kind"},
             "position": {"grow": 0, "shrink": 1, "basis": "auto"},
             "props": {"style": {"fontSize": "12px",
                                 "color": "var(--neutral-70)"}},
             "propConfig": {"props.text": {"binding": _prop(
                 "view.custom.key", EDITOR_KIND_LABEL)}}},
            _spacer(),
            # ONE button. "New theme..." and "Copy this one..." read as
            # alternatives and were not: one gave you a whole theme, the other
            # an empty shell with none of the --st-* vocabulary this page is
            # built around, and the natural first click was the wrong one.
            _button("btn_new", "Make a theme...", EDITOR_START_NEW),
            _only_when(_button("btn_delete", "Delete this theme",
                               EDITOR_DELETE), IS_USER_THEME, layout=True),
        ],
    }


def _make_panel():
    """The name/base row, shown only while making a theme.

    Hidden until asked for. Always on show it is three controls and two buttons
    that most visits never touch, sitting between the theme you picked and the
    file you came to edit.
    """
    return {
        "type": "ia.container.flex", "meta": {"name": "make"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "column",
                  "style": {"gap": "7px", "padding": "11px 12px",
                            "borderRadius": "4px",
                            "backgroundColor": "var(--containerNested)",
                            "borderStyle": "solid", "borderWidth": "1px",
                            "borderColor": "var(--callToAction)"}},
        "children": [
            {"type": "ia.display.label", "meta": {"name": "hint"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"text":
                 "Your theme starts as a copy of whatever you pick, files and "
                 "all, and nothing on the Installer page overwrites it.",
                 "style": {"fontSize": "12.5px", "lineHeight": "1.5",
                           "color": "var(--label)"}}},
            {"type": "ia.container.flex", "meta": {"name": "row"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"direction": "row", "alignItems": "center",
                       "wrap": "wrap", "style": {"gap": "9px",
                                                 "rowGap": "8px"}},
             "children": [
                 _cap("cap", "Call it"),
                 {"type": "ia.input.text-field", "meta": {"name": "new_name"},
                  "position": {"grow": 0, "shrink": 0, "basis": "190px"},
                  # deferUpdates false so the button beside it cannot read a
                  # stale value however fast the click follows the keystroke.
                  "props": {"deferUpdates": False,
                            "placeholder": "ocean-dark",
                            "style": {"height": "32px",
                                      "fontFamily": "'DejaVu Sans Mono', "
                                                    "'Liberation Mono', "
                                                    "Consolas, monospace"}},
                  "propConfig": {"props.text": {"binding": {
                      "type": "property",
                      "config": {"path": "view.custom.new_name",
                                 "bidirectional": True}}}}},
                 _cap("cap2", "starting from"),
                 {"type": "ia.input.dropdown", "meta": {"name": "new_base"},
                  "position": {"grow": 0, "shrink": 1, "basis": "260px"},
                  "props": {"allowClearing": False, "showSearch": True,
                            "style": {"height": "32px"}},
                  "propConfig": {
                      # Re-read on every nudge: a theme you made a minute ago
                      # is a perfectly good thing to start the next one from.
                      "props.options": {"binding": _expr(
                          "{view.custom.nudge}", EDITOR_START_OPTIONS)},
                      "props.value": {"binding": {
                          "type": "property",
                          "config": {"path": "view.custom.new_base",
                                     "bidirectional": True}}}}},
                 _spacer(),
                 _button("btn_cancel", "Cancel", EDITOR_CANCEL),
                 _button("btn_create", "Make it", EDITOR_NEW, primary=True),
             ]},
            # Only when the choice costs something. A bare Ignition theme
            # ships no --st-* tokens at all, so the theme you get has no
            # accent and no card colour -- which is exactly what happened to
            # anyone who pressed the old "New theme..." button first.
            _only_when(
                {"type": "ia.display.label", "meta": {"name": "startwarn"},
                 "position": {"grow": 0, "shrink": 0, "basis": "auto"},
                 "props": {"style": {"fontSize": "12px", "lineHeight": "1.45",
                                     "color": "var(--callToAction)"}},
                 "propConfig": {"props.text": {"binding": _prop(
                     "view.custom.startwarn")}}},
                "{view.custom.startwarn} != ''", layout=True),
        ],
    }


def _editor_pane():
    """The file you have open, with the buttons that act on THAT FILE.

    Save lives inside the pane whose contents it writes, rather than a
    toolbar beside a theme dropdown and a delete -- the same rule the
    Installer's cards follow.
    """
    actions = {
        "type": "ia.container.flex", "meta": {"name": "fileactions"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "row", "alignItems": "center", "wrap": "wrap",
                  "style": {"gap": "8px", "rowGap": "8px",
                            "padding": "8px 10px",
                            "borderBottomStyle": "solid",
                            "borderBottomWidth": "1px",
                            "borderBottomColor": "var(--border)"}},
        "children": [
            {"type": "ia.display.label", "meta": {"name": "openfile"},
             "position": {"grow": 0, "shrink": 1, "basis": "auto"},
             "props": {"style": {
                 "fontSize": "13px", "fontWeight": 600, "color": "var(--label)",
                 "fontFamily": "'DejaVu Sans Mono', 'Liberation Mono', "
                               "Consolas, monospace"}},
             "propConfig": {"props.text": {"binding": {
                 "type": "expr", "config": {"expression":
                     "if({view.custom.file} = '', "
                     "'-- pick a file on the left --', "
                     "{view.custom.file})"}}}}},
            _spacer(),
            _button("btn_save", "Save", EDITOR_SAVE, primary=True),
            _button("btn_revert", "Undo my changes", EDITOR_REVERT),
            _button("btn_scan", "Re-scan", EDITOR_REFRESH),
        ],
    }
    return _pane(
        "editorpane", "The file",
        "Saving writes it and runs a config scan, which is what makes the "
        "gateway use it. Undo my changes puts back what the installer ships "
        "for this one file.",
        [actions, _raw_editor()], "0px")


def _locked_banner():
    """Shown instead of an editor for a theme that is not yours.

    This is the whole repositioning in one component. The generated files say
    DO NOT EDIT BY HAND and mean it -- Install overwrites them -- so rather
    than inviting an edit that disappears, the page says why and offers the
    copy that makes it stick.
    """
    return {
        "type": "ia.container.flex", "meta": {"name": "locked"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "row", "alignItems": "center", "wrap": "wrap",
                  "style": {"gap": "12px", "rowGap": "8px",
                            "padding": "12px 14px", "borderRadius": "4px",
                            "backgroundColor": "var(--containerNested)",
                            "borderStyle": "solid", "borderWidth": "1px",
                            "borderColor": "var(--border)"}},
        "children": [
            {"type": "ia.display.label", "meta": {"name": "why"},
             "position": {"grow": 1, "shrink": 1, "basis": "0px"},
             "props": {"style": {"fontSize": "12.5px", "lineHeight": "1.5",
                                 "color": "var(--label)"}},
             "propConfig": {"props.text": {"binding": _prop(
                 "view.custom.key", EDITOR_LOCKED)}}},
            _button("btn_copyme", "Make my own copy", EDITOR_COPY_THIS,
                    primary=True),
        ],
    }


def _preview_pane():
    """The mini screen, painted from the LIVE stylesheet.

    Tuning colours without seeing the result is guessing, and this is the one
    thing the Installer's build-time thumbnails cannot do -- they show what the
    repo ships, not what this gateway is serving after your last save.
    """
    return _pane(
        "preview", "Preview",
        # Three sentences in a 352px column is five lines of caption above a
        # 96px picture. One sentence; Refresh explains itself.
        "This theme's own colours. Repaints on every save.",
        [{"type": "ia.display.label", "meta": {"name": "shot"},
          # Scales instead of scrolling. A fixed 320x96 plus its margins was a
          # number that fitted one window height; backgroundSize contain keeps
          # the picture's shape at whatever height the rail can spare.
          "position": {"grow": 0, "shrink": 1, "basis": "auto"},
          "props": {"text": "",
                    # aspect-ratio does the scaling: the picture is 200x60, so
                    # its height follows the rail's width and it is never
                    # letterboxed inside its own box. grow 1 did not scale it
                    # at all -- the pane hugs, so there was nothing to grow
                    # into and it sat on its min-height at every window size.
                    "style": {"aspectRatio": "200 / 60", "width": "auto",
                              "height": "auto", "maxHeight": "96px",
                              "margin": "8px",
                              "backgroundRepeat": "no-repeat",
                              "backgroundPosition": "center",
                              "backgroundSize": "contain",
                              "borderRadius": "3px"}},
          "propConfig": {"props.style.backgroundImage": {"binding": _prop(
              "view.custom.key", EDITOR_PREVIEW)}}},
         {"type": "ia.container.flex", "meta": {"name": "prefresh"},
          "position": {"grow": 0, "shrink": 0, "basis": "auto"},
          "props": {"direction": "row",
                    "style": {"padding": "0 10px 10px", "gap": "8px"}},
          "children": [_button("btn_refresh", "Refresh", EDITOR_REFRESH)]}],
        # No height at all now: hug=True sizes it to the picture and the
        # button, so it cannot scroll and cannot leave a gap, whatever the
        # caption does at whatever width.
        "auto", hug=True)


def _swatch_chip(index):
    """One clickable colour from the theme's own palette.

    Perspective cannot generate components from a list, so the row is a fixed
    number of chips at fixed indexes and themepack.swatches() pads its answer
    to match. A chip with nothing behind it takes its space back rather than
    leaving a hole in the row.
    """
    path = "view.custom.swatches[%d]" % index
    chip = {
        "type": "ia.display.label", "meta": {"name": "sw%d" % index},
        # basis, not a style width: _only_when(layout=True) moves this to the
        # wrapper, where it is the main-axis size the chip actually gets.
        "position": {"grow": 0, "shrink": 0, "basis": "22px"},
        "props": {"text": "", "style": {
            "width": "100%", "height": "22px", "borderRadius": "3px",
            "borderStyle": "solid", "borderWidth": "1px",
            "borderColor": "var(--border)", "cursor": "pointer"}},
        "propConfig": {
            "props.style.backgroundColor": {"binding": _prop(path)},
            "meta.tooltip.text": {"binding": _prop(path)}},
        # DOM event, not component: onClick under events.component is
        # accepted, saved and never fires -- the same trap the page tabs hit.
        "events": {"dom": {"onClick": {
            "config": {"script": _pick_swatch(index)},
            "scope": "G", "type": "script"}}},
    }
    chip["meta"]["tooltip"] = {"enabled": True, "text": ""}
    _keyboard_click(chip)
    return _only_when(chip, "{%s} != ''" % path, layout=True)


def _colour_pane():
    """The colours, and the one you picked with a field to change it.

    A table plus an edit strip, not an in-cell editor: Perspective's Table
    never opened one for a column marked editable (its _isCellEditable gate is
    reached through prop shapes not in any documentation we have), and a named
    field leaves the token you are changing on screen while you change it.
    """
    table = _table("tokens", [
        # Two rules here, both learned the hard way.
        #
        # No empty header titles: an empty one falls back to the FIELD NAME,
        # which is how a 46px swatch column came out labelled "swatc".
        #
        # And the columns must FILL the row. onRowClick is fired from
        # handleBodyClick via getCellInfo(e.target), which needs a .tc under
        # the pointer -- with every column given a fixed width the row was
        # 530px of cells in a 1100px pane, so a click anywhere right of the
        # last column hit dead space and silently did nothing. The Token
        # column takes the slack.
        _col("group", "Affects", 150, True),
        _col("name", "Token", 210, True),
        # The slack column, and the one that answers "what IS this". Kept
        # here rather than in a separate read-only pane, which would only
        # repeat the same --st-* names with their resolved values -- the
        # sentence is the part that is not a duplicate of the token list,
        # and it belongs beside the value you are about to change.
        _col("what", "What it does"),
        _col("swatch", "Colour", 58, True),
        _col("value", "Value", 130, True),
    ], "view.custom.tokens")
    table["props"]["style"] = {}
    table["events"] = {"component": {"onRowClick": {
        "config": {"script": EDITOR_PICK_TOKEN}, "scope": "G",
        "type": "script"}}}
    strip = {
        "type": "ia.container.flex", "meta": {"name": "edit"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        # The border moved out to the block below, so the strip and the
        # swatches under it read as one thing rather than two.
        "props": {"direction": "row", "alignItems": "center", "wrap": "wrap",
                  "style": {"gap": "9px", "rowGap": "8px",
                            "padding": "9px 10px 0px"}},
        "children": [
            {"type": "ia.display.label", "meta": {"name": "sel"},
             "position": {"grow": 0, "shrink": 1, "basis": "auto"},
             "props": {"style": {
                 "fontSize": "12.5px", "fontWeight": 600,
                 "color": "var(--label)", "minWidth": "180px",
                 "fontFamily": "'DejaVu Sans Mono', 'Liberation Mono', "
                               "Consolas, monospace"}},
             "propConfig": {"props.text": {"binding": {
                 "type": "expr", "config": {"expression":
                     "if({view.custom.sel_name} = '', "
                     "'-- pick a value above --', "
                     "{view.custom.sel_name})"}}}}},
            {"type": "ia.input.text-field", "meta": {"name": "val"},
             "position": {"grow": 0, "shrink": 0, "basis": "170px"},
             # deferUpdates false so Save cannot read a stale value however
             # fast the click follows the last keystroke.
             "props": {"deferUpdates": False, "placeholder": "#3b4252",
                       "style": {"height": "32px",
                                 "fontFamily": "'DejaVu Sans Mono', "
                                               "'Liberation Mono', Consolas, "
                                               "monospace"}},
             "propConfig": {"props.text": {"binding": {
                 "type": "property",
                 "config": {"path": "view.custom.sel_value",
                            "bidirectional": True}}}}},
            # The swatch of what is in the box, so a typo shows before it is
            # saved rather than after the page repaints.
            {"type": "ia.display.label", "meta": {"name": "chip"},
             "position": {"grow": 0, "shrink": 0, "basis": "auto"},
             "props": {"text": "",
                       "style": {"width": "32px", "height": "32px",
                                 "borderRadius": "3px",
                                 "borderStyle": "solid", "borderWidth": "1px",
                                 "borderColor": "var(--border)"}},
             # sel_ok, not sel_value: a value CSS cannot parse leaves the
             # chip painted in the last one that worked, so the only visual
             # confirmation on the page said "fine" for a broken value.
             "propConfig": {"props.style.backgroundColor": {"binding": _prop(
                 "view.custom.sel_ok")}}},
            # Says what is wrong BEFORE you press Save, and Save refuses it
            # afterwards -- the check is in set_any_token, not here, so the
            # same rule holds for anything else that writes a token.
            _only_when(
                {"type": "ia.display.label", "meta": {"name": "warn"},
                 "position": {"grow": 1, "shrink": 1, "basis": "0px"},
                 "props": {"style": {"fontSize": "12px", "lineHeight": "1.4",
                                     "color": "var(--callToAction)"}},
                 "propConfig": {"props.text": {"binding": _prop(
                     "view.custom.warn")}}},
                "{view.custom.warn} != ''", layout=True),
            _spacer(),
            # One level of undo, offered only when there is something to undo.
            # Nobody remembers the hex they just overwrote.
            _only_when(_bound_button(
                "btn_undo", EDITOR_UNDO,
                "'Undo ' + {view.custom.undo_name}"),
                "{view.custom.undo_name} != ''", layout=True),
            _button("btn_save_token", "Save", EDITOR_SAVE_TOKEN,
                    primary=True),
        ],
    }
    # The colours the theme already holds, one click each. Perspective has no
    # colour picker to reach for -- its form declares a color-picker control
    # with no factory behind it, so a form using one is a Component Error --
    # and a palette of what the theme already uses is the better offer anyway:
    # those are the colours somebody chose to sit together, where a free
    # picker's whole range mostly is not.
    palette = {
        "type": "ia.container.flex", "meta": {"name": "palette"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "row", "alignItems": "center", "wrap": "wrap",
                  "style": {"gap": "6px", "rowGap": "6px",
                            "padding": "8px 10px 9px"}},
        "children": ([_cap("palcap", "Already in this theme")]
                     + [_swatch_chip(i) for i in range(SWATCH_COUNT)]),
    }
    editblock = {
        "type": "ia.container.flex", "meta": {"name": "editblock"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "column",
                  "style": {"borderTopStyle": "solid",
                            "borderTopWidth": "1px",
                            "borderTopColor": "var(--border)"}},
        "children": [strip, palette],
    }
    # The search box. 150 values is ten screens, and every visit is after ONE
    # of them; scrolling for it was the friction, not the editing.
    find = {
        "type": "ia.container.flex", "meta": {"name": "find"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "row", "alignItems": "center",
                  "style": {"gap": "9px", "padding": "8px 10px",
                            "borderBottomStyle": "solid",
                            "borderBottomWidth": "1px",
                            "borderBottomColor": "var(--border)"}},
        "children": [
            _cap("findcap", "Find"),
            {"type": "ia.input.text-field", "meta": {"name": "filter"},
             "position": {"grow": 0, "shrink": 1, "basis": "260px"},
             "props": {"deferUpdates": False,
                       "placeholder": "accent, button, #ffffff, table...",
                       "style": {"height": "30px"}},
             "propConfig": {"props.text": {"binding": {
                 "type": "property",
                 "config": {"path": "view.custom.filter",
                            "bidirectional": True}}}}},
            _cap("findhint", "name, description, group or value"),
        ],
    }
    pane = _pane(
        "colours", "This theme's values",
        "Mostly colours, and a few sizes, grouped by what they affect. Click "
        "one, change it, Save -- each save writes the file and runs the scan "
        "that makes the gateway use it.",
        [find, table, _only_when(editblock, IS_EDITABLE, layout=True)], "0px")
    # The grower again, now that there are five columns and the widest is a
    # sentence: a column taking a whole row's slack needs something worth
    # reading in that space, not a narrower table.
    pane["position"] = {"grow": 1, "shrink": 1, "basis": "0px"}
    pane["props"]["style"]["minWidth"] = "560px"
    return pane


def _raw_pane():
    """The escape hatch. Structural edits -- a new rule, an @import -- are not
    colours, and a theme of your own is yours to break."""
    actions = {
        "type": "ia.container.flex", "meta": {"name": "fileactions"},
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"direction": "row", "alignItems": "center", "wrap": "wrap",
                  "style": {"gap": "8px", "rowGap": "8px",
                            "padding": "8px 10px",
                            "borderBottomStyle": "solid",
                            "borderBottomWidth": "1px",
                            "borderBottomColor": "var(--border)"}},
        "children": [
            {"type": "ia.input.dropdown", "meta": {"name": "file"},
             "position": {"grow": 0, "shrink": 0, "basis": "190px"},
             "props": {"allowClearing": False, "showSearch": False,
                       "style": {"height": "32px"}},
             "propConfig": {
                 "props.options": {"binding": _prop("view.custom.key",
                                                    EDITOR_FILE_OPTIONS)},
                 "props.value": {"binding": {
                     "type": "property",
                     "config": {"path": "view.custom.file",
                                "bidirectional": True}}}}},
            _spacer(),
            _button("btn_save", "Save file", EDITOR_SAVE, primary=True),
            _button("btn_scan", "Re-scan", EDITOR_REFRESH),
        ],
    }
    return _pane(
        "rawpane", "Raw files",
        "The theme's files as they are on disk. For structural changes -- a "
        "rule of your own, an extra import -- rather than colours.",
        [actions, _raw_editor()], "0px")


def build_editor_view_json(themes, version):
    """Page: copy one of ours, then tune the copy."""
    return {
        "custom": {"theme": "", "file": "variables.css", "key": "",
                   "filter": "",
                   "text": "", "status": "", "nudge": 0, "kind": "",
                   "tokens": [], "about": "", "swatches": [],
                   "sel_name": "", "sel_value": "", "sel_ok": "",
                   "warn": "", "startwarn": "",
                   "undo_name": "", "undo_value": "",
                   "raw": False, "making": "", "new_name": "",
                   "new_base": ""},
        "propConfig": {
            "custom.theme": {"binding": _expr("1", EDITOR_FIRST_THEME)},
            # One key for everything that depends on the selection, and nudge
            # in it so a save re-reads from disk rather than trusting the
            # buffer. The whole path goes INSIDE the braces.
            "custom.key": {"binding": {"type": "expr", "config": {
                "expression": "{view.custom.theme} + '|' + "
                              "{view.custom.file} + '|' + "
                              "{view.custom.nudge} + '|' + "
                              "{view.custom.filter}"}}},
            "custom.kind": {"binding": _prop("view.custom.key", EDITOR_KIND)},
            "custom.tokens": {"binding": _prop("view.custom.key",
                                               EDITOR_TOKEN_ROWS)},
            # Off the same key as everything else, so a save re-reads the
            # palette too: change a colour and the chip for the old one goes.
            "custom.swatches": {"binding": _prop("view.custom.key",
                                                 EDITOR_SWATCHES)},
            "custom.text": {"binding": _prop("view.custom.key", EDITOR_TEXT)},
            "custom.about": {"binding": _prop("view.custom.key",
                                              EDITOR_ABOUT)},
            # Live, as you type: the chip shows the colour only when the
            # value IS one, and the line beside it says so when it is not --
            # otherwise the one visual confirmation on the page would keep
            # painting the last valid colour and say "fine" for a value that
            # is not.
            "custom.startwarn": {"binding": _prop("view.custom.new_base",
                                                  EDITOR_START_WARNING)},
            "custom.sel_ok": {"binding": _prop("view.custom.sel_value",
                                               EDITOR_SEL_OK)},
            "custom.warn": {"binding": {
                "type": "expr", "config": {"expression":
                    "{view.custom.sel_name} + '|' + {view.custom.sel_value}"},
                "transforms": [{"type": "script", "code": EDITOR_WARN}]}},
        },
        "params": {},
        "root": {
            "type": "ia.container.flex", "meta": {"name": "root"},
            "props": {"direction": "column",
                      "style": {"padding": PAGE_PADDING, "gap": "10px",
                                "height": "100%", "overflow": "hidden",
                                "backgroundColor": "var(--containerRoot)"}},
            "children": [
                _nav("Customise", version, "{view.custom.nudge}"),
                _prose("sub",
                       "Make a theme of your own: copy one of the ten, then "
                       "change its colours here. The ten themselves are "
                       "generated from the repo and Install overwrites them, "
                       "so they are read-only on this page -- a copy is yours "
                       "and nothing overwrites it.",
                       size="12.5px", colour="var(--neutral-70)"),
                _theme_bar(),
                _only_when(_make_panel(), "{view.custom.making} != ''",
                           layout=True),
                _only_when(_locked_banner(), IS_LOCKED, layout=True),
                # The status line is the page's only feedback and every button
                # writes to it, so it gets a row rather than competing for
                # space in a toolbar.
                {"type": "ia.display.label", "meta": {"name": "status"},
                 "position": {"grow": 0, "shrink": 0, "basis": "auto"},
                 "props": {"style": {"fontSize": "12px", "minHeight": "15px",
                                     "color": "var(--callToAction)"}},
                 "propConfig": {"props.text": {"binding": _prop(
                     "view.custom.status")}}},

                # This row is the ONE grower on the page.
                {"type": "ia.container.flex", "meta": {"name": "panes"},
                 "position": {"grow": 1, "shrink": 1, "basis": "0px"},
                 "props": {"direction": "row",
                           "style": {"gap": "10px", "minHeight": "0px"}},
                 "children": [
                     _only_when(_colour_pane(), SHOW_TOKENS, layout=True),
                     _only_when(_raw_pane(), SHOW_RAW, layout=True),
                     {"type": "ia.container.flex", "meta": {"name": "previewcol"},
                      "position": {"grow": 0, "shrink": 0, "basis": "352px"},
                      "props": {"direction": "column",
                                "style": {"gap": "10px", "minHeight": "0px"}},
                      "children": [
                          _preview_pane(),
                          # The classes live HERE, not under the token table.
                          # They are single short strings, so they read fine
                          # in a 352px rail -- and stacking them under the
                          # preview is what fills the 380px of dead space the
                          # preview left below itself. The token table, which
                          # is three columns, keeps the wide middle.
                          _only_when(_about_pane(),
                                     "{view.custom.kind} != ''", layout=True),
                      ]},
                 ]},
                # The escape hatch is a toggle, not a tab: most visits change a
                # colour and never want a text box.
                _only_when(
                    {"type": "ia.container.flex", "meta": {"name": "advanced"},
                     "position": {"grow": 0, "shrink": 0, "basis": "auto"},
                     "props": {"direction": "row", "alignItems": "center",
                               "style": {"gap": "10px"}},
                     "children": [
                         # Its own label is the only thing telling you which
                         # mode you are in and which way the button goes.
                         _bound_button(
                             "btn_raw", EDITOR_TOGGLE_RAW,
                             "if({view.custom.raw}, "
                             "'Back to the colour list', "
                             "'Advanced: edit the files directly')"),
                         _bound_cap(
                             "rawhint",
                             "if({view.custom.raw}, "
                             "'You are editing the file itself. Colours are "
                             "easier to change in the list.', "
                             "'Colours are easier to change in the list "
                             "above; this is for structural edits.')"),
                     ]},
                    IS_EDITABLE, layout=True),
            ],
        },
    }



def _pane_head(name, text):
    return {"type": "ia.display.label", "meta": {"name": name},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {"text": text,
                      "style": {"fontSize": "11px", "fontWeight": 600,
                                "letterSpacing": "0.06em",
                                "textTransform": "uppercase",
                                "color": "var(--neutral-70)",
                                "padding": "9px 10px 5px",
                                "borderTopStyle": "solid",
                                "borderTopWidth": "1px",
                                "borderTopColor": "var(--border)"}}}


def _file_rail():
    table = _table("files", [_col("name", "File")], "view.custom.files")
    table["props"]["style"] = {}
    table["events"] = {"component": {"onRowClick": {
        "config": {"script": EDITOR_PICK_FILE}, "scope": "G",
        "type": "script"}}}
    return table


def _about_pane():
    """Three facts about the theme, one line each.

    This was a list of the 69 st/... class names. Every one of the ten ships
    the SAME 69 -- measured, not assumed -- so per theme it answered "does
    this carry the contract" with a scroll, and told you nothing about the
    theme you had open. One line says it; the names belong in the README,
    where someone building a project would look for them.
    """
    # Lines in a label, not rows in a table. Four short facts in a table cost
    # a 30px header band and 30px a row -- 212px for 70px of text, and a
    # scrollbar on the rail at laptop height.
    body = {"type": "ia.display.label", "meta": {"name": "about"},
            "position": {"grow": 0, "shrink": 0, "basis": "auto"},
            "props": {"style": {"fontSize": "12px", "lineHeight": "1.5",
                                "whiteSpace": "pre-line",
                                "padding": "7px 11px 8px",
                                "color": "var(--label)"}},
            "propConfig": {"props.text": {"binding": _prop(
                "view.custom.about")}}}
    return _pane("about_pane", "About this theme", "", [body], "auto",
                 hug=True)


def _raw_editor():
    return {
        "type": "ia.input.text-area", "meta": {"name": "raw"},
        "position": {"grow": 1, "shrink": 1, "basis": "0px"},
        "props": {"style": {
            # ui-monospace resolves to a PROPORTIONAL face on this platform;
            # name real families. Never set -webkit-font-smoothing.
            "fontFamily": "'DejaVu Sans Mono', 'Liberation Mono', Consolas, monospace",
            "fontSize": "12.5px", "lineHeight": "1.55",
            "whiteSpace": "pre", "tabSize": "2",
            "border": "none", "borderRadius": "0px",
            "padding": "10px 12px",
            "backgroundColor": "var(--container)",
            # A flex item's min-height defaults to its CONTENT, so a long file
            # beats its own flex-basis and pushes the box off the page. Zero
            # minimum, and the overflow scrolls inside the box.
            "minHeight": "0", "overflow": "auto"}},
        "propConfig": {"props.text": {"binding": {
            "type": "property",
            "config": {"path": "view.custom.text", "bidirectional": True}}}},
    }


def _only_when(node, expression, layout=False):
    """Hide a component, and with layout=True take its SPACE back too.

    meta.visible alone only adds component-meta-hidden, which stops a component
    being seen and leaves it in the flex layout. Binding display fixes that,
    but most components ignore style.display on their own root -- measured on
    8.3.8, a table stayed 297px tall and a label stayed 34px with the binding
    applied and no error. A flex container honours it, so layout=True wraps
    whatever it is given rather than trusting the component to obey.
    """
    visible = {"binding": {"type": "expr", "config": {"expression": expression}}}
    if not layout:
        node.setdefault("propConfig", {})["meta.visible"] = visible
        return node
    # The wrapper INHERITS the child's position and the child then fills it.
    # position.basis is the MAIN-AXIS size, so a child with basis 150px left
    # inside a column wrapper is asking for 150px of HEIGHT: the "built on"
    # dropdown rendered as a tall black box until the position moved out here.
    outer = dict(node.get("position") or {"grow": 0, "shrink": 0,
                                          "basis": "auto"})
    node["position"] = {"grow": 1, "shrink": 1, "basis": "auto"}
    return {
        "type": "ia.container.flex",
        "meta": {"name": node["meta"]["name"] + "_wrap"},
        "position": outer,
        # A ROW wrapper, and the child fills it on the cross axis rather than
        # being given a main-axis size of its own. A column wrapper broke both
        # ways round: with the child's basis left on it the "built on" dropdown
        # asked for 150px of HEIGHT and rendered as a tall black box, and with
        # the child set to grow the wrapper had no intrinsic height and
        # collapsed to 2px.
        "props": {"direction": "row", "style": {}},
        "propConfig": {
            "meta.visible": visible,
            "props.style.display": {"binding": {"type": "expr", "config": {
                "expression": "if(%s, 'flex', 'none')" % expression}}},
        },
        "children": [node],
    }



# ---------------------------------------------------------------------------
# Import page. All the checking is themepack.check_import(); this lays out
# the upload, the verdict and the findings, bound to view.custom.state, which
# themepack.import_view() fills with plain strings.
# ---------------------------------------------------------------------------

_IMPORT_TRY = (
    "\tfrom java.lang import Throwable\n"
    "\timport themepack\n"
    "\ttry:\n"
    "%s"
    "\texcept (Exception, Throwable) as e:\n"
    "\t\tself.view.custom.state = themepack.import_view(None, str(e))\n"
)


def _import_script(body):
    return _IMPORT_TRY % "".join("\t\t" + line + "\n" for line in body)


def _bind(node, prop, path):
    node.setdefault("propConfig", {})[prop] = {"binding": {
        "type": "property", "config": {"path": path}}}
    return node


def build_import_view_json(version):
    # A new zip always starts from its own name. Reusing the field let the
    # previous upload's name install a different theme under it; renaming is
    # what Check again is for.
    received = _import_script([
        "data = themepack.import_bytes(event.file.getBytes())",
        "self.view.custom.zipName = event.file.name",
        "report = themepack.stage_import(data, event.file.name, None)",
        "self.view.custom.state = themepack.import_view(report)",
        "self.view.custom.name = report.get('id') or ''",
    ])
    recheck = _import_script([
        "if not self.view.custom.state.token:",
        "\treturn",
        "report = themepack.recheck_import(self.view.custom.state.token,",
        "\tself.view.custom.zipName, (self.view.custom.name or '').strip() or None)",
        "self.view.custom.state = themepack.import_view(report)",
    ])
    install = _import_script([
        "themepack.install_import(self.view.custom.state.token,",
        "\tself.view.custom.zipName, (self.view.custom.name or '').strip() or None)",
        "theme = self.view.custom.state.id",
        "self.view.custom.state = {'ok': False, 'token': '', 'id': theme,",
        "\t'preview': self.view.custom.state.preview, 'details': '', 'findings': '',",
        "\t'verdict': \"Installed as '%s'. It is on the Installer tab and in every \"",
        "\t\t\"project's Theme menu.\" % theme}",
        "self.view.custom.name = ''",
        "self.view.custom.done += 1",
    ])
    upload = {
        "type": "ia.input.fileupload", "meta": {"name": "upload"},
        "position": {"grow": 1, "shrink": 1, "basis": "0px"},
        "props": {"supportedFileTypes": ["zip"], "fileSizeLimit": 2,
                  "maxUploads": 1,
                  "style": {"height": "166px"}},
        "events": {"component": {"onFileReceived": {
            "type": "script", "scope": "G",
            "config": {"script": received}}}},
    }
    name_field = {
        "type": "ia.input.text-field", "meta": {"name": "name"},
        "position": {"grow": 0, "shrink": 0, "basis": "32px"},
        "props": {"placeholder": "theme id, e.g. ocean-dark",
                  "style": {"height": "32px"}},
        "propConfig": {"props.text": {"binding": {
            "type": "property",
            "config": {"path": "view.custom.name", "bidirectional": True}}}},
    }
    install_btn = _button("install_btn", "Install", install, primary=True)
    _bind(install_btn, "props.enabled", "view.custom.state.ok")
    name_col = _flex("name_col", [
        _label("name_l", "Install as", size="12px", colour="var(--neutral-70)"),
        name_field,
        {"type": "ia.container.flex", "meta": {"name": "name_row"},
         "position": {"grow": 0, "shrink": 0, "basis": "auto"},
         "props": {"direction": "row", "style": {"gap": "8px"}},
         "children": [_button("recheck_btn", "Check again", recheck),
                      install_btn]},
    ], basis="220px", style={"gap": "6px"})
    verdict = _bind(_label("verdict", "", size="14px", weight=600),
                    "props.text", "view.custom.state.verdict")
    details = _bind(_prose("details", "", size="12px", colour="var(--neutral-70)"),
                    "props.text", "view.custom.state.details")
    preview = _bind({
        "type": "ia.display.image", "meta": {"name": "preview"},
        "position": {"grow": 0, "shrink": 0, "basis": "170px"},
        "props": {"fit": {"mode": "fill"}, "style": {"height": "51px",
                  "borderRadius": "3px"}}}, "props.source",
        "view.custom.state.preview")
    # No picture for a refused zip; an empty source draws a broken-image icon.
    preview["propConfig"]["position.display"] = {"binding": {
        "type": "expr", "config": {
            "expression": "len({view.custom.state.preview}) > 0"}}}
    findings = _bind({
        "type": "ia.display.label", "meta": {"name": "findings"},
        # Sized to its lines, which import_view() caps: a label centres
        # text that overflows it, which cut the first and last lines in half.
        "position": {"grow": 0, "shrink": 0, "basis": "auto"},
        "props": {"style": {"fontSize": "12px", "lineHeight": "1.5",
                            "whiteSpace": "pre-wrap",
                            "color": "var(--label)"}}},
        "props.text", "view.custom.state.findings")
    root = _flex("root", [
        _nav("Import", version, "{view.custom.done}"),
        _prose("intro",
               "A zip holding one theme: its index.css and the .css files "
               "that imports. Checked before anything is written. Anything "
               "that fetches from elsewhere, runs code or leaves its own "
               "folder is refused; low contrast and other quality problems "
               "are listed for you to decide.",
               size="12.5px", colour="var(--neutral-70)"),
        {"type": "ia.container.flex", "meta": {"name": "top"},
         "position": {"grow": 0, "shrink": 0, "basis": "auto"},
         "props": {"direction": "row", "style": {"gap": "14px"}},
         "children": [upload, name_col]},
        verdict,
        {"type": "ia.container.flex", "meta": {"name": "mid"},
         "position": {"grow": 0, "shrink": 0, "basis": "auto"},
         "props": {"direction": "row", "alignItems": "center",
                   "style": {"gap": "12px"}},
         "children": [preview, dict(details, position={
             "grow": 1, "shrink": 1, "basis": "0px"})]},
        findings,
    ], style={"gap": "12px", "padding": PAGE_PADDING, "height": "100%",
              "backgroundColor": "var(--containerRoot)"})
    return {
        "custom": {"name": "", "zipName": "", "done": 0,
                   "state": {"ok": False, "token": "", "id": "",
                             "preview": "", "details": "", "findings": "",
                             "verdict": "Pick a .zip, or drop one on the box."}},
        "params": {},
        "root": root,
    }


def main():
    version = read_version()
    themes = read_themes()

    for name in GENERATED:
        path = os.path.join(PROJECT_DIR, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.isfile(path):
            os.remove(path)

    if not os.path.isfile(INSIGHT_SRC):
        print("build_manager.py: %s not found -- the insight functions are "
              "hand-authored, not generated" % os.path.relpath(INSIGHT_SRC, HERE))
        sys.exit(1)

    if not os.path.isfile(EDITOR_SRC):
        print("build_manager.py: %s not found -- the editor functions are "
              "hand-authored, not generated" % os.path.relpath(EDITOR_SRC, HERE))
        sys.exit(1)

    for src in (SELECTOR_POPUP_SRC, THEME_DROPDOWN_SRC):
        if not os.path.isfile(src):
            print("build_manager.py: %s not found -- the theme-switcher views "
                  "are hand-authored, not generated; see "
                  "tools/themes/selector-popup/README.md" % os.path.relpath(src, HERE))
            sys.exit(1)

    script_dir = os.path.join(PROJECT_DIR, "ignition", "script-python", "themepack")
    persp_dir = os.path.join(PROJECT_DIR, "com.inductiveautomation.perspective")
    session_props_dir = os.path.join(persp_dir, "session-props")
    page_config_dir = os.path.join(persp_dir, "page-config")
    stylesheet_dir = os.path.join(persp_dir, "stylesheet")
    view_dir = os.path.join(persp_dir, "views", "Installer")
    editor_dir = os.path.join(persp_dir, "views", "Editor")
    popup_dir = os.path.join(persp_dir, "views", "SelectorPopup")
    dropdown_dir = os.path.join(persp_dir, "views", "ThemeDropdown")
    import_dir = os.path.join(persp_dir, "views", "Import")

    for d in (script_dir, session_props_dir, page_config_dir, stylesheet_dir,
              view_dir, popup_dir, dropdown_dir, editor_dir, import_dir):
        os.makedirs(d)

    # project.json
    write_json(os.path.join(PROJECT_DIR, "project.json"), build_project_json(version, themes))

    # ignition/script-python/themepack/
    write_text(os.path.join(script_dir, "code.py"), build_themepack_code(themes, version))
    write_json(os.path.join(script_dir, "resource.json"), resource_json(["code.py"]))

    # session-props -- hide the app bar (standing rule for every project) and
    # run on Ignition's STOCK dark theme.
    #
    # Setting no theme at all would let the project inherit whatever the
    # gateway session had, which does not survive the preview pages: they
    # paint every theme in literal colours, so the surface behind them has
    # to be a known, stable backdrop or the same gallery reads differently on
    # every gateway. "dark" is also the one theme guaranteed to exist -- it
    # lives inside the Perspective module, so it is present before this project
    # has installed anything and cannot be removed by uninstalling.
    write_json(os.path.join(session_props_dir, "props.json"), {
        "custom": {},
        "props": {
            "appBar": {"togglePosition": "hidden"},
            "theme": "dark",
        },
        "propConfig": {},
    })
    write_json(os.path.join(session_props_dir, "resource.json"), resource_json(["props.json"]))

    # page-config -- "/" -> Installer
    write_json(os.path.join(page_config_dir, "config.json"), {
        "pages": {
            "/": {"title": TITLE, "viewPath": "Installer"},
            "/editor": {"title": "Customise", "viewPath": "Editor"},
            "/import": {"title": "Import", "viewPath": "Import"},
        }
    })
    write_json(os.path.join(page_config_dir, "resource.json"), resource_json(["config.json"]))

    # stylesheet -- color-scheme (standing workspace rule, every Perspective
    # project) + the app-bar CSS fallback the session prop alone doesn't cover
    # on Maker Edition (feedback-hide-perspective-app-bar).
    stylesheet_css = (
        "/* GENERATED by build_manager.py -- DO NOT EDIT.\n"
        " * Workspace cross-cutting rules: every Perspective project declares\n"
        " * color-scheme, and the app bar is always hidden.\n"
        " *\n"
        " * BOTH, not dark. session.props.theme defaults to Ignition's stock\n"
        " * dark, but the tab strip carries a switcher, so a reader can be on a\n"
        " * light theme at any moment -- and this file was briefly `dark` on the\n"
        " * strength of the default alone, which would have told Chrome the\n"
        " * wrong thing the instant anyone picked Leather Light. The rule is to\n"
        " * declare what the page is ACTUALLY painted in; where that can change,\n"
        " * the honest declaration is both. */\n"
        "html {\n"
        "  color-scheme: light dark;\n"
        "}\n"
        "\n"
        "/* The installer usually runs on a stock theme, whose focus outline is\n"
        " * 1px and can fall under 3:1. The Ignition Themes supply a measured\n"
        " * ring; the heading ink stands in on a stock theme. */\n"
        ":focus-visible,\n"
        ".ia_dropdown.ia_dropdown--focused {\n"
        "  outline: 2px solid var(--a11y-focus-ring, var(--neutral-100));\n"
        "  outline-offset: 1px;\n"
        "}\n"
        ".ReactVirtualized__Grid:focus-visible {\n"
        "  outline: 2px solid var(--a11y-focus-ring, var(--neutral-100)) !important;\n"
        "  outline-offset: -2px;\n"
        "}\n"
        "\n"
        ".app-bar {\n"
        "  display: none !important;\n"
        "}\n"
        "\n"
        "/* The Installer's tick column is display-only (a row click toggles it),\n"
        " * so Perspective draws it disabled. Draw it as a live checkbox. */\n"
        ".ia_table__cell[data-column-id=\"pick\"] .ia_checkbox--disabled {\n"
        "  cursor: pointer;\n"
        "}\n"
        ".ia_table__cell[data-column-id=\"pick\"] .ia_checkbox__uncheckedIcon--disabled {\n"
        "  fill: var(--checkbox--unchecked);\n"
        "  color: var(--checkbox--unchecked);\n"
        "}\n"
        ".ia_table__cell[data-column-id=\"pick\"] .ia_checkbox__checkedIcon--disabled {\n"
        "  fill: var(--checkbox--checked);\n"
        "  color: var(--checkbox--checked);\n"
        "}\n"
    )
    write_text(os.path.join(stylesheet_dir, "stylesheet.css"), stylesheet_css)
    write_json(os.path.join(stylesheet_dir, "resource.json"), resource_json(["stylesheet.css"]))

    # views/Installer
    write_json(os.path.join(view_dir, "view.json"), build_view_json(themes, version))
    write_json(os.path.join(view_dir, "resource.json"), resource_json(["view.json"]))

    # views/Preview, Themes, How -- the lay-reader surface: a miniature
    # screen painted from params, the gallery of all themes drawn with their
    # real colours, and the three-sentence story with a before/after pair.

    # views/Changes and views/Contract -- the insight pages. Generated, but
    # they contain no data of their own: every number is bound to a themepack
    # call that reads the live gateway.
    write_json(os.path.join(editor_dir, "view.json"),
               build_editor_view_json(themes, version))
    write_json(os.path.join(editor_dir, "resource.json"), resource_json(["view.json"]))

    # views/SelectorPopup -- copied verbatim from the hand-adapted, commit-tracked
    # template (NOT generated from out/ -- see tools/themes/selector-popup/README.md). Only
    # resource.json is built fresh here, same as every other resource.json in
    # this project: no signature, timestamp from the clock.
    with open(SELECTOR_POPUP_SRC) as fh:
        popup_view = json.load(fh)
    write_json(os.path.join(popup_dir, "view.json"), popup_view)
    write_json(os.path.join(popup_dir, "resource.json"), resource_json(["view.json"]))

    write_json(os.path.join(import_dir, "view.json"), build_import_view_json(version))
    write_json(os.path.join(import_dir, "resource.json"), resource_json(["view.json"]))

    # views/ThemeDropdown -- the other copy-me view, same treatment.
    with open(THEME_DROPDOWN_SRC) as fh:
        dropdown_view = json.load(fh)
    write_json(os.path.join(dropdown_dir, "view.json"), dropdown_view)
    write_json(os.path.join(dropdown_dir, "resource.json"), resource_json(["view.json"]))

    print("build_manager.py: wrote the project (%d themes, v%s)" % (
        len(themes), version))


if __name__ == "__main__":
    main()
