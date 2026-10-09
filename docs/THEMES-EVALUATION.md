# Perspective gateway themes — evaluation against a stylesheet parent

**Rig:** Ignition 8.3.8 (docker).

> `Styles_Template2` below names the in-house look-and-feel **parent
> project** a theme is evaluated against — one shared Perspective project a
> child project inherits for its stylesheet, style classes and token CSS.
> Read "Styles_Template2" as "a look-and-feel parent project" throughout.

**Experiment:** the `aurora-violet` and `leather-night-tan` packs
regenerated as gateway themes (`test-aurora-violet`, `test-leather-night-tan`) and applied
to `Themes_Test`, a throwaway project with **no parent, no stylesheet, no style classes**.
This document is the deliverable; the experiment itself is disposable.

## What a theme is on 8.3

A gateway **config resource** at
`data/config/resources/core/com.inductiveautomation.perspective/themes/<name>/`:
`config.json` (`{"entrypoint": "index.css", "isPrivate": false}`), the CSS files
(relative `@import`s only), and a `resource.json` with **no**
`lastModificationSignature`. `light`/`dark` are reserved and live inside the Perspective
module jar, but a custom theme can still `@import "../dark/index.css"` — the gateway
resolves the import virtually and serves one flattened file at
`/data/perspective/themes/<name>.css` (~85 KB for ours: the whole dark base + our
overrides; comments are stripped). Selection is `session.props.theme`.

A theme restyles every stock IA component because they all consume ~136 CSS custom
properties (`--neutral-10..100`, `--callToAction*`, `--container*`, `--border*`,
`--input*`, `--label*`, `--icon*`, status colours, `--qual/div/seq-*`, `--borderRadius`,
`--boxShadow1..5`, …). Our generator (`build_theme.py`) maps ~35 pack
tokens onto that set; translucent pack surfaces are flattened to opaque colours the same
way the parent's own stylesheet builder does.

## The headline finding: no restart

The official docs (8.1 **and** 8.3) say a new theme is not selectable until the gateway
restarts. **On 8.3.8 that is wrong.** A brand-new theme dropped under
`config/resources/.../themes/` registered with a single Platform → Overview
**Scan File System** (the config scan, not the Projects one) — it served immediately and
a session with `session.props.theme` set to it came up fully themed. No restart was
performed at any point in this test. Theme *edits* likewise apply on a config scan.

## The three claims, tested

### (a) "The project stylesheet stays free for individual project use" — TRUE

`Themes_Test` has no `stylesheet` resource at all and renders fully themed. Under
Styles_Template2 the parent *owns* the one stylesheet per project and a child that adds
its own loses everything (`check_consumer.py` check 3 — 0 of 780 custom properties
survive). Moving pack tokens into themes would return `stylesheet.css` to each consumer.
This is the strongest genuine advantage a theme has over the shared stylesheet.

### (b) "No template project necessarily required" — TRUE, with a hard boundary

A parent-free project with stock components restyled correctly: page, cards, table,
buttons (`#8558ec` aurora / `#c08a4a` leather, pixel-verified), inputs, radii, shadows,
inks. What a bare theme **cannot** deliver (all verified, not speculative):

- **The 69-class contract.** A theme is CSS only; it cannot ship Perspective style
  classes. Every semantic surface the packs define beyond IA's variable set — status
  pills, KPI deltas, alarm-priority chips, nav states — has no hook in a bare project.
- **Typography targeting.** `ia.display.label` renders as `<div class="ia_labelComponent">
  <span>`, never `h1..h4` — leather's serif heading face is unreachable by global CSS;
  it needs a style class on the component.
- **Chart palettes.** `styles.chart_palette()` is a gateway-scope script reading pack
  `style.json` off the project tree — categorically impossible for a theme. Chart.js
  cannot be themed by CSS at all.
- **Per-user persistence and the picker.** `session.custom.style`, the `style_prefs`
  table, the alias map and the family/mode/palette Switcher are project resources.
  `session.props.theme` is a flat string with no composition model.
- **Scale.** 81 packs = 81 theme resources to generate, deploy and name-govern,
  gateway-wide (a theme is visible to every project on the gateway and cannot travel in
  a project export or inheritance chain).

### (c) "More performant — applies before the page even loads" — FALSE as stated

Measured on cold loads: the theme CSS and the project style bundle are **sibling
blocking `<link>` tags** in the same document head
(`PerspectiveClient.css` → `themes/<name>.css` → `style-classes/<project>/…/style.css`).
The theme is earlier in *cascade* order — and therefore actually **loses** collisions to
the project stylesheet (IA's documented order: theme → stylesheet.css → style classes →
inline). Nothing paints "before the page loads" in either mechanism; the documented FOUC
in this area is the *theme-switching* flash, which IA mitigate via `stylesheet.css`.

The kernel of truth is **payload**: the shared Styles_Template2 sheet ships all 81
packs to every session — the parent's style-classes bundle is **1,130,232 B**
vs **84,763 B** for a single-pack theme (`Themes_Test`'s style-classes bundle: 26 B).
Total cold load: 914 ms vs 1,205 ms. That ~1.1 MB is a Styles_Template2 packaging
choice, not a Perspective mechanism advantage — it could equally be fixed inside the
stylesheet model by scoping what a consumer receives.

## Traps hit (worth knowing before doing this again)

- The **Overview** config scan registers themes; the Projects scan silently does not.
- `resource.json` must omit `lastModificationSignature` or the scan silently skips it.
- Never edit the four shipped variants (`light-cool` etc.) or `light`/`dark` — gateway-
  owned; custom names are safe across upgrades but live only in the docker volume, so
  the git copy under `out/` is the source of truth.
- `docker exec` in this container runs as uid 2003 — `chown` needs `-u root`.
- **Verify visibility, not computed style.** The page background-image rule on
  `#app-container` "applied" per `getComputedStyle` while the page's top-level view root
  (`.view.ia_container--root` — stock Perspective paints the outermost per-view root
  opaque) covered it; pixel-flat screenshots caught what the DOM check missed. Fix: keep
  the image on `#app-container` and make only
  `#app-container .center.view-parent > .view.ia_container--root` transparent
  (`!important` required — docks/popups/embedded views keep their surfaces). Pixel-
  verified after: aurora's four blooms and leather's texture at its exact 31px period.
  Note the fragility: a theme wanting a page background must reach into Perspective's
  internal DOM classes — something the pack system does with an opt-in `containers/page`
  class instead.
- A theme carries `color-scheme` in `:root` — a bare themed project satisfies the
  workspace Chrome-auto-dark rule without a stylesheet, one small point *for* themes.

## What a template parent still buys

Even in a themes-first world, a parent project remains the only carrier for: the style
class contract (anything richer than IA's variable set), the picker + per-user
persistence machinery, script libraries (`styles`, `styles_charts` — chart palettes
especially), and consumer lint/guarantees. A theme replaces exactly one of the parent's
five deliverables: the token CSS.

## Verdict and the hybrid worth considering

Themes are not a replacement for Styles_Template2 — they are a better *transport for the
token layer* than the shared stylesheet is. The forward-looking option (out of scope
here, not started):

**Hybrid:** generate one theme per pack from `packs/*.json` (the mapping in
`mapping.py` is ~80% of that generator), keep the style classes,
picker, persistence and script libraries in the parent, drive `session.props.theme` from
`session.custom.style`, and delete the token section (§1, ~3,400 of 4,346 lines) from
the shared stylesheet — freeing `stylesheet.css` for consumers and cutting ~1 MB off
every session's cold load, while keeping every existing consumer binding unchanged.
Costs to answer first: 81 theme resources per gateway deployed *outside* the project
tree (new deploy surface — `tools/deploy.sh` only rsyncs projects), and theme switching
flashes unstyled content momentarily (documented IA behaviour), which the current
class-swap mechanism does not.

## Artefacts

- Generator, mapping and generated themes (committed to this repo).
- Gateway test fixtures: themes `test-aurora-violet`, `test-leather-night-tan`;
  project `Themes_Test`.
