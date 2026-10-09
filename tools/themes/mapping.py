"""Curated token -> IA Perspective theme-variable mapping.

This is NOT part of the packs/families source-of-truth pipeline (see repo
CLAUDE.md's "the one rule") and is never read by tools/build_all.py. It
delivers 9 curated packs as gateway *themes* -- see
README.md. The mapping table itself is pack-agnostic: it
was proven against 2 packs (aurora-violet, leather-night-tan) and now runs
unchanged across all 9, light and dark alike -- flatten() and every other
transform here are direction-agnostic, they just composite colours.

Each entry describes how to derive ONE built-in Perspective theme custom
property from a pack's own tokens/overrides/variants. `build_theme.py` is the
only consumer of this module; it walks MAPPING in order (order matters --
later entries may `ref:` an earlier `--var` that must already be resolved)
and applies the transform named in `transform`.

Source-spec mini-DSL (each item in `sources` is tried in order until one
resolves to a non-None value; the first successful one wins and, if it is not
the first item, or the chain bottoms out at a `literal:`, build_theme.py logs
a WARNING):

    "token:<key>"                       pack["tokens"][<key>]
    "variant:<classpath>:<pseudo>:<prop>"
                                         pack["variants"][<classpath>] ->
                                         the entry whose "pseudo" == <pseudo>
                                         -> its "style"[<prop>]
    "literal:<value>"                   a constant, used only as a last-resort
                                         fallback (e.g. "literal:none" for a
                                         pack that defines no shadow token)
    "ref:--<name>"                      the ALREADY-COMPUTED value of another
                                         entry in this same mapping (must
                                         appear earlier in MAPPING)

`behind` is a single source-spec (same DSL, no fallback list) used as the
opaque background for the `flatten` transform. `None` means "flatten against
plain white" (matches tools/build_css.py's flatten() default). In practice
almost everything here flattens over `ref:--containerRoot` (the pack's own
page colour, itself flattened over white) because both packs' non-page
surfaces are translucent rgba() meant to sit on the page -- see the plan's
"What exploration established" notes.

Transforms:
    "flatten"     composite the resolved colour over `behind` -> opaque hex.
                  If the resolved value cannot be parsed as a colour (e.g. a
                  gradient string sneaking in through a wrong lookup), this
                  counts as UNRESOLVED and the next source in the fallback
                  chain is tried -- it does not silently fall through to
                  `behind`.
    "literal"     pass the resolved value through unchanged (radius px
                  values, shadow strings, font stacks, "none").
    "alpha:<X>"   parse the resolved value as a colour and re-emit it as
                  "rgba(r,g,b,X)" -- used for *--disabled slots so they stay
                  legibly related to their non-disabled sibling rather than
                  inventing a new colour.
    "darken:<X>"  parse the resolved value as a colour, multiply each channel
                  toward 0 by X (0..1), re-emit as opaque hex -- used only for
                  --callToAction--active, since neither pack declares a
                  distinct :active state.

Chart scales (--qual-1..10, --seq-1..6, --div-1..16) are NOT in this DSL --
no pack defines a 10/16/6-step scale for these to read from, and the whole
point is to generate one algorithmically per theme (colorsys, anchored at
the theme's own accent/error hues). That needs real code, not a token
lookup, so it lives in `build_theme.py`'s `build_chart_scales()` instead.
It runs AFTER both MAPPING and EXTENDED_MAPPING (and any TWEAKS) have been
resolved, reading the final --callToAction/--error/--neutral-10, so a
tweaked theme's chart scale is anchored on its tweaked accent, not the raw
pack's.

EXTENDED_MAPPING (below MAPPING) covers the rest of the live IA variable
surface that IS a straightforward derivation from vars already computed by
MAPPING -- controls, the neutral midtones, status-secondary washes, symbols,
pipes, a few misc. Same DSL, same engine, just resolved in a SECOND pass
after MAPPING so it can `ref:` anything MAPPING produced (including a
TWEAKS-overridden value -- see TWEAKS below). Two additions to the
DSL/transform vocabulary for this pass:
    "inset"        for --boxShadow--inset: prefix "inset " onto the resolved
                   shadow value, or pass "none" through unchanged.
    "lerp:<t>:<ref>" linearly interpolate the entry's own resolved colour
                   toward `ref`'s already-computed value by t (0..1) --
                   used for the --neutral-40/50/60/70/80 midtones, which no
                   pack token supplies.

GROUND TRUTH: the live gateway's flattened dark.css/light.css define exactly
120 unique custom properties each (audited via
curl http://<gw>/data/perspective/themes/{dark,light}.css, every
`--name: value;` enumerated). MAPPING + EXTENDED_MAPPING + the chart-scale
generator together cover all 120 except the 11 documented below as
deliberately out of scope. The real CSS confirms `--checkbox--*`,
`--radio--selected/--unselected/--disabled` (not `--checked`/`--unchecked`/
`--indeterminate` -- there is no `--radio--indeterminate`),
`--toggleSwitch--selected/--unselected` (not `--on`/`--off`, and there is no
`--toggleSwitch--disabled`), and `--progressLinearBar--*` /
`--progressLinearTrack--*`. `--tooltip-background-color` and `--arrow-color`
are also real, and IA's own theme CSS never defines either of them anywhere
(they're referenced via `var()` in `.ia_form__tooltip-*` rules with no
`:root` value at all) -- our themes are the only thing giving those two a
colour.

TWEAKS (below EXTENDED_MAPPING) is a per-theme-id table of LITERAL
overrides applied to `computed` after MAPPING resolves but BEFORE
EXTENDED_MAPPING and the chart scales run -- so a tweaked accent/page
correctly propagates into every derived var downstream (checkboxes, chart
hues, symbols, …) without re-deriving anything by hand. It exists so a
theme whose SOURCE PACK has a known defect (aurora-teal's page/surface
tokens are copy-pasted from aurora-violet and never diverged -- see
glass-green's entry) can be corrected here, as DATA, with the pack file
itself left untouched. `glass-violet` (and every other theme) has no
TWEAKS entry and passes through MAPPING unmodified.

Deliberately NOT mapped anywhere in this file (documented gap, see README):
--white, --black, --font-NotoSans, --opacity-*, --red-* -- explicitly out of
scope; these are left exactly as `../dark/index.css` or `../light/index.css`
defines them.
"""

# Every flatten below composites against the pack's OWN page colour, not a
# fixed white -- see module docstring. Kept as a named constant so entries
# read declaratively instead of repeating the same ref string 20+ times.
PAGE = "ref:--containerRoot"

MAPPING = [
    # ---- neutrals + containers ---------------------------------------
    # containerRoot and --neutral-10 are the SAME derivation (the page
    # colour itself, flattened over white since surface.page is opaque in
    # both packs anyway). containerRoot is computed first because every
    # other flatten in this table uses it as `behind`.
    {
        "var": "--containerRoot",
        "sources": ["token:surface.page"],
        "transform": "flatten",
        "behind": None,
        "note": "page background, flattened over white (defines PAGE for everything below)",
    },
    {
        "var": "--neutral-10",
        "sources": ["token:surface.page"],
        "transform": "flatten",
        "behind": None,
        "note": "same derivation as --containerRoot (literal reuse)",
    },
    {
        "var": "--container",
        "sources": ["token:surface.card"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "card surface flattened over the page",
    },
    {
        "var": "--neutral-20",
        "sources": ["token:surface.card"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "same derivation as --container (literal reuse)",
    },
    {
        "var": "--containerNested",
        "sources": ["token:surface.kpi-tile"],
        "transform": "flatten",
        "behind": "ref:--container",
        "note": "a tile/nested-card surface flattened over --container (one level deeper than a card)",
    },
    {
        "var": "--containerBorder",
        "sources": ["token:border.card"],
        "transform": "flatten",
        "behind": "ref:--container",
        "note": "card border flattened over --container",
    },

    # ---- borders / inputs ----------------------------------------------
    {
        "var": "--border",
        "sources": ["token:border.input", "token:border.primary"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "input border flattened over the page",
    },
    {
        "var": "--border--disabled",
        "sources": ["ref:--border"],
        "transform": "alpha:0.5",
        "behind": None,
        "note": "half-opacity --border (no separate disabled-border token in either pack)",
    },
    {
        "var": "--input",
        "sources": ["token:surface.input"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "input surface flattened over the page",
    },
    {
        "var": "--input--disabled",
        "sources": ["token:surface.ghost", "ref:--input"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "ghost surface (the packs' own muted-control colour) flattened over the page; several packs declare surface.ghost as the keyword \"transparent\" (unparsable as a colour), which falls back to --input itself",
    },

    # ---- text / label / icon --------------------------------------------
    {
        "var": "--label",
        "sources": ["token:text.body"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "body text colour",
    },
    {
        "var": "--neutral-90",
        "sources": ["token:text.body"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "same derivation as --label (literal reuse)",
    },
    {
        "var": "--label--disabled",
        "sources": ["token:text.muted"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "muted text colour",
    },
    {
        "var": "--neutral-100",
        "sources": ["token:text.heading"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "heading ink (lightest/most emphatic text colour)",
    },
    {
        "var": "--icon",
        "sources": ["token:text.body"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "reuses body text colour -- neither pack declares a distinct icon ink",
    },
    {
        "var": "--icon--hover",
        "sources": ["token:accent.primary"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "accent colour on hover",
    },
    {
        "var": "--icon--selected",
        "sources": ["ref:--icon--hover"],
        "transform": "literal",
        "behind": None,
        "note": "same as --icon--hover (literal reuse; no distinct selected-icon token)",
    },
    {
        "var": "--icon--disabled",
        "sources": ["ref:--label--disabled"],
        "transform": "alpha:0.6",
        "behind": None,
        "note": "muted text colour at reduced alpha",
    },

    # ---- call to action ---------------------------------------------------
    {
        "var": "--callToAction",
        "sources": ["token:accent.primary"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "primary accent colour",
    },
    {
        "var": "--callToAction--hover",
        "sources": [
            "variant:buttons/primary:hover:backgroundColor",
            "token:accent.progress",
            "ref:--callToAction",
        ],
        "transform": "flatten",
        "behind": PAGE,
        "note": "the pack's own buttons/primary:hover colour when it declares a solid one, else its secondary accent, else --callToAction itself",
    },
    {
        "var": "--callToAction--active",
        "sources": ["ref:--callToAction"],
        "transform": "darken:0.15",
        "behind": None,
        "note": "--callToAction darkened 15% -- neither pack declares a distinct :active state",
    },
    {
        "var": "--callToAction--disabled",
        "sources": ["ref:--callToAction"],
        "transform": "alpha:0.35",
        "behind": None,
        "note": "--callToAction at reduced alpha",
    },
    {
        "var": "--callToActionHighlight",
        "sources": ["token:surface.nav-active"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "the pack's own active-nav wash, flattened over the page",
    },

    # ---- status colours -----------------------------------------------
    {
        # IA paints --error as INK -- alarm text, error labels, invalid-input
        # messages -- so it has to read against the card it sits on, and
        # `accent.danger` cannot be trusted to be that. The token means three
        # different things across the packs: the danger colour (nord-light,
        # both glass packs, both leather packs), the INK ON a danger fill
        # (finance-ledger and industrial-light both set it #ffffff, which
        # landed white-on-white), and a 12% background WASH (industrial-dark's
        # rgba(255,77,77,.12), flattening to #251317 on its own near-black
        # page at 1.03:1).
        #
        # So the chain is gated on legibility rather than existence: each
        # candidate must clear 3:1 against --container or the resolver falls
        # through to the next. `border.danger` is the reliable second -- every
        # pack carries it and a border colour is ink-grade by construction --
        # and it is `transparent` in exactly the packs whose accent.danger was
        # already right, so it is skipped there rather than preferred.
        #
        # accent.alarm-high is LAST, not second, because it is the amber/orange
        # high-priority alarm colour in the industrial packs (#D97706, #F6B93B)
        # and an error rendered as a warning is worse than one that is merely
        # dim.
        #
        # The min:3.0 gate is why order matters here: a theme whose
        # accent.danger already clears 3:1 keeps it, while one that doesn't
        # falls through to border.danger or accent.alarm-high instead of
        # emitting an illegible colour.
        "var": "--error",
        "sources": ["token:accent.danger", "token:border.danger",
                    "token:accent.alarm-high"],
        "transform": "flatten",
        "behind": PAGE,
        "require": {"contrast_with": "ref:--container", "min": 3.0},
        "note": "danger accent -- first candidate legible as ink on a card",
    },
    {
        "var": "--warning",
        "sources": ["token:accent.alarm-med"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "medium-priority alarm colour",
    },
    {
        "var": "--success",
        "sources": ["token:accent.delta-up", "token:text.status-ok"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "positive-delta accent (falls back to the OK status text colour)",
    },
    {
        "var": "--info",
        "sources": ["token:accent.alarm-low"],
        "transform": "flatten",
        "behind": PAGE,
        "note": "low-priority alarm colour",
    },

    # ---- radius ----------------------------------------------------------
    {
        "var": "--borderRadius",
        "sources": ["token:radius.control"],
        "transform": "literal",
        "behind": None,
        "note": "control radius",
    },
    {
        "var": "--borderRadiusInput",
        "sources": ["token:radius.control"],
        "transform": "literal",
        "behind": None,
        "note": "same as --borderRadius (literal reuse; neither pack declares a separate input radius)",
    },

    # ---- elevation ---------------------------------------------------------
    # Both packs define at most ONE elevation shadow (shadow.card); leather
    # defines none at all (its overrides null out every boxShadow -- "reads
    # as a book, not a dashboard"). Documented gap: one value reused across
    # all five --boxShadow slots, see README.
    {
        "var": "--boxShadow1",
        "sources": ["token:shadow.card", "literal:none"],
        "transform": "literal",
        "behind": None,
        "note": "the pack's one elevation shadow, reused across all 5 slots",
    },
    {
        "var": "--boxShadow2",
        "sources": ["token:shadow.card", "literal:none"],
        "transform": "literal",
        "behind": None,
        "note": "same as --boxShadow1 (literal reuse)",
    },
    {
        "var": "--boxShadow3",
        "sources": ["token:shadow.card", "literal:none"],
        "transform": "literal",
        "behind": None,
        "note": "same as --boxShadow1 (literal reuse)",
    },
    {
        "var": "--boxShadow4",
        "sources": ["token:shadow.card", "literal:none"],
        "transform": "literal",
        "behind": None,
        "note": "same as --boxShadow1 (literal reuse)",
    },
    {
        "var": "--boxShadow5",
        "sources": ["token:shadow.card", "literal:none"],
        "transform": "literal",
        "behind": None,
        "note": "same as --boxShadow1 (literal reuse)",
    },
]


# ---------------------------------------------------------------------------
# EXTENDED_MAPPING -- resolved in a second pass, after MAPPING + TWEAKS, so
# every `ref:` here can see the FINAL (possibly tweaked) value. See module
# docstring for the naming-confidence caveat on --radio--*/--toggleSwitch--*/
# --progressLinearTrack--*.
# ---------------------------------------------------------------------------

EXTENDED_MAPPING = [
    # ---- neutral midtones (--neutral-40/50/60/70/80) --------------------
    # These 5 steps are NOT mere indirection behind vars we already cover --
    # ~98 component rules across the two files reference them DIRECTLY
    # (icon fills/strokes, secondary text, hairline borders, SVG symbol
    # strokes, …), so leaving them unthemed left a large swath of secondary
    # chrome rendering in IA's own stock grey regardless of pack. No pack
    # token supplies 5 more neutral steps, so these are INTERPOLATED (RGB
    # lerp, evenly spaced) between the two neutrals every pack already
    # supplies -- --neutral-30 (a "sunken" tone) and --neutral-90 (ink) --
    # rather than a fixed pack-independent grey ramp, so the midtones keep
    # whatever tint the pack's own neutrals carry (e.g. glass-green's stay
    # green-grey, not a flat desaturated grey). New transform: "lerp:<t>:<ref>"
    # -- lerps the entry's own resolved colour toward `ref`'s value by t.
    # The ramp anchors on --neutral-10 (page) -> --neutral-90 (ink), NOT on the
    # pack's sidebar tone: a pack may legitimately pair a light page with a dark
    # contrast sidebar (finance-ledger does), and anchoring there inverted the
    # midtones -- hairlines and icon fills came out near-ink on a light page.
    # t values follow IA's own perceptual spacing (light.css: 250->50 grey ramp).
    {"var": "--neutral-30", "sources": ["ref:--neutral-10"],
     "transform": "lerp:0.11:--neutral-90", "behind": None,
     "note": "subtle sunken surface tone, 11% from page toward ink (IA neutral-30 spacing)"},
    {"var": "--neutral-40", "sources": ["ref:--neutral-10"],
     "transform": "lerp:0.30:--neutral-90", "behind": None,
     "note": "30% from page toward ink (IA neutral-40 spacing; no pack token for this step)"},
    {"var": "--neutral-50", "sources": ["ref:--neutral-10"],
     "transform": "lerp:0.44:--neutral-90", "behind": None,
     "note": "44% from page toward ink (IA neutral-50 spacing; no pack token for this step)"},
    {"var": "--neutral-60", "sources": ["ref:--neutral-10"],
     "transform": "lerp:0.66:--neutral-90", "behind": None,
     "note": "66% from page toward ink (IA neutral-60 spacing; no pack token for this step)"},
    {"var": "--neutral-70", "sources": ["ref:--neutral-10"],
     "transform": "lerp:0.78:--neutral-90", "behind": None,
     "note": "78% from page toward ink (IA neutral-70 spacing; no pack token for this step)"},
    {"var": "--neutral-80", "sources": ["ref:--neutral-10"],
     "transform": "lerp:0.85:--neutral-90", "behind": None,
     "note": "85% from page toward ink (IA neutral-80 spacing; no pack token for this step)"},

    # ---- checkbox / radio (live-verified var family; radio inferred by
    # symmetry with it -- see docstring) ---------------------------------
    {"var": "--checkbox--checked", "sources": ["ref:--callToAction"],
     "transform": "literal", "behind": None, "note": "reuses --callToAction"},
    {"var": "--checkbox--unchecked", "sources": ["ref:--border"],
     "transform": "literal", "behind": None, "note": "reuses --border"},
    {"var": "--checkbox--indeterminate", "sources": ["ref:--callToAction"],
     "transform": "literal", "behind": None,
     "note": "same accent tone as --checkbox--checked (no pack distinguishes an indeterminate colour)"},
    {"var": "--checkbox--disabled", "sources": ["ref:--border--disabled"],
     "transform": "literal", "behind": None, "note": "reuses --border--disabled"},

    {"var": "--radio--selected", "sources": ["ref:--callToAction"],
     "transform": "literal", "behind": None, "note": "reuses --callToAction (the real var is --radio--selected, not --radio--checked)"},
    {"var": "--radio--unselected", "sources": ["ref:--border"],
     "transform": "literal", "behind": None, "note": "reuses --border (the real var is --radio--unselected, not --radio--unchecked)"},
    {"var": "--radio--disabled", "sources": ["ref:--border--disabled"],
     "transform": "literal", "behind": None, "note": "reuses --border--disabled"},
    # NOTE: there is no --radio--indeterminate in IA's real var set. Dropped,
    # not renamed.

    # ---- toggle switch (the real vars are --toggleSwitch--selected/
    # --unselected, not --toggleSwitch--on/off) ----------------------------
    {"var": "--toggleSwitch--selected", "sources": ["ref:--callToAction"],
     "transform": "literal", "behind": None, "note": "reuses --callToAction"},
    {"var": "--toggleSwitch--unselected", "sources": ["ref:--border"],
     "transform": "literal", "behind": None, "note": "reuses --border"},
    # NOTE: there is no --toggleSwitch--disabled in IA's real var set either
    # (a disabled toggle is presumably done with opacity/filter, not a
    # themed colour) -- dropped, not renamed.

    # ---- progress bars ----------------------------------------------------
    {"var": "--progressLinearBar--determinate", "sources": ["ref:--callToAction"],
     "transform": "literal", "behind": None, "note": "reuses --callToAction"},
    {"var": "--progressLinearBar--indeterminate", "sources": ["ref:--callToAction"],
     "transform": "literal", "behind": None,
     "note": "same accent tone as the determinate bar; IA's indeterminate animation reuses one colour, not a second one"},
    {"var": "--progressLinearTrack--determinate", "sources": ["token:surface.progress-track", "ref:--containerBorder"],
     "transform": "flatten", "behind": PAGE,
     "note": "the pack's own progress-track surface flattened over the page (name inferred by symmetry, see docstring)"},
    {"var": "--progressLinearTrack--indeterminate", "sources": ["ref:--progressLinearTrack--determinate"],
     "transform": "literal", "behind": None,
     "note": "same as the determinate track (name inferred by symmetry, see docstring)"},

    # ---- status secondaries (tinted washes, not opaque) --------------------
    {"var": "--warningSecondary", "sources": ["ref:--warning"],
     "transform": "alpha:0.16", "behind": None, "note": "--warning as a low-opacity wash"},
    {"var": "--infoSecondary", "sources": ["ref:--info"],
     "transform": "alpha:0.16", "behind": None, "note": "--info as a low-opacity wash"},

    # ---- symbols (P&ID / SCADA symbol library states) -----------------
    {"var": "--symbolFill--default", "sources": ["ref:--container"],
     "transform": "literal", "behind": None, "note": "reuses --container (idle/neutral tone)"},
    {"var": "--symbolFill--running", "sources": ["ref:--success"],
     "transform": "literal", "behind": None, "note": "reuses --success"},
    {"var": "--symbolFill--faulted", "sources": ["ref:--error"],
     "transform": "literal", "behind": None, "note": "reuses --error"},
    {"var": "--symbolFill--stopped", "sources": ["ref:--label--disabled"],
     "transform": "literal", "behind": None, "note": "reuses --label--disabled (muted ink)"},
    {"var": "--symbolStroke--default", "sources": ["ref:--containerBorder"],
     "transform": "literal", "behind": None, "note": "reuses --containerBorder"},
    {"var": "--symbolStroke--running", "sources": ["ref:--success"],
     "transform": "darken:0.2", "behind": None, "note": "--success darkened 20% for a visible outline against its own fill"},
    {"var": "--symbolStroke--faulted", "sources": ["ref:--error"],
     "transform": "darken:0.2", "behind": None, "note": "--error darkened 20% for a visible outline against its own fill"},
    {"var": "--symbolStroke--stopped", "sources": ["ref:--label--disabled"],
     "transform": "darken:0.2", "behind": None, "note": "--label--disabled darkened 20% for a visible outline against its own fill"},

    # ---- pipes (native Perspective pipe rendering) ---------------------
    {"var": "--pipeStroke", "sources": ["ref:--border"],
     "transform": "literal", "behind": None, "note": "reuses --border"},
    {"var": "--pipePrimaryFill", "sources": ["ref:--label--disabled"],
     "transform": "literal", "behind": None, "note": "reuses --label--disabled (muted ink -- an inactive/unqualified pipe)"},
    {"var": "--pipeSecondaryFill", "sources": ["ref:--containerNested"],
     "transform": "literal", "behind": None, "note": "reuses --containerNested (a differentiated neutral tone)"},
    {"var": "--pipeSelectStroke", "sources": ["ref:--callToAction"],
     "transform": "literal", "behind": None, "note": "reuses --callToAction (selection highlight)"},

    # ---- misc ------------------------------------------------------------
    {"var": "--tooltip-background-color", "sources": ["ref:--containerNested"],
     "transform": "literal", "behind": None, "note": "reuses --containerNested (a raised-above-card tone)"},
    {"var": "--boxShadow--inset", "sources": ["ref:--boxShadow1"],
     "transform": "inset", "behind": None,
     "note": "--boxShadow1 turned into an inset shadow (or \"none\" unchanged, for packs with no shadow token)"},
    {"var": "--arrow-color", "sources": ["ref:--icon"],
     "transform": "literal", "behind": None, "note": "reuses --icon"},

    # ---- vars found uncovered against the live flattened dark.css/light.css
    # -- each one confirmed to drive something visible (grep for `var(--x)`
    # in the actual component rules). ------------------------------------
    {"var": "--indicator", "sources": ["ref:--success"],
     "transform": "literal", "behind": None,
     "note": "reuses --success -- drives the LED component's \"on\" diode fill AND the quality-overlay \"pending\" state (IA's own dark.css uses a bright green for both, same semantic fit)"},
    {"var": "--indicatorOff", "sources": ["ref:--indicator"],
     "transform": "darken:0.85", "behind": None,
     "note": "--indicator darkened 85% -- the LED component's \"off\" diode fill; IA's own indicatorOff is a near-black shade of indicator's own hue, same ratio applied here"},
    {"var": "--contextBackground", "sources": ["ref:--containerNested"],
     "transform": "literal", "behind": None,
     "note": "reuses --containerNested -- the right-click context-menu background. IA hardcodes this to --black in BOTH its light and dark themes, which is a real contrast bug for a light pack: the context menu's own text uses --label (dark ink on a light theme), so a literal black background would be near-illegible. --containerNested keeps it in the theme's own surface family and pairs correctly with --label either way"},
    {"var": "--defaultSliderFocusColor", "sources": ["ref:--callToAction"],
     "transform": "alpha:0.5", "behind": None,
     "note": "--callToAction at IA's own 0.5 alpha -- the slider handle's focus glow. Reaches the ALTERNATE slider selector that actually consumes this var via var(); the PRIMARY .ia_slider__handle:focus selector hardcodes its own colour instead (see README's hard-coded-colour audit) and needs a compensating rule in globals.css, not a var override, to pick this up"},
    {"var": "--callToAction--activeAlt", "sources": ["ref:--callToActionHighlight"],
     "transform": "literal", "behind": None,
     "note": "reuses --callToActionHighlight -- IA's own activeAlt (#093952) and callToActionHighlight (#0C2938) are both dark, similarly-saturated accent washes used for different components' pressed/focused feedback (a dropdown option's focus background, a split-container handle's active-drag background); close enough in IA's own values that one derivation covers both meaningfully"},
    {"var": "--callToAction--activeAltInvis", "sources": ["ref:--callToAction--hover"],
     "transform": "literal", "behind": None,
     "note": "reuses --callToAction--hover -- IA's own activeAltInvis (#0A6291) sits roughly midway between callToAction and callToActionHighlight in lightness; --callToAction--hover is already a mid-tone lighter accent in this generator and is the closest existing derived value without inventing a new blend"},
    {"var": "--symbolFillAnimation--default", "sources": ["ref:--neutral-80"],
     "transform": "literal", "behind": None,
     "note": "reuses the newly-interpolated --neutral-80 -- a symbol flow/pulse animation overlay; IA's own value is identical to its own --neutral-80"},
    {"var": "--symbolFillAnimation--running", "sources": ["ref:--neutral-80"],
     "transform": "literal", "behind": None,
     "note": "same as --symbolFillAnimation--default -- IA defines both with the identical value"},
]


# ---------------------------------------------------------------------------
# TWEAKS -- per-theme-id literal overrides, DATA not code. Applied to
# `computed` right after MAPPING resolves (before EXTENDED_MAPPING and the
# chart-scale generator run), so a tweaked accent/page correctly propagates
# downstream. Only "vars" (theme custom properties) and "globals"
# (background-image/background-color for globals.css) may be overridden.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Variables IA consumes as a CSS SHORTHAND rather than as a colour.
#
# Ignition's own Perspective CSS says, in 85 separate rules:
#
#     .ia_inputField { border: var(--containerBorder); ... }
#
# so --containerBorder has to hold `1px solid <colour>`, not `<colour>`. A bare
# colour makes every one of those 85 declarations invalid at once and the
# borders simply vanish -- inputs, dropdowns, buttons, alarm tables, accordions,
# dashboard tiles. On a light theme a text field is then white on a white card
# with nothing to say where it is. All six stock IA themes hold the shorthand,
# and this emit-time step is what makes these ten do the same.
#
# Counted against a SERVED theme (8.3.8, /data/perspective/themes/dark.css, 83 KB
# -- the Perspective module bundle itself has only one of the 85; the rest come
# from the theme base). All 85 are `border` (32) or `border-top`/`-bottom`/
# `-left`/`-right` (53), and in every one the variable is the ENTIRE value.
# There is no `border-color: var(--containerBorder)` anywhere, which is what
# makes emitting a shorthand safe rather than a trade -- checked, not assumed.
#
# This is applied at EMIT time, not in the mapping, because computed[] must keep
# the bare colour: --symbolStroke--default and --progressLinearTrack--determinate
# both `ref:--containerBorder` and need something a `stroke` can take, and
# build_globals() is handed it as a colour too. So the variable is written as a
# shorthand and used internally as a colour.
#
# The width comes from the pack's own border.width rather than a hardcoded 1px,
# so a pack that wants heavier chrome gets it. Every pack says 1px today.
SHORTHAND_VARS = {
    "--containerBorder": {"style": "solid", "width_token": "border.width",
                          "width_default": "1px"},
}


TWEAKS = {
    "newsprint-dark": {
        # newsprint-night's accent.primary is the literal same value as
        # text.body (#e8e2d6), so the pack is deliberately monochrome --
        # handsome, but --callToAction gives ZERO separation between an
        # action and the surface it sits on.
        # Fix is an OXBLOOD accent, chosen over navy so it suits the
        # ink-and-paper character while staying clearly apart from BOTH the
        # pack's own masthead-red danger (#c23b3b, kept danger-only) and
        # finance-ledger's navy (its declared light counterpart). Source
        # pack untouched -- Styles_Template2 consumers keep the monochrome.
        # --callToAction--hover MUST be overridden here: its mapping falls
        # back to accent.progress, which this pack sets to the danger red.
        # Everything accent-derived downstream (controls, indicator, slider
        # focus, qual/seq scales) re-anchors on these automatically.
        "vars": {
            "--callToAction": "#b1554a",
            "--callToAction--hover": "#c26a5e",
            "--callToAction--active": "#96453c",
            "--callToAction--disabled": "rgba(177,85,74,0.35)",
            "--callToActionHighlight": "#3a2a25",
            "--icon--hover": "#b1554a",
        },
    },
    "glass-green": {
        # aurora-teal (the source pack for glass-green) still LOOKS like
        # aurora-violet with a teal accent swapped in. Root cause: aurora-teal's
        # surface.page/surface.card/surface.sidebar/... tokens were never
        # diverged from aurora-violet when the teal pack was cloned -- both
        # packs' tokens["surface.page"] are the literal string "#1a1233"
        # (violet). Only the accent/chart-adjacent tokens (accent.primary,
        # accent.progress, surface.nav-active, the containers/page override)
        # actually changed. tools/build_css.py's stylesheet output never
        # showed this because IT reads containers/page's EFFECTIVE
        # backgroundColor override (#091b1b, already a dark teal) rather
        # than the raw surface.page token -- this generator's MAPPING reads
        # the raw token instead (see MAPPING's --containerRoot entry), which
        # is what let the violet leak through into a THEME specifically.
        #
        # Fix is 100% here, not in packs/aurora-teal.json (untouched): a
        # full green surface stack recomputed from a new dark near-black
        # green-tinted base (#0d1412) using THIS FILE's own flatten() over
        # the SAME translucent white-glass alpha values the pack already
        # declares for its cards/inputs/sidebar/borders (rgba(255,255,255,
        # 0.06/0.08/0.10/0.14/0.22)) -- the glass EFFECT is untouched, only
        # what it now sits on. Accent moved from the pack's own muted teal
        # (#0f766e) to a brighter mint. Every value below was computed with
        # the exact same parse_colour()/flatten() this generator uses --
        # nothing here is eyeballed.
        "vars": {
            "--containerRoot": "#0d1412",
            "--neutral-10": "#0d1412",
            "--container": "#252c2a",
            "--neutral-20": "#252c2a",
            "--containerNested": "#3b413f",
            "--containerBorder": "#555a59",
            "--border": "#424846",
            "--border--disabled": "rgba(66,72,70,0.5)",
            "--input": "#202725",
            "--input--disabled": "#1c2220",
            "--label": "#eefcf6",
            "--neutral-90": "#eefcf6",
            "--label--disabled": "#7b9389",
            "--neutral-100": "#f6fff9",
            "--icon": "#eefcf6",
            "--icon--hover": "#2dd4bf",
            "--icon--selected": "#2dd4bf",
            "--icon--disabled": "rgba(123,147,137,0.6)",
            "--callToAction": "#2dd4bf",
            "--callToAction--hover": "#5eead4",
            "--callToAction--active": "#26b4a2",
            "--callToAction--disabled": "rgba(45,212,191,0.35)",
            "--callToActionHighlight": "#0f423b",
            "--success": "#4ade80",
        },
        "globals": {
            # Reuses the chosen hues (#065f46, #0e7490 -- the one cool
            # blue-green allowed, #134e4a, #0f766e); same stop positions as
            # the original aurora layout, just re-picked so every stop is
            # green/teal, none violet.
            "backgroundImage": (
                "radial-gradient(1100px 700px at 8% -10%, #065f46 0%, transparent 55%), "
                "radial-gradient(900px 650px at 88% 8%, #0e7490 0%, transparent 55%), "
                "radial-gradient(1000px 700px at 30% 115%, #134e4a 0%, transparent 55%), "
                "radial-gradient(800px 600px at 95% 100%, #0f766e 0%, transparent 55%)"
            ),
            "backgroundColor": "#0d1412",
        },
    },
}
