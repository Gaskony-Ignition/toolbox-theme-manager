# Ignition Themes

Ten curated Perspective gateway themes. A **theme** here is a native Ignition 8.3 gateway config resource — it restyles every stock Ignition component without needing a parent project, a project stylesheet, or any style classes.

Source, full generator documentation and the evaluation this pack grew out of are at <https://github.com/Gaskony-Ignition/toolbox-theme-manager>.

## What's in the box

| Theme id | Label | Look | Mode |
| --- | --- | --- | --- |
| `glass-violet` | Glass Violet | translucent glass panels over a violet/blue/green/pink gradient field | dark |
| `glass-green` | Glass Green | translucent glass panels over a dark near-black green/teal gradient field, bright mint accent | dark |
| `leather-dark` | Leather Dark | warm tan leather and dark paper, reads as a book after dark | dark |
| `leather-light` | Leather Light | warm tan leather and parchment, reads as a book in daylight | light |
| `finance-ledger` | Finance Ledger | clean, restrained ledger/spreadsheet look | light |
| `newsprint-dark` | Newsprint Dark | newsprint greys and ink on a dark page | dark |
| `nord-dark` | Nord Dark | the Nord palette, dark mode | dark |
| `nord-light` | Nord Light | the Nord palette, light mode | light |
| `industrial-dark` | Industrial Dark | industrial control-room cyan, dark mode | dark |
| `industrial-light` | Industrial Light | industrial control-room cyan, day mode | light |

Every theme covers 110 of the gateway's 120 built-in theme-variable surface, not just the headline colours, and declares `color-scheme` for its own mode so Chrome's auto-dark-mode doesn't repaint chart SVGs white on a dark theme.

## Quick start

The easiest way is the Toolbox Theme Manager project (https://github.com/Gaskony-Ignition/toolbox-theme-manager), which installs any or all of the ten from a page and runs the config scan for you.

Or use the `install.sh` route (`--data-dir`, `--docker <container>`, or `--ssh <host> --data-dir`) to inspect or script the install without a Gateway UI round-trip, or to deploy to several gateways from one place — it copies every theme directory into `<data-dir>/config/resources/core/com.inductiveautomation.perspective/themes/<theme-id>/`, idempotent and safe to re-run, and refuses to touch `light`, `dark`, `light-cool`, `light-warm`, `dark-cool`, `dark-warm`.

Themes are gateway **config resources**, not project resources: register them via **Config → Platform → Overview → "Scan File System"** — a different button from the Projects page's own scan, which will not register a new theme. No gateway restart is required.

The repo's `selector-popup/` folder has two copy-me views (a swatch popup and a dropdown) that let a user switch their own session's theme and list whatever the gateway has.

Select a theme by binding `session.props.theme` (bindable, session-wide — not page-scoped; that's `system.perspective.setTheme()` instead). `themes.json` (included in this pack) carries the id/label/dark-flag list as data if you'd rather build the options dynamically than hand-write them.

Uninstall by deleting each theme's directory under `.../themes/<theme-id>/` and running the same Overview config scan again — there's no separate gateway-side registry to clean up.

## What's covered

Each theme's `variables.css` maps **110** of the live gateway's **120** built-in custom properties (audited directly against a running 8.3.8 gateway's flattened `dark.css`/`light.css`) — surfaces, borders, ink, the full accent family, status colours (incl. secondary washes), radius, elevation, checkbox/radio/toggle/progress-bar controls, the full 10-step neutral scale, P&ID symbol fill/stroke states, native pipe rendering, and three algorithmically-generated chart scales (`--qual-1..10`, `--seq-1..6`, `--div-1..16`) anchored on each theme's own accent colour.

**Deliberately left inherited** (the remaining 10 of the 120 — geometry or pure IA brand constants, not colours a pack should override): `--white`, `--black`, `--font-NotoSans`, `--opacity-25/50/85`, `--red-10/20/30/50/60`, `--defaultSliderFocusBoxShadow` (a pure blur/spread value with no colour component — its colour half, `--defaultSliderFocusColor`, IS themed).

**Two bonus variables** our themes cover that IA's own built-in themes never define at all — `--tooltip-background-color` and `--arrow-color` are referenced by `.ia_form__tooltip-*` rules via `var()` with no fallback and no `:root` value anywhere in IA's own CSS, so a stock IA tooltip's background/arrow are effectively unset. Every theme in this pack gives them a real value.

**A handful of IA rules hard-code a colour literal directly onto a component selector, bypassing the variable system entirely** — no theme, IA's own or ours, can reach these by overriding a variable. Three were judged common and visible enough to compensate for with a small targeted rule in each theme's `globals.css`:
- Browser text selection (`::selection`) — IA hardcodes a fixed dark blue in dark mode and leaves light mode at browser default; every theme here tints it with its own accent instead.
- The primary slider's focus glow (`.ia_slider__handle:focus`) — IA hardcodes its own blue directly on this selector rather than reading the `--defaultSliderFocusColor` variable the way its own *other* slider implementation does; compensated to read the variable properly.
- Table row hover/selection (`.ia_tableComponent__body__row--hovered`, `.ia_tableComponent__selection`, `.ia_alarmJournalTableComponent__selection`, `.ia_alarmStatusTableComponent__selection`) — the highest-traffic hardcode found (every table hits it); IA's own blue is replaced with the theme's accent at the same alpha steps IA itself uses.

**Left as IA constants, not compensated for**:
- Generic black elevation `box-shadow`s across many selectors (alarm table panels, the pager, table head/foot containers, the toggle switch thumb, editable table cells, form tooltips) — these are neutral black in IA's own themes too, so they're consistent with everything else this pack already does for its own `--boxShadow1..5`.
- The date-range picker's day-hover tint (a narrow, low-traffic component).
- The **entire Equipment Schedule / Gantt component** — progress-bar fill and track, tooltip, schedule-event blocks, lead-time shading, move/selected placeholders, downtime and break-period washes are ALL hard-coded regardless of theme. If your project uses this component, expect it to look the same (IA-purple/blue/peach) under every theme in this pack, including the stock ones.
- `.ia_form__actionBar--fixed`'s border colour (a single grey hairline).
- The video player's control-popup background (deliberately black — matches the convention most video players use regardless of surrounding theme).

## Upgrade risk

Custom-named themes are low-risk — the Perspective module's upgrade migrator only manages the bundled names (`light`, `dark`, and the four shipped variants), and never touches a custom directory. A theme installed by this pack lives only on the gateway it was installed to unless you also keep a copy elsewhere (git, a backup, this zip).

## Source

Generated by `mapping.py` (the token → theme-variable table) and `build_theme.py`, at <https://github.com/Gaskony-Ignition/toolbox-theme-manager> under `tools/themes/`. That repo's `docs/THEMES-INTERNALS.md` carries the generator documentation, including per-theme derivation notes and the style-class contract.

Apache-2.0.
