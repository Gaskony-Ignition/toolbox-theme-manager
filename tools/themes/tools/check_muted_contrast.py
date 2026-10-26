#!/usr/bin/env python3
"""Fail if a muted-text class misses WCAG 2.1 AA (4.5:1) on a surface it sits on.

check_contrast.py checks the :root variables against the three container
surfaces, and check_alarm_contrast.py checks the alarm rows. Neither looks at
the secondary-text classes (`text/muted`, `kpi/label`, ...) on the other
surfaces they are drawn on: the card header, the sidebar, the tile and readout
frames, the chip, the progress track. v2.1.4 shipped industrial-light's muted
grey at 3.96:1 on its card header because of that gap.

It also covers the roles drawn on their own background: the active nav item,
the status pill, the alarm banner and its text (v2.1.6). Their background is
composited over the surface beneath it, and a gradient's translucent stops
are tried too, so the worst point of the fill is what is held to 4.5:1. None
of these is large text (11-14px, weight 500-700 is under the 18.66px bold /
24px regular threshold), so all take 4.5:1.

Reads out/<theme>/globals.css. A surface that is transparent or translucent is
composited the way check_alarm_contrast.py does.

Usage: tools/check_muted_contrast.py        exit 1 on any failure
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
from build_theme import contrast_ratio, flatten, parse_colour  # noqa: E402
from check_alarm_contrast import _class_rules, _resolve_bg  # noqa: E402
from check_contrast import read_vars, resolve  # noqa: E402

FLOOR = 4.5
PAGE = "page"  # --st-page-solid, not a class
CONTENT = [PAGE, "containers/card", "containers/card-header", "kpi/tile", "readouts/frame",
           "buttons/chip", "status/badge-neutral", "progress/track"]

# class -> the surfaces it can be drawn on. nav-group lives only in the sidebar,
# which several themes make dark, so it is not held against the content surfaces.
ROLES = {
    "text/muted": CONTENT + ["containers/sidebar", "containers/topbar"],
    "text/nav-group": ["containers/sidebar"],
    "kpi/label": [PAGE, "containers/card", "containers/card-header", "kpi/tile"],
    "kpi/unit": [PAGE, "containers/card", "containers/card-header", "kpi/tile"],
    "readouts/label": [PAGE, "containers/card", "containers/card-header", "readouts/frame"],
    "readouts/unit": [PAGE, "containers/card", "containers/card-header", "readouts/frame"],
    "readouts/label-warn": ["readouts/frame-warn"],
    "readouts/unit-warn": ["readouts/frame-warn"],
    "readouts/value-warn": ["readouts/frame-warn"],
    "status/badge-ok": ["status/badge-ok"],
    "status/badge-warn": ["status/badge-warn"],
}

# role -> (surface it sits on, [(own-background class or None)]). A role with
# an own background is checked on that fill composited over each base surface.
OWN = [
    # (role, own-fill class, base surfaces beneath the fill)
    ("nav/item", None, ["containers/sidebar"]),
    ("nav/item-active", "nav/item-active", ["containers/sidebar"]),
    ("status/pill", "status/pill", [PAGE, "containers/card", "containers/card-header", "kpi/tile"]),
    ("status/pill-text", "status/pill", [PAGE, "containers/card", "containers/card-header", "kpi/tile"]),
    ("status/pill-text", None, [PAGE, "containers/card", "containers/card-header", "kpi/tile", "readouts/frame"]),
    ("containers/alarm-banner", "containers/alarm-banner", [PAGE]),
    ("containers/alarm-banner-text", "containers/alarm-banner", [PAGE]),
]


def fills(css, cls, base, values, root):
    """-> the colours a class's background can show: its colour over base, and
    each translucent gradient stop over that."""
    rules = _class_rules(css, cls)
    raw = rules.get("background-color") or rules.get("background")
    solid = flatten(raw, base) if raw and parse_colour(raw) and raw != "transparent" else base
    out = [solid]
    for stop in re.findall(r"rgba?\([^)]*\)", rules.get("background-image", "")):
        out.append(flatten(stop, solid))
    return out


def main():
    out = os.path.join(REPO, "out")
    failures, missing, checked = [], [], 0
    for theme in sorted(os.listdir(out)):
        path = os.path.join(out, theme, "globals.css")
        if not os.path.isfile(path):
            continue
        css = re.sub(r"/\*.*?\*/", "", open(path).read(), flags=re.S)
        values = read_vars(os.path.join(out, theme))
        root = resolve(values, "--containerRoot")
        page = resolve(values, "--st-page-solid")

        def surface(name):
            if name == PAGE:
                return page
            raw = (_class_rules(css, name).get("background-color")
                   or _class_rules(css, name).get("background"))
            return _resolve_bg(raw, values, root) if raw else None

        for role, surfaces in ROLES.items():
            fg_raw = _class_rules(css, role).get("color")
            if not fg_raw or not parse_colour(fg_raw):
                missing.append("%s %s: no plain colour (%r)" % (theme, role, fg_raw))
                continue
            for name in surfaces:
                bg = surface(name)
                if not bg:
                    missing.append("%s %s on %s: surface not a plain colour" % (theme, role, name))
                    continue
                # A sidebar or topbar on the other side of light/dark from the
                # page (finance-ledger, leather-light) takes its own text colour.
                if role == "text/muted" and name in ("containers/sidebar", "containers/topbar") \
                        and (contrast_ratio(bg, "#000000") < contrast_ratio(bg, "#ffffff")) \
                        != (contrast_ratio(page, "#000000") < contrast_ratio(page, "#ffffff")):
                    continue
                checked += 1
                fg = flatten(fg_raw, bg)
                ratio = contrast_ratio(fg, bg)
                if ratio < FLOOR:
                    failures.append("%-16s %-20s %s on %-22s %s  %.2f:1 < %.1f"
                                    % (theme, role, fg, name, bg, ratio, FLOOR))
        for role, own, bases in OWN:
            fg_raw = _class_rules(css, role).get("color")
            if not fg_raw or not parse_colour(fg_raw):
                missing.append("%s %s: no plain colour (%r)" % (theme, role, fg_raw))
                continue
            for name in bases:
                base = surface(name)
                if not base:
                    missing.append("%s %s on %s: surface not a plain colour" % (theme, role, name))
                    continue
                for bg in (fills(css, own, base, values, root) if own else [base]):
                    checked += 1
                    fg = flatten(fg_raw, bg)
                    ratio = contrast_ratio(fg, bg)
                    if ratio < FLOOR:
                        failures.append("%-16s %-28s %s on %-22s %s  %.2f:1 < %.1f"
                                        % (theme, role, fg, (own + " over " if own else "") + name,
                                           bg, ratio, FLOOR))
    for line in missing:
        print("not checked: " + line)
    for line in failures:
        print("FAIL " + line)
    print("%d checks, %d failed, %d not checked" % (checked, len(failures), len(missing)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
