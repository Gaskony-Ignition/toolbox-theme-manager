#!/usr/bin/env python3
"""Fail if any generated theme misses WCAG 2.1 AA contrast.

Reads out/<theme>/variables.css and globals.css as the gateway would see them
(later :root declarations win) and checks each text/surface and
control-edge/surface pair. A value that is not a plain colour (a gradient, or
`transparent` on a button border) cannot be checked; those are counted and
printed, never skipped silently.

Usage: tools/check_contrast.py        exit 1 on any failure
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from build_theme import contrast_ratio, flatten, parse_colour  # noqa: E402

SURFACES = ["--containerRoot", "--container", "--containerNested"]

# (foreground, [backgrounds], floor)
PAIRS = [
    *[(v, SURFACES, 4.5) for v in
      ["--label", "--label--disabled", "--neutral-100",
       "--error", "--warning", "--success", "--info"]],
    ("--st-fg", ["--st-page-solid", "--st-card"], 4.5),
    ("--st-on-accent", ["--st-accent"], 4.5),
    ("--a11y-button-text",
     ["--callToAction", "--callToAction--hover", "--callToAction--active"], 4.5),
    ("--st-btn-dan-fg", ["--st-btn-dan-bg"], 4.5),
    ("--st-btn-gho-fg", ["--st-btn-gho-bg"], 4.5),
    ("--st-head-fg", ["--st-head-solid"], 4.5),
    ("--st-tab-active", ["--st-card"], 4.5),
    ("--st-tab-inactive", ["--st-card"], 4.5),
    ("--st-cell-fg", ["--st-table-bg"], 4.5),
    ("--st-input-fg", ["--st-input-bg"], 4.5),
    ("--st-chrome-fg", ["--st-sidebar-solid"], 4.5),  # popup header
    ("--a11y-input-edge", SURFACES + ["--input"], 3.0),
    # The table grid's ring is inset over the table's own surfaces.
    ("--a11y-focus-ring", SURFACES + ["--st-table-bg", "--st-head-solid"], 3.0),
    *[(v, SURFACES, 3.0) for v in
      ["--checkbox--unchecked", "--radio--unselected", "--toggleSwitch--unselected"]],
]


def read_vars(theme_dir):
    values = {}
    for name in ("variables.css", "globals.css"):
        css = re.sub(r"/\*.*?\*/", "", open(os.path.join(theme_dir, name)).read(), flags=re.S)
        for block in re.findall(r":root\s*\{([^}]*)\}", css):
            for var, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block):
                values[var] = value.strip()
    return values


def resolve(values, var, depth=0):
    value = values.get(var)
    m = re.fullmatch(r"var\((--[\w-]+)\)", value or "")
    if m and depth < 10:
        return resolve(values, m.group(1), depth + 1)
    return value


def solid(values, var, page):
    """A background as the eye sees it: translucent surfaces over the page."""
    value = resolve(values, var)
    if value == "transparent":  # a ghost button shows the card behind it
        value = resolve(values, "--st-card")
    colour = parse_colour(value)
    if not colour:
        return None
    return flatten(value, page) if colour[3] < 1 else flatten(value, "#ffffff")


def main():
    out = os.path.join(REPO, "out")
    failures, unchecked, checked = [], [], 0
    for theme in sorted(os.listdir(out)):
        theme_dir = os.path.join(out, theme)
        if not os.path.isdir(theme_dir):
            continue
        values = read_vars(theme_dir)
        page = resolve(values, "--containerRoot")
        for fg_var, bg_vars, floor in PAIRS:
            if fg_var not in values:
                continue
            for bg_var in bg_vars:
                bg = solid(values, bg_var, page)
                fg_value = resolve(values, fg_var)
                fg = flatten(fg_value, bg) if bg and parse_colour(fg_value) else None
                if not bg or not fg:
                    unchecked.append("%s %s on %s" % (theme, fg_var, bg_var))
                    continue
                checked += 1
                ratio = contrast_ratio(fg, bg)
                if ratio < floor:
                    failures.append("%-16s %-26s %s on %-18s %s  %.2f:1 < %.1f"
                                    % (theme, fg_var, fg, bg_var, bg, ratio, floor))
    for line in unchecked:
        print("not a plain colour, unchecked: " + line)
    for line in failures:
        print("FAIL " + line)
    print("%d pairs checked, %d failed, %d unchecked" % (checked, len(failures), len(unchecked)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
