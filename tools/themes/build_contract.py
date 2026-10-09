#!/usr/bin/env python3
"""Appends a 69-class style-class contract to each theme's globals.css.

Perspective emits whatever string sits in `style.classes` into the DOM as a
`psc-<string>` class, resource or no resource -- so a theme's globals.css,
served gateway-wide, can define `.psc-st\\/containers\\/card` and carry a
whole semantic class contract without a parent project or a Designer
style-class resource. The payload is built in cascade order: each pack's 40
`--st-*` tokens hoisted to `:root`, `contract/chrome.css` verbatim (component
chrome, shell, card grid, written against `[class*="/family/name"]` attribute
selectors so slash-named classes port unchanged), then the 69-class contract
itself.

Class names keep their slashes (`st/containers/card`, not
`st-containers-card`) so they port byte-for-byte against those attribute
selectors. Selectors here are doubled rather than using `!important`
(`.psc-st\\/x\\/y.psc-st\\/x\\/y`, specificity 0-2-0): a theme loads before
IA's own component CSS, so a plain class would lose ties it needs to win, but
`!important` would also beat inline styles and break per-component overrides.

Inputs are vendored under `contract/`; nothing here reads a sibling checkout.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = os.path.join(HERE, "contract")


def _kebab(prop):
    """backgroundColor -> background-color; borderLeftWidth -> border-left-width."""
    return re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), prop)


def _selector(path):
    """`containers/card` -> `.psc-st\\/containers\\/card.psc-st\\/containers\\/card`.

    Slashes are CSS-escaped; the class is doubled for specificity. See the
    module docstring for why both of those are load-bearing.
    """
    one = ".psc-st" + "".join("\\/" + seg for seg in path.split("/"))
    return one + one


def _block(selector, style):
    return "%s {\n%s}\n" % (selector, "".join(
        "  %s: %s;\n" % (_kebab(k), v) for k, v in style.items()))


def has_contract(pack_id):
    """Whether this pack has been vendored. Themes build fine without it."""
    return os.path.isfile(os.path.join(CONTRACT, "classes", "%s.json" % pack_id))


# The seven roles a chart config paints with, and where each is read from in
# the contract. Lifted verbatim from Styles_Template2's own
# `styles._PALETTE_SOURCES` so a migrated chart gets the identical colours --
# "a chart needs an ink, a paper, a grid line and a series colour, and anything
# more invites charts that are decorated rather than legible".
#
# This is the one deliverable a theme CANNOT carry as CSS: Chart.js takes
# literal colours in its options, not `var()`, so a chart cannot read the
# theme's own custom properties. Hence a data file, emitted alongside the
# themes, that a consumer's script library reads.
PALETTE_SOURCES = [
    ("kpi/value", "color", "ink"),
    ("text/muted", "color", "muted"),
    ("charts/frame", "backgroundColor", "paper"),
    ("charts/frame", "borderColor", "grid"),
    ("buttons/primary", "backgroundColor", "series"),
    ("kpi/delta-up", "color", "good"),
    ("kpi/delta-down", "color", "bad"),
]


# Styles_Template2's own _PALETTE_FALLBACK, carried over with the sources above.
# It is the half that is easy to drop and the half that makes the contract seven
# roles rather than "however many this pack happens to define": `charts/frame`
# carries no borderColor in eight of the ten packs, so `grid` resolves from the
# source data for only two of them. v2 started from these defaults and overlaid
# whatever it could read, so a chart always had all seven; emitting only what
# resolves would hand a consumer six keys and a chart with no grid line -- or a
# KeyError, depending on how it reads them.
PALETTE_FALLBACK = {"ink": "#E8EFF5", "muted": "#7E93A3", "paper": "#0F161E",
                    "grid": "#26333F", "series": "#2BB3D6",
                    "good": "#4CC38A", "bad": "#E5484D"}


def build_palette(pack_id):
    """The seven chart roles for one pack, or None if it is not vendored.

    Starts from PALETTE_FALLBACK and overlays what the pack defines, which is
    what Styles_Template2 did -- see the note above for why that matters.
    """
    if not has_contract(pack_id):
        return None
    classes = json.load(open(os.path.join(CONTRACT, "classes", "%s.json" % pack_id)))
    palette = dict(PALETTE_FALLBACK)
    for class_path, style_key, role in PALETTE_SOURCES:
        style = ((classes.get(class_path) or {}).get("base") or {}).get("style") or {}
        value = style.get(style_key)
        if value:
            palette[role] = value
    return palette


def build_contract(pack_id):
    """The full payload for one pack, or "" if it has not been vendored."""
    if not has_contract(pack_id):
        return ""

    tokens = json.load(open(os.path.join(CONTRACT, "tokens", "%s.json" % pack_id)))
    classes = json.load(open(os.path.join(CONTRACT, "classes", "%s.json" % pack_id)))
    chrome = open(os.path.join(CONTRACT, "chrome.css")).read()

    out = [
        "\n/* ======================================================================",
        " * Styles_Template2 compatibility payload -- GENERATED by build_contract.py.",
        " * Source pack: %s. Lets a project drop the styles parent entirely:" % pack_id,
        " * tokens, component chrome and the 69-class contract all travel in the",
        " * theme. Class names keep their slashes and the selectors are doubled",
        " * rather than !important -- see build_contract.py's docstring.",
        " * ==================================================================== */",
        "",
        "/* ---- 1. the pack's own tokens (section 1, collapsed to :root) ---- */",
        ":root {",
    ]
    out += ["  %s: %s;" % (k, v) for k, v in sorted(tokens.items())]
    out += ["}", "",
            "/* ---- 2. component chrome, shell and card grid (verbatim) ---- */",
            chrome,
            "/* ---- 3. the 69-class contract ---- */"]

    for path in sorted(classes):
        definition = classes[path]
        sel = _selector(path)
        base = (definition.get("base") or {}).get("style") or {}
        if base:
            out.append(_block(sel, base))
        for variant in definition.get("variants") or []:
            pseudo, style = variant.get("pseudo"), variant.get("style")
            if pseudo and style:
                out.append(_block("%s:%s" % (sel, pseudo), style))

    return "\n".join(out)


if __name__ == "__main__":
    import sys
    pack = sys.argv[1] if len(sys.argv) > 1 else "aurora-violet"
    css = build_contract(pack)
    if not css:
        sys.exit("pack %r has no vendored contract -- run tools/sync-contract.sh" % pack)
    sys.stderr.write("%s: %d bytes\n" % (pack, len(css)))
    print(css)
