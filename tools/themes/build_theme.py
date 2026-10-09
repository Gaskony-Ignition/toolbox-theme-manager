#!/usr/bin/env python3
"""Generate 9 curated Perspective gateway THEMES from 9 existing packs.

This script is not wired into tools/build_all.py, does not import anything
from tools/, and never touches Styles_Template2/, Styles_Example2/, packs/
or families/. It only READS files under packs/ and WRITES under
out/ (which it wipes and rebuilds from scratch every run
-- see main()).

Usage:
    python3 build_theme.py

For each entry in THEMES, resolves mapping.MAPPING (the core ~35 IA
variables) against that entry's SOURCE PACK, applies mapping.TWEAKS[id] if
one exists (a literal data-only override -- see mapping.py's docstring),
resolves mapping.EXTENDED_MAPPING (controls/symbols/pipes/status/misc, a
second pass so it can `ref:` the tweaked values), generates the three
algorithmic chart scales (--qual-1..10, --seq-1..6, --div-1..16), and writes
out/<theme-id>/{config.json, index.css, variables.css, globals.css,
resource.json}. THEME ID != pack id in general now (e.g. glass-green comes
from packs/aurora-teal.json) -- see THEMES below. out/themes.json is a
LABELS index (id, label, dark, source pack) for whatever selector UI
consumes these.

Each pack's own "dark" flag decides two things: which of Perspective's two
undeliverable built-in themes it imports as a base (`../dark/index.css` or
`../light/index.css`), and the `color-scheme` value declared in
variables.css. Nothing else in the mapping or the colour maths cares about
light vs dark -- flatten() only composites colours, it does not know or need
to know which direction "light" runs.

Prints a WARNING line for every mapping entry that needed a fallback source,
bottomed out at a literal fallback, or produced a chart-scale colour with
poor contrast against the page or too close to its neighbour -- those lines
are evaluation evidence, not just debug noise. Exits non-zero only on a hard
error (missing pack file, totally unresolvable entry with no literal
fallback at all).
"""

import colorsys
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapping import (MAPPING, EXTENDED_MAPPING, TWEAKS,  # noqa: E402
                     SHORTHAND_VARS)
from build_contract import build_contract, build_palette  # noqa: E402

# Standalone repo: the 10 source packs are VENDORED under packs/ (copied from
# ignition-styles-template-v2, the design source of truth for colours --
# tools/sync-packs.sh re-pulls them from a sibling checkout when they change).
REPO = os.path.dirname(os.path.abspath(__file__))
PACKS_DIR = os.path.join(REPO, "packs")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(OUT_DIR, "out")

# The 9 curated themes. "id"/"label" are the exact display names; "pack" is
# the SOURCE PACK file this theme derives from -- kept explicit (not assumed
# == id) so the derivation stays traceable even where id and pack diverge
# (glass-green <- aurora-teal, everything else <- a pack of a
# related-but-different name; only finance-ledger has id == pack).
# family: grouping for pickers (a family is not necessarily a light/dark pair --
# the glass pair are two hues, both dark). pair: the id of this theme's
# light<->dark counterpart, or None. Emitted into out/themes.json so consumers
# lay out counterparts side by side without deriving pairs from id strings --
# string-stripping cannot know finance-ledger's counterpart or that the glass
# pair isn't one.
THEMES = [
    {"id": "glass-violet", "label": "Glass Violet", "pack": "aurora-violet",
     "family": "glass", "pair": None},
    {"id": "glass-green", "label": "Glass Green", "pack": "aurora-teal",
     "family": "glass", "pair": None},
    {"id": "leather-dark", "label": "Leather Dark", "pack": "leather-night-tan",
     "family": "leather", "pair": "leather-light"},
    {"id": "leather-light", "label": "Leather Light", "pack": "leather-parchment-tan",
     "family": "leather", "pair": "leather-dark"},
    {"id": "finance-ledger", "label": "Finance Ledger", "pack": "finance-ledger",
     "family": "finance", "pair": "newsprint-dark"},
    {"id": "newsprint-dark", "label": "Newsprint Dark", "pack": "newsprint-night",
     "family": "finance", "pair": "finance-ledger"},
    {"id": "nord-dark", "label": "Nord Dark", "pack": "nord-dark-frost",
     "family": "nord", "pair": "nord-light"},
    {"id": "nord-light", "label": "Nord Light", "pack": "nord-light-frost",
     "family": "nord", "pair": "nord-dark"},
    {"id": "industrial-dark", "label": "Industrial Dark", "pack": "industrial-control-cyan",
     "family": "industrial", "pair": "industrial-light"},
    {"id": "industrial-light", "label": "Industrial Light", "pack": "industrial-day-cyan",
     "family": "industrial", "pair": "industrial-dark"},
]

WARNINGS = []  # collected across the whole run, printed + returned


def warn(theme, msg):
    line = "WARNING [%s] %s" % (theme, msg)
    WARNINGS.append(line)
    print(line)


# ---------------------------------------------------------------------------
# Colour maths -- copied verbatim (docstring trimmed) from
# ignition-styles-template-v2/tools/build_css.py's parse_colour()/flatten(),
# per the plan's explicit instruction to replicate rather than import from
# tools/. Do not let this drift silently; if tools/build_css.py's algorithm
# changes, this copy is NOT updated automatically.
# ---------------------------------------------------------------------------

def parse_colour(value):
    """-> (r, g, b, a) or None for anything we cannot reason about (gradients,
    `transparent`, keywords). Callers fall back rather than guess."""
    if not value:
        return None
    value = value.strip()
    m = re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", value)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(float(int(h[i:i + 2], 16)) for i in (0, 2, 4)) + (1.0,)
    m = re.match(r"^rgba?\(([^)]+)\)$", value)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", ",").split(",")]
        try:
            rgb = tuple(float(p) for p in parts[:3])
        except ValueError:
            return None
        a = float(parts[3]) if len(parts) > 3 else 1.0
        return rgb + (a,)
    return None


def flatten(colour, behind):
    """Composite `colour` over the opaque `behind`, -> #rrggbb."""
    c = parse_colour(colour)
    if not c:
        return behind if isinstance(behind, str) else "#ffffff"
    b = parse_colour(behind) or (255.0, 255.0, 255.0, 1.0)
    a = c[3]
    return "#%02x%02x%02x" % tuple(
        int(round(c[i] * a + b[i] * (1 - a))) for i in range(3))


# ---------------------------------------------------------------------------
# Mini-DSL resolver -- see mapping.py's module docstring for the grammar.
# ---------------------------------------------------------------------------

def _lookup_token(pack, key):
    return pack.get("tokens", {}).get(key)


def _lookup_variant(pack, classpath, pseudo, prop):
    for entry in pack.get("variants", {}).get(classpath, []):
        if entry.get("pseudo") == pseudo:
            return entry.get("style", {}).get(prop)
    return None


def resolve_one(pack, spec, computed):
    """Resolve a single source-spec (no fallback chain here) -> value or None."""
    if spec.startswith("token:"):
        return _lookup_token(pack, spec[len("token:"):])
    if spec.startswith("literal:"):
        return spec[len("literal:"):]
    if spec.startswith("ref:"):
        varname = spec[len("ref:"):]
        return computed.get(varname)
    if spec.startswith("variant:"):
        _, classpath, pseudo, prop = spec.split(":", 3)
        return _lookup_variant(pack, classpath, pseudo, prop)
    raise ValueError("unrecognised source spec: %r" % spec)


def resolve_colour_for_transform(pack, spec, computed):
    """Resolve `spec` AND confirm it parses as a colour (for flatten/alpha/
    darken). Returns (raw_value, parsed_rgba) or (None, None) if unresolved
    or unparsable -- unparsable counts as unresolved so the caller's fallback
    chain keeps trying rather than silently degrading."""
    raw = resolve_one(pack, spec, computed)
    if raw is None:
        return None, None
    parsed = parse_colour(raw)
    if parsed is None:
        return None, None
    return raw, parsed


def apply_transform(transform, raw_value, pack, entry, computed):
    behind_spec = entry.get("behind")
    if transform == "literal":
        return raw_value
    if transform == "flatten":
        behind = "#ffffff"
        if behind_spec:
            behind_val = resolve_one(pack, behind_spec, computed)
            if behind_val is not None:
                behind = behind_val
        return flatten(raw_value, behind)
    if transform.startswith("alpha:"):
        pct = float(transform.split(":", 1)[1])
        c = parse_colour(raw_value)
        if not c:
            # already an opaque hex/whatever from an upstream ref/flatten --
            # try parsing again defensively; if it still fails, pass through.
            return raw_value
        return "rgba(%d,%d,%d,%s)" % (int(c[0]), int(c[1]), int(c[2]), pct)
    if transform.startswith("darken:"):
        pct = float(transform.split(":", 1)[1])
        c = parse_colour(raw_value)
        if not c:
            return raw_value
        return "#%02x%02x%02x" % tuple(
            int(round(c[i] * (1 - pct))) for i in range(3))
    if transform == "inset":
        if raw_value == "none":
            return "none"
        return "inset " + raw_value
    if transform.startswith("lerp:"):
        _, t_str, other_ref = transform.split(":", 2)
        t = float(t_str)
        a = parse_colour(raw_value)
        other_val = computed.get(other_ref)
        b = parse_colour(other_val) if other_val is not None else None
        if not a or not b:
            # can't interpolate without two real colours -- pass the primary
            # endpoint through unchanged rather than guess.
            return raw_value
        return "#%02x%02x%02x" % tuple(
            int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))
    raise ValueError("unrecognised transform: %r" % transform)


def emit_value(var, value, pack):
    """The text written into variables.css for `var`.

    Identical to the computed value except for the handful of variables IA
    consumes as a CSS shorthand -- see mapping.SHORTHAND_VARS for why this is
    an emit-time concern and not a mapping one. computed[] keeps the colour.
    """
    spec = SHORTHAND_VARS.get(var)
    if not spec:
        return value
    width = _lookup_token(pack, spec["width_token"]) or spec["width_default"]
    return "%s %s %s" % (width, spec["style"], value)


def requirement_failure(entry, raw_value, pack, computed):
    """Does `raw_value` satisfy entry["require"]? Returns None if it does (or if
    there is no requirement), else a short reason for the warning.

    The value is transformed FIRST, because the constraint is about what will
    actually be painted: a 12% danger wash only becomes #251317 once it has been
    flattened over the page, and it is the flattened result that has to be
    legible, not the token.

    Only `contrast_with` today -- a minimum WCAG ratio against another variable,
    for a colour IA uses as INK. --error is the case that needs it: Ignition
    paints alarm text and error labels with it, so it has to read against the
    card it sits on, and three packs supplied something that cannot.
    """
    req = entry.get("require")
    if not req:
        return None
    value = apply_transform(entry["transform"], raw_value, pack, entry, computed)
    against = resolve_one(pack, req["contrast_with"], computed)
    if against is None:
        # The thing to contrast against is not computed yet -- a mapping.py
        # ordering bug. Fail loudly rather than silently skipping the check.
        raise SystemExit(
            "FATAL %s: require.contrast_with=%r is not computed yet; move the "
            "entry after it in MAPPING" % (entry["var"], req["contrast_with"]))
    ratio = contrast_ratio(value, against)
    if ratio >= req["min"]:
        return None
    return "%s on %s is %.2f:1, under %.1f" % (value, against, ratio, req["min"])


def resolve_entry(pack, entry, computed, theme_name):
    var = entry["var"]
    sources = entry["sources"]
    transform = entry["transform"]
    used_spec = None
    raw_value = None

    # An entry may also declare `require`, a legibility constraint the RESOLVED
    # value has to satisfy. A candidate that resolves but fails it is treated
    # exactly like one that did not resolve at all -- the chain keeps trying --
    # which is the same principle resolve_colour_for_transform already applies
    # to an unparsable colour. Without this a source only has to EXIST to be
    # accepted, and a token whose name matches can still be the wrong kind of
    # value (see mapping.py's --error note).
    rejected = []

    for i, spec in enumerate(sources):
        if transform in ("flatten",):
            val, parsed = resolve_colour_for_transform(pack, spec, computed)
        else:
            val = resolve_one(pack, spec, computed)
        if val is None:
            continue

        why = requirement_failure(entry, val, pack, computed)
        if why is not None:
            rejected.append((spec, why))
            continue

        raw_value = val
        used_spec = spec
        if i > 0:
            detail = "earlier source(s) %r missing or unparsable" % (sources[:i],)
            if rejected:
                detail = "; ".join("%s rejected (%s)" % (s, w) for s, w in rejected)
            warn(theme_name, "%s: fell back to %r (%s)" % (var, spec, detail))
        break

    if raw_value is None:
        # Hard failure: nothing in the fallback chain resolved, and there was
        # no literal: at the end of it to catch this. This is a mapping.py
        # authoring bug, not an evaluation finding, so it's fatal.
        raise SystemExit(
            "FATAL [%s] %s: no source resolved at all (sources=%r) -- "
            "mapping.py needs a literal: fallback here" % (theme_name, var, sources))

    if used_spec is not None and used_spec.startswith("literal:"):
        warn(theme_name, "%s: bottomed out at literal fallback %r" % (var, raw_value))

    value = apply_transform(transform, raw_value, pack, entry, computed)
    computed[var] = value
    return value, used_spec


def apply_tweaks(theme_id, computed, theme_name):
    """Overwrite `computed` in place with mapping.TWEAKS[theme_id]["vars"], if
    any -- literal DATA overrides, applied after MAPPING and before
    EXTENDED_MAPPING / chart scales (see mapping.py's TWEAKS docstring)."""
    tweak = TWEAKS.get(theme_id)
    if not tweak:
        return
    var_overrides = tweak.get("vars", {})
    for var, value in var_overrides.items():
        computed[var] = value
    if var_overrides:
        print("TWEAK [%s] %d var(s) overridden by mapping.TWEAKS: %s"
              % (theme_name, len(var_overrides), ", ".join(sorted(var_overrides))))


# ---------------------------------------------------------------------------
# Chart scales -- generated algorithmically (colorsys), NOT read from a pack
# (no pack defines a 10/16/6-step scale). Anchored on the theme's OWN final
# --callToAction / --error / --neutral-10 (post-MAPPING, post-TWEAKS), so a
# tweaked theme (glass-green) gets a scale anchored on its tweaked mint
# accent, not the raw pack's teal. Deterministic: same inputs always produce
# the same output, no randomness anywhere in this section.
# ---------------------------------------------------------------------------

def _rgb01(hex_colour):
    c = parse_colour(hex_colour)
    return (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)


def _hex_from_rgb01(rgb):
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, int(round(v * 255)))) for v in rgb)


def _hue_of(hex_colour):
    r, g, b = _rgb01(hex_colour)
    h, _l, _s = colorsys.rgb_to_hls(r, g, b)
    return h


def _hls_hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return _hex_from_rgb01((r, g, b))


def build_qual(accent_hex, is_dark):
    """10 distinguishable hues rotated around the wheel, anchored at the
    theme's accent hue (qual-1 IS the accent hue, unrotated)."""
    h0 = _hue_of(accent_hex)
    l = 0.65 if is_dark else 0.46
    s = 0.60
    return [_hls_hex(h0 + i / 10.0, l, s) for i in range(10)]


def build_seq(accent_hex, is_dark):
    """6-step monotonic ramp of the accent hue, weak -> strong. "Weak" reads
    as low-contrast against the theme's own page (dark: darker+desaturated;
    light: paler+desaturated); "strong" is the vivid, saturated end."""
    h0 = _hue_of(accent_hex)
    if is_dark:
        l_start, l_end = 0.22, 0.72
        s_start, s_end = 0.30, 0.70
    else:
        l_start, l_end = 0.88, 0.40
        s_start, s_end = 0.25, 0.70
    out = []
    for i in range(6):
        t = i / 5.0
        out.append(_hls_hex(h0, l_start + (l_end - l_start) * t,
                             s_start + (s_end - s_start) * t))
    return out


def build_div(accent_hex, error_hex, page_hex, is_dark):
    """16-step diverging ramp: accent hue (strong at div-1) through a
    NEUTRAL MIDPOINT matched to the page (same lightness as --neutral-10,
    zero saturation) to the error hue (strong at div-16)."""
    h_a = _hue_of(accent_hex)
    h_e = _hue_of(error_hex)
    _pr, page_l, _ps = colorsys.rgb_to_hls(*_rgb01(page_hex))
    strong_l = 0.62 if is_dark else 0.45
    strong_s = 0.65
    out = []
    for i in range(8):  # accent, strong -> near-neutral
        t = 1.0 - i / 7.0
        out.append(_hls_hex(h_a, page_l + (strong_l - page_l) * t, strong_s * t))
    for i in range(8):  # near-neutral -> error, strong
        t = (i + 1) / 8.0
        out.append(_hls_hex(h_e, page_l + (strong_l - page_l) * t, strong_s * t))
    return out


# ---- sanity checks on the generated scales (WCAG-style, warn-only) --------

def _linearise(c8):
    c = c8 / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_colour):
    c = parse_colour(hex_colour)
    return (0.2126 * _linearise(c[0]) + 0.7152 * _linearise(c[1])
            + 0.0722 * _linearise(c[2]))


def contrast_ratio(hex_a, hex_b):
    la, lb = relative_luminance(hex_a), relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def rgb_distance(hex_a, hex_b):
    ca, cb = parse_colour(hex_a), parse_colour(hex_b)
    return sum((ca[i] - cb[i]) ** 2 for i in range(3)) ** 0.5


# ---- WCAG 2.1 AA floors ----------------------------------------------------
# IA's stock components use --error/--warning/--success/--info as TEXT
# (.ia_form__error, alarm table footers, file upload messages) and never as a
# fill behind text, so the vars themselves must reach 4.5:1 -- a separate
# text token would never reach the stock components.

TEXT_FLOOR = 4.5         # 1.4.3
NON_TEXT_FLOOR = 3.0     # 1.4.11
TEXT_VARS = ["--label", "--label--disabled", "--error", "--warning", "--success", "--info"]
SURFACE_VARS = ["--containerRoot", "--container", "--containerNested"]
# Controls whose unselected edge is the only thing that shows they exist.
EDGE_VARS = ["--checkbox--unchecked", "--radio--unselected", "--toggleSwitch--unselected"]


def min_contrast(colour, surfaces):
    return min(contrast_ratio(colour, s) for s in surfaces)


def lift_to_floor(colour, surfaces, floor, is_dark):
    """Move `colour` in lightness only (hue and saturation kept) away from the
    surfaces until it clears `floor` against every one. Returns the colour
    unchanged when it already passes."""
    if min_contrast(colour, surfaces) >= floor:
        return colour
    h, l, s = colorsys.rgb_to_hls(*_rgb01(colour))
    step = 0.005 if is_dark else -0.005
    while 0.0 <= l + step <= 1.0:
        l += step
        candidate = _hls_hex(h, l, s)
        if min_contrast(candidate, surfaces) >= floor:
            return candidate
    return "#ffffff" if is_dark else "#000000"


def apply_contrast_floors(theme_id, computed, resolutions, names, surfaces, floor, is_dark, why):
    for var in names:
        before = computed[var]
        after = lift_to_floor(before, surfaces, floor, is_dark)
        if after == before:
            continue
        computed[var] = after
        for i, (v, value, spec, note) in enumerate(resolutions):
            if v == var:
                resolutions[i] = (v, after, spec, "%s -- %s %s -> %s for %.1f:1 on every surface (%s)"
                                  % (note, "lightened" if is_dark else "darkened", before, after, floor, why))
        print("A11Y [%s] %s %s -> %s (%.2f -> %.2f:1)" % (
            theme_id, var, before, after, min_contrast(before, surfaces), min_contrast(after, surfaces)))


def check_qual_scale(theme_name, qual, page_hex):
    for i, colour in enumerate(qual):
        cr = contrast_ratio(colour, page_hex)
        if cr < 1.5:
            warn(theme_name,
                 "qual-%d (%s) contrast vs --neutral-10 (%s) is only %.2f (<1.5) -- may read as near-invisible on the page"
                 % (i + 1, colour, page_hex, cr))
        prev = qual[i - 1]  # i=0 compares to qual[-1] (wraparound), by design
        d = rgb_distance(colour, prev)
        if d < 40:
            j = 10 if i == 0 else i
            warn(theme_name,
                 "qual-%d (%s) and qual-%d (%s) are near-identical (rgb distance %.1f, <40)"
                 % (j, prev, i + 1, colour, d))


# ---------------------------------------------------------------------------
# globals.css -- GENERATED generically from each pack's own containers/page
# override, not hand-templated per theme. Two rules, always both present:
#
#   1. #app-container gets the page's background -- backgroundImage from
#      overrides["containers/page"] when the pack declares one (the stacked
#      radial-gradients / paper-texture packs), plus backgroundColor from
#      the pack's own flattened surface.page (--containerRoot) always, so a
#      pack with no signature background image still gets its solid page
#      colour rather than Perspective's own default.
#
#   2. The occlusion-fix rule, found live against test-aurora-violet and
#      test-leather-night-tan on the module-testing gateway:
#      Perspective's own top-level view root -- the element carrying both
#      `.view` and `.ia_container--root` -- paints itself OPAQUE using the
#      theme's own --containerRoot, one level inside #app-container. That is
#      stock IA behaviour for any `ia_container--primary` root container (it
#      consumes --containerRoot as its own background), not a bug in any
#      project's view JSON -- it hides rule 1's background on every ordinary
#      page, in every theme, unless punched through. The structural
#      selector (`.view-parent > .view.ia_container--root`) is a Perspective
#      shell pattern, not specific to any one pack or project, so the same
#      fix generalises unchanged across all 9 themes without needing a
#      separate live check per pack.
# ---------------------------------------------------------------------------

OCCLUSION_FIX_COMMENT = """/* Perspective's own top-level view root paints itself OPAQUE using this
 * theme's --containerRoot (any `ia_container--primary` root container
 * consumes --containerRoot as its own background -- stock IA behaviour, not
 * a bug in any project's view JSON), one level inside #app-container. That
 * hides the background set above on every ordinary page unless punched
 * through. Found live against test-aurora-violet and test-leather-night-tan
 * on the module-testing gateway; the selector is a structural
 * Perspective shell pattern (present on every view, not specific to any one
 * pack or project's component tree), so the same fix generalises unchanged
 * to all 9 themes. Scoped to `.view-parent > .view.ia_container--root` so
 * only the page's own outermost view goes transparent -- docked views,
 * popups, and any view embedded deeper in the tree (via ia.display.view)
 * keep their normal opaque --containerRoot/--container surfaces. */"""


def build_globals(pack, page_solid, globals_tweak, sb_thumb, sb_hover, accent_hex):
    """`globals_tweak` is TWEAKS[id]["globals"] (a dict with optional
    "backgroundImage"/"backgroundColor") or None -- when present it wins over
    the pack's own overrides["containers/page"], because the pack's page
    colour/image is exactly what a TWEAK exists to correct."""
    if globals_tweak:
        bg_image = globals_tweak.get("backgroundImage")
        bg_colour = globals_tweak.get("backgroundColor", page_solid)
        source_lines = [
            " * TWEAKED (see mapping.TWEAKS) -- overrides this pack's own",
            " * overrides[\"containers/page\"].",
        ]
    else:
        ov = pack.get("overrides", {}).get("containers/page", {})
        bg_image = ov.get("backgroundImage")
        bg_colour = page_solid
        source_lines = [
            " * GENERATED from this pack's own overrides[\"containers/page\"].",
        ]

    lines = (["/* globals.css -- %s" % pack["id"],
              " * GENERATED by build_theme.py."]
             + source_lines
             + [" * DO NOT EDIT BY HAND. */",
                "#app-container {"])
    if bg_image:
        lines.append("  background-image: %s;" % bg_image)
    lines.append("  background-color: %s;" % bg_colour)
    lines.append("}")
    lines.append("")
    lines.append(OCCLUSION_FIX_COMMENT)
    lines.append("#app-container .center.view-parent > .view.ia_container--root {")
    lines.append("  background-color: transparent !important;")
    lines.append("}")
    lines.append("")
    lines.append("/* ---- scrollbars follow the theme ----")
    lines.append(" * Stock IA themes leave scrollbars at browser default, so they never change")
    lines.append(" * with the theme. Thumb = the theme's container border tone, accent on hover,")
    lines.append(" * track transparent. `scrollbar-color` is the modern control (Chrome 121+ and")
    lines.append(" * Firefox use it and ignore the ::-webkit-* rules); the ::-webkit-* block")
    lines.append(" * carries width/radius for older Chromium (Perspective Workstation). */")
    lines.append("* {")
    lines.append("  scrollbar-color: %s transparent;" % sb_thumb)
    lines.append("  scrollbar-width: thin;")
    lines.append("}")
    lines.append("::-webkit-scrollbar { width: 10px; height: 10px; }")
    lines.append("::-webkit-scrollbar-track, ::-webkit-scrollbar-corner { background: transparent; }")
    lines.append("::-webkit-scrollbar-thumb {")
    lines.append("  background: %s;" % sb_thumb)
    lines.append("  border-radius: 6px;")
    lines.append("  border: 2px solid transparent;")
    lines.append("  background-clip: content-box;")
    lines.append("}")
    lines.append("::-webkit-scrollbar-thumb:hover { background: %s; background-clip: content-box; }" % sb_hover)

    # ---- compensating rules for hard-coded IA colours --------------------
    # A handful of rules in IA's own flattened dark.css/light.css apply a
    # colour LITERAL directly to a selector rather than through a --var, so
    # no theme -- IA's or ours -- can reach them by overriding variables.css
    # alone. Most of those are neutral (black elevation shadows, dedicated
    # black chrome like the video player) and are correctly left alone -- see
    # README's "Hard-coded colour audit". These three are the ones judged
    # low-risk AND clearly beneficial enough to compensate for here: they are
    # common, visible, and each is a single targeted selector override, never
    # a redesign of a component.
    ar, ag, ab, _aa = parse_colour(accent_hex)
    lines.append("")
    lines.append("/* ---- compensating rules for IA's hard-coded colours ----")
    lines.append(" * See README's \"Hard-coded colour audit\" for the full list found and why")
    lines.append(" * only these three were judged worth compensating for. */")
    lines.append("")
    lines.append("/* Browser text selection: IA's dark.css hardcodes a fixed dark blue")
    lines.append(" * (rgba(12,41,61,0.99)), and light.css defines no ::selection at all (browser")
    lines.append(" * default, usually blue) -- both clash against a non-blue accent pack. */")
    lines.append("::selection {")
    lines.append("  background: rgba(%d,%d,%d,0.35);" % (int(ar), int(ag), int(ab)))
    lines.append("}")
    lines.append("")
    lines.append("/* Slider focus glow: .ia_slider__handle:focus hardcodes `color:")
    lines.append(" * rgba(78,188,252,0.5)` directly (IA's own stock blue) instead of reading")
    lines.append(" * --defaultSliderFocusColor the way the OTHER slider selector does -- our var")
    lines.append(" * override alone never reaches this one. Same specificity family, later in")
    lines.append(" * the cascade (this file loads after the base import), so it wins cleanly. */")
    lines.append(".ia_slider__handle:focus {")
    lines.append("  color: var(--defaultSliderFocusColor);")
    lines.append("}")
    lines.append("")
    lines.append("/* Table row hover/selection: IA hardcodes its own blue")
    lines.append(" * (rgba(12,123,179,*) / rgba(34,154,214,*)) directly on these selectors in")
    lines.append(" * BOTH themes -- tables are used constantly, so this is the highest-traffic")
    lines.append(" * hardcode found. Same selectors, same alpha steps IA itself uses, just the")
    lines.append(" * theme's own accent instead. !important because IA's own declarations here")
    lines.append(" * carry the same specificity and would otherwise win on source order alone")
    lines.append(" * inside the SAME imported stylesheet (../dark|light/index.css). */")
    lines.append(".ia_tableComponent__body__row--hovered {")
    lines.append("  background-color: rgba(%d,%d,%d,0.10) !important;" % (int(ar), int(ag), int(ab)))
    lines.append("}")
    lines.append(".ia_tableComponent__selection {")
    lines.append("  background-color: rgba(%d,%d,%d,0.25) !important;" % (int(ar), int(ag), int(ab)))
    lines.append("}")
    lines.append(".ia_alarmJournalTableComponent__selection,")
    lines.append(".ia_alarmStatusTableComponent__selection {")
    lines.append("  background-color: rgba(%d,%d,%d,0.20) !important;" % (int(ar), int(ag), int(ab)))
    lines.append("}")
    lines.append("")
    lines.append("/* Dropdown option rows: IA paints the SELECTED option with")
    lines.append(" * --callToAction--hover and the focused one with --callToAction--activeAlt,")
    lines.append(" * both under plain --label text. That pairing only reads when the accent is")
    lines.append(" * a mid-tone -- a dark-accent light theme (finance-ledger, 1.1:1) went")
    lines.append(" * ink-on-ink, and 6 of the 10 themes measured under 3:1. Repaint with the")
    lines.append(" * same accent WASH the table rows above use (same alpha steps), which keeps")
    lines.append(" * the surface/label pairing readable by construction on every theme. The")
    lines.append(" * extra ancestor class outranks IA's two-class selectors. */")
    lines.append(".ia_dropdown__optionsModal .ia_dropdown__option--focused:not(.ia_dropdown__option--selected) {")
    lines.append("  background-color: rgba(%d,%d,%d,0.10);" % (int(ar), int(ag), int(ab)))
    lines.append("  color: var(--label);")
    lines.append("}")
    lines.append(".ia_dropdown__optionsModal .ia_dropdown__option.ia_dropdown__option--selected {")
    lines.append("  background-color: rgba(%d,%d,%d,0.25);" % (int(ar), int(ag), int(ab)))
    lines.append("  color: var(--label);")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build_a11y(input_edge, focus_ring, button_text):
    return """
/* ---- accessibility (WCAG 2.1 AA) ----
 * Stock inputs take their edge from --containerBorder, the same hairline as a
 * card, which sits under 3:1 on every theme. Only the controls are raised, so
 * cards keep their light outline. */
:root {
  --a11y-input-edge: %s;
  --a11y-focus-ring: %s;
  --a11y-button-text: %s;
  --st-input-border: var(--a11y-input-edge);
}
.ia_inputField,
.ia_dropdown,
.ia_select,
.ia_textArea {
  border-color: var(--a11y-input-edge);
}

/* Stock primary buttons write --neutral-10 on the accent; on a mid-tone
 * accent that is under 4.5:1, so the build picks the text colour. */
.ia_button--primary {
  color: var(--a11y-button-text);
}

/* IA's own :focus outline is 1px of --callToAction--hover, under 3:1 on some
 * themes. Keyboard focus gets a 2px ring that clears 3:1 on every surface. */
:focus-visible {
  outline: 2px solid var(--a11y-focus-ring);
  outline-offset: 1px;
}
/* A dropdown turns its search input's outline off and marks the box instead. */
.ia_dropdown.ia_dropdown--focused,
.ia_dropdown.ia_dropdown--active {
  outline: 2px solid var(--a11y-focus-ring);
  outline-offset: 1px;
}
/* The table grid sets outline:none on itself; inset so the scroll box does
 * not clip the ring. */
.ReactVirtualized__Grid:focus-visible {
  outline: 2px solid var(--a11y-focus-ring) !important;
  outline-offset: -2px;
}

/* Honour the OS "reduce motion" setting, project alarm pulses included.
 * Near-zero rather than none so animationend/transitionend still fire. */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
""" % (input_edge, focus_ring, button_text)


# ---------------------------------------------------------------------------

def build_theme(theme):
    theme_id = theme["id"]
    label = theme["label"]
    pack_filename = theme["pack"] + ".json"

    pack_path = os.path.join(PACKS_DIR, pack_filename)
    with open(pack_path) as fh:
        pack = json.load(fh)

    is_dark = bool(pack.get("dark"))
    base_import = "../dark/index.css" if is_dark else "../light/index.css"
    color_scheme = "dark" if is_dark else "light"

    computed = {}
    resolutions = []  # (var, value, used_spec, note)

    # Pass 1: core ~35 IA vars, straight from the pack.
    for entry in MAPPING:
        value, used_spec = resolve_entry(pack, entry, computed, theme_id)
        resolutions.append((entry["var"], value, used_spec, entry["note"]))

    # TWEAKS: literal data-only overrides (only glass-green has any today).
    # Applied AFTER the pack mapping, BEFORE the extended pass and the chart
    # scales, so both see the corrected values.
    apply_tweaks(theme_id, computed, theme_id)
    # list, not set: a set of strings iterates in PYTHONHASHSEED order, which
    # makes this block's emission order differ between processes -- same
    # lines, different order, large diffs from unchanged input. The dict's
    # declared order is the deterministic one.
    tweaked_vars = list(TWEAKS.get(theme_id, {}).get("vars", {}))
    for var in tweaked_vars:
        # Replace pass-1's resolution record so variables.css's comment
        # reflects the tweak rather than the (now-overridden) pack source.
        resolutions = [r for r in resolutions if r[0] != var]
        resolutions.append((var, computed[var], "tweak:mapping.TWEAKS[%s]" % theme_id,
                             "overridden by mapping.TWEAKS -- see mapping.py for the reasoning"))

    # Before pass 2, so the symbol fills and chart poles that reuse these
    # colours pick up the corrected values.
    surfaces = [computed[v] for v in SURFACE_VARS]
    apply_contrast_floors(theme_id, computed, resolutions, TEXT_VARS, surfaces,
                          TEXT_FLOOR, is_dark, "WCAG 1.4.3")
    # Stock primary buttons put --neutral-10 on --callToAction. Keep that
    # when it passes; otherwise use white or black, whichever reads better,
    # and move the hover/pressed fills away from it until they pass too.
    button_text = computed["--neutral-10"]
    if contrast_ratio(button_text, computed["--callToAction"]) < TEXT_FLOOR:
        button_text = max(["#ffffff", "#000000"],
                          key=lambda c: contrast_ratio(c, computed["--callToAction"]))
    apply_contrast_floors(theme_id, computed, resolutions,
                          ["--callToAction--hover", "--callToAction--active"], [button_text],
                          TEXT_FLOOR, relative_luminance(button_text) < 0.5, "button text")

    # Pass 2: extended vars (controls/status/symbols/pipes/misc), can ref:
    # anything from pass 1, tweaked or not.
    for entry in EXTENDED_MAPPING:
        value, used_spec = resolve_entry(pack, entry, computed, theme_id)
        resolutions.append((entry["var"], value, used_spec, entry["note"]))

    # --border stays a hairline (dividers, menu rows, chart frames); only the
    # edges that identify a control are raised to 3:1.
    input_edge = lift_to_floor(computed["--border"], surfaces + [computed["--input"]],
                               NON_TEXT_FLOOR, is_dark)
    for var in EDGE_VARS:
        computed[var] = input_edge
    resolutions = [(v, input_edge if v in EDGE_VARS else value, spec,
                    note + " -- replaced by the 3:1 input edge (WCAG 1.4.11)" if v in EDGE_VARS else note)
                   for v, value, spec, note in resolutions]

    # Chart scales -- algorithmic, anchored on the FINAL --callToAction /
    # --error / --neutral-10 (post-tweak).
    accent = computed["--callToAction"]
    error = computed["--error"]
    page = computed["--neutral-10"]
    qual = build_qual(accent, is_dark)
    seq = build_seq(accent, is_dark)
    # Diverging scale needs two DISTINGUISHABLE poles. When the accent and
    # error hues nearly coincide (newsprint-dark: oxblood accent vs the
    # pack's masthead-red danger, ~10 degrees apart), a red<->red ramp has
    # indistinguishable ends -- swap the far pole to --info (each pack's
    # cool alarm-low blue) instead. 40 degrees circular distance threshold.
    hue_gap = abs(_hue_of(accent) - _hue_of(error)) % 1.0
    hue_gap = min(hue_gap, 1.0 - hue_gap) * 360.0
    div_pole = error if hue_gap >= 40.0 else computed["--info"]
    if div_pole is not error:
        print("NOTE [%s] div scale far pole = --info (%s): accent/error hues "
              "only %.0f degrees apart" % (theme_id, div_pole, hue_gap))
    div = build_div(accent, div_pole, page, is_dark)
    check_qual_scale(theme_id, qual, page)
    print("SWATCH [%s] qual-1..10: %s" % (theme_id, " ".join(qual)))
    for i, colour in enumerate(qual):
        computed["--qual-%d" % (i + 1)] = colour
        resolutions.append(("--qual-%d" % (i + 1), colour, "generated:colorsys",
                             "hue %d/10 rotated from --callToAction" % (i + 1)))
    for i, colour in enumerate(seq):
        computed["--seq-%d" % (i + 1)] = colour
        resolutions.append(("--seq-%d" % (i + 1), colour, "generated:colorsys",
                             "step %d/6 of the --callToAction hue, weak->strong" % (i + 1)))
    for i, colour in enumerate(div):
        computed["--div-%d" % (i + 1)] = colour
        resolutions.append(("--div-%d" % (i + 1), colour, "generated:colorsys",
                             "step %d/16 of the accent<->error diverging ramp" % (i + 1)))

    theme_dir = os.path.join(OUT_DIR, theme_id)
    os.makedirs(theme_dir, exist_ok=True)

    # config.json
    config = {"entrypoint": "index.css", "isPrivate": False}
    with open(os.path.join(theme_dir, "config.json"), "w") as fh:
        json.dump(config, fh, indent=2)
        fh.write("\n")

    # index.css -- imports only, this exact order (later imports win cascade).
    # Base import follows the PACK's own "dark" flag, not an assumption.
    index_css = (
        '@import "%s";\n'
        '@import "./variables.css";\n'
        '@import "./globals.css";\n'
    ) % base_import
    with open(os.path.join(theme_dir, "index.css"), "w") as fh:
        fh.write(index_css)

    # variables.css
    width = max(len(var) for var, _, _, _ in resolutions)
    lines = [
        "/* GENERATED by build_theme.py -- DO NOT EDIT BY HAND.",
        " * Theme: %s (%s). Source pack: packs/%s." % (theme_id, label, pack_filename),
        " * mapping.MAPPING + mapping.EXTENDED_MAPPING%s + colorsys chart scales. */"
        % (" + mapping.TWEAKS[%r]" % theme_id if theme_id in TWEAKS else ""),
        ":root {",
        "  color-scheme: %s; /* this pack declares \"dark\": %s --" % (
            color_scheme, "true" if is_dark else "false"),
        "                         workspace standing rule, see repo CLAUDE.md */",
        "",
    ]
    for var, value, used_spec, note in resolutions:
        comment = "%s (%s)" % (note, used_spec)
        emitted = emit_value(var, value, pack)
        if emitted != value:
            comment += " -- IA reads this as a shorthand"
        lines.append("  %-*s %s; /* %s */" % (width + 1, var + ":", emitted, comment))
    lines.append("}")
    variables_css = "\n".join(lines) + "\n"
    with open(os.path.join(theme_dir, "variables.css"), "w") as fh:
        fh.write(variables_css)

    # globals.css
    globals_tweak = TWEAKS.get(theme_id, {}).get("globals")
    globals_css = build_globals(pack, computed["--containerRoot"], globals_tweak,
                            computed["--containerBorder"], computed["--callToAction"],
                            computed["--callToAction"])
    # The Styles_Template2 compatibility payload, when this pack has been
    # vendored under contract/. It is what lets a consumer drop the styles
    # parent rather than only inherit its colours -- see build_contract.py.
    # Appended rather than woven in: everything above is this repo's own
    # generated theme, everything below is the contract it now also carries,
    # and a reader (or a diff) can tell them apart at a glance.
    contract_css = build_contract(pack["id"])
    globals_css += contract_css
    # The table grid's ring is drawn inset, over the contract's table surfaces.
    ring_surfaces = list(surfaces)
    for var in ("--st-table-bg", "--st-head-solid"):
        m = re.search(r"%s:\s*([^;]+);" % var, contract_css)
        if m and parse_colour(m.group(1)):
            ring_surfaces.append(flatten(m.group(1), computed["--containerRoot"]))
    focus_ring = lift_to_floor(computed["--callToAction"], ring_surfaces, NON_TEXT_FLOOR, is_dark)
    # After the contract, so its :root --st-input-border is the one replaced.
    globals_css += build_a11y(input_edge, focus_ring, button_text)
    with open(os.path.join(theme_dir, "globals.css"), "w") as fh:
        fh.write(globals_css)

    # resource.json -- NO lastModification / lastModificationSignature: the
    # config-resource stamp trap means a hand-written signature that doesn't
    # match content makes the gateway silently skip this resource on every
    # scan. The gateway must stamp it itself on first scan.
    resource = {
        "scope": "G",
        "description": "%s theme (from packs/%s%s). See README.md." % (
            label, pack_filename, ", tweaked -- see mapping.TWEAKS" if theme_id in TWEAKS else ""),
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": ["config.json", "index.css", "variables.css", "globals.css"],
    }
    with open(os.path.join(theme_dir, "resource.json"), "w") as fh:
        json.dump(resource, fh, indent=2)
        fh.write("\n")

    print("wrote %s (%s): %s, base=%s, source=packs/%s, %d vars, %d bytes variables.css, %d bytes globals.css"
          % (theme_id, label, color_scheme, base_import, pack_filename, len(resolutions),
             len(variables_css), len(globals_css)))
    return theme_dir, {"id": theme_id, "label": label, "dark": is_dark,
                        "source_pack": theme["pack"],
                        "family": theme.get("family"), "pair": theme.get("pair")}


def main():
    if not os.path.isdir(PACKS_DIR):
        raise SystemExit("FATAL: packs dir not found: %s" % PACKS_DIR)
    # Wipe and rebuild out/ from scratch every run, so a rename (like this
    # one) can never leave a stale directory under an old theme id.
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    written = []
    labels = []
    for theme in THEMES:
        theme_dir, label_entry = build_theme(theme)
        written.append(theme_dir)
        labels.append(label_entry)

    themes_json_path = os.path.join(OUT_DIR, "themes.json")
    with open(themes_json_path, "w") as fh:
        json.dump(labels, fh, indent=2)
        fh.write("\n")

    # out/palettes.json -- theme id -> the seven chart roles. Charts are the one
    # thing a theme cannot carry as CSS, because Chart.js takes literal colours
    # in its options and cannot read a custom property. A consumer's script
    # library reads this instead of the parent's styles.chart_palette(), which
    # walked the style-class files on the project tree and so needed a parent.
    palettes = {}
    for theme in THEMES:
        palette = build_palette(theme["pack"])
        if palette:
            palettes[theme["id"]] = palette
    with open(os.path.join(OUT_DIR, "palettes.json"), "w") as fh:
        json.dump(palettes, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("wrote palettes.json (%d themes)" % len(palettes))

    print("\n%d warning(s) total" % len(WARNINGS))
    print("wrote %d theme(s) + themes.json under %s" % (len(written), OUT_DIR))


if __name__ == "__main__":
    main()
