#!/usr/bin/env python3
"""Capture Ignition's OWN theme palettes into insight/stock-palettes.json.

The six stock themes are what a gateway looks like before this project touches
it, and "The themes" page draws all six so a reader can see what they are
choosing between. Their stylesheets are not in this repo -- light and dark live
inside the Perspective module, and the four variants are gateway config
resources -- so a build machine with no gateway cannot read them. Same reason
tools/sync-packs.sh vendors the source packs.

    python3 insight/capture_stock.py http://gateway.example.com:8088

Nothing is installed from the result and no theme depends on it; it only paints
the previews. Re-run when Ignition changes its neutrals.
"""
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stock-palettes.json")
STOCK = ["light", "dark", "light-cool", "light-warm", "dark-cool", "dark-warm"]
LABELS = {"light": "Ignition light", "dark": "Ignition dark",
          "light-cool": "Light cool", "light-warm": "Light warm",
          "dark-cool": "Dark cool", "dark-warm": "Dark warm"}
VARDEF = re.compile(r'^[ \t]*(--[A-Za-z0-9_-]+)[ \t]*:[ \t]*([^;]+);', re.M)


def palette(css):
    # Last definition wins, as the cascade does.
    values = {}
    for match in VARDEF.finditer(css):
        values[match.group(1)] = match.group(2).strip()

    def resolve(value, hops=0):
        # The stock themes define nearly everything as var(--neutral-NN); left
        # unresolved they render in the VIEWING page's colours, which quietly
        # shows the wrong thing rather than nothing.
        while value.startswith("var(") and hops < 6:
            name = re.match(r'var\(\s*(--[A-Za-z0-9_-]+)', value)
            if not name:
                return ""
            value = values.get(name.group(1), "").strip()
            hops += 1
        return "" if value.startswith("var(") else value

    def pick(*names):
        for name in names:
            got = resolve(values.get(name, "").strip())
            if got and got != "transparent":
                return got
        return ""

    page = pick("--containerRoot")
    return {
        "page": page,
        "sidebar": pick("--containerNested", "--container"),
        "card": pick("--container"),
        "text": pick("--label"),
        "muted": pick("--label--disabled", "--label"),
        "chromeFg": pick("--label"),
        "accent": pick("--callToAction"),
        "onAccent": "#ffffff",
        "border": pick("--border"),
        "headBg": pick("--containerNested", "--container"),
        "headFg": pick("--label"),
        "rowBg": page,
        "cellFg": pick("--label"),
    }


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
    if not base:
        sys.exit("usage: capture_stock.py <gateway base url>")
    out = {"_comment": [
        "Ignition's OWN theme palettes, captured by insight/capture_stock.py.",
        "Not in this repo: light and dark live inside the Perspective module,",
        "and the four variants are gateway config resources, so a build machine",
        "with no gateway cannot read them. Used ONLY to draw the 'what every",
        "gateway starts with' previews -- nothing is installed from this file",
        "and no theme depends on it. Re-run the script to refresh.",
        "Captured from %s" % base,
    ], "order": STOCK, "labels": LABELS, "palettes": {}}
    for theme in STOCK:
        url = "%s/data/perspective/themes/%s.css" % (base, theme)
        css = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
        got = palette(css)
        missing = [k for k, v in got.items() if not v]
        if missing:
            sys.exit("%s: could not resolve %s" % (theme, ", ".join(missing)))
        out["palettes"][theme] = got
        print("  %-12s %s" % (theme, got["page"]))
    with open(OUT, "w") as handle:
        json.dump(out, handle, indent=2)
    print("wrote %s" % os.path.relpath(OUT, os.path.dirname(HERE)))


if __name__ == "__main__":
    main()
