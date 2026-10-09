# The theme switchers

Two copy-me views, either of which lets a user change the theme of their own
session. A project takes whichever suits it, or both:

| File | Project view | What it is |
| ---- | ------------ | ---------- |
| `SelectorPopup.view.json` | `views/SelectorPopup` | The swatch grid, opened as a popup. Each theme is a button in its own colours. |
| `ThemeDropdown.view.json` | `views/ThemeDropdown` | One dropdown, 34px tall. Embeds in a header or a settings row. |

Each view is independent and carries its own copy of the listing script, so
copying either into a project drags nothing else in.

## Both read the gateway, not a fixed list

Neither view offers a theme that is not on the gateway. Both call
`system.config.getResources(moduleId="com.inductiveautomation.perspective",
typeId="themes")` when they open, and both add Ignition's six stock themes as
a fixed base (`light` and `dark` live inside the Perspective module's jar and
never appear as config resources). A theme from anywhere else appears in both
without either file being edited.

The swatch grid's colours are a fixed, hand-verified list — a view binding
cannot read a colour out of a theme's CSS — but a swatch is only offered when
the gateway has that theme; when none are, a line says so and points at the
dropdown at its foot.

## Embedding either one

**Dropdown:** copy the whole `views/ThemeDropdown` directory into the target
project and place it with an Embedded View component
(`props.path = "ThemeDropdown"`, about 260×34).

**Popup:** copy the whole `views/SelectorPopup` directory into the target
project, then add a button that calls:

```python
system.perspective.openPopup(
    'theme-selector',
    'SelectorPopup',
    title='Theme switcher',
    modal=True,
    draggable=True,
    resizable=False,
    overlayDismiss=True,
    viewportBound=True,
    position={'width': 560, 'height': 590})
```

`width`/`height` are keys inside `position`, not top-level kwargs.

Neither view needs a script package, a parent project, or any other prop
wiring — each writes `session.props.theme` itself.
