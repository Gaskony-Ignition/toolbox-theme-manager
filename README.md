# Toolbox Theme Manager

A Perspective project that installs, removes, customises and imports gateway themes, one at a time or all at once.

> **Not an Inductive Automation product, and not supported by Inductive Automation.** Independent work, largely built with AI tools and tested for one purpose on a limited subset of gateway versions and platforms. Take the ideas; fork and review it before it goes near production. Feedback is welcome in Issues; improvements are made where possible, but no support is guaranteed. [NOTICE.md](NOTICE.md) says more.

## Why this exists

A Perspective theme is a gateway config resource: a folder of CSS under the gateway's data directory that every session on the gateway can wear. Putting one there normally means shell access and a config scan. This project does it from a page, carries ten ready-made themes from [ignition-themes](https://github.com/Gaskony-Ignition/project-themes), and takes a theme someone else made as a zip, checking it first, because a theme is CSS that every session on the gateway loads.

## What it looks like

![The Installer page with two themes selected](docs/images/installer.png)

The Installer page. Select rows and press Install selected or Remove selected to act on just those; Install all and Remove all still do the ten in one go. Ignition's own themes, themes made on Customise and imported themes are listed with them.

![An imported theme that passed the checks](docs/images/import-checked.png)

Importing a theme zip. It passed the safety checks, so Install is enabled, and the contrast pairs that fall under WCAG 2.1 AA are listed for the admin to weigh up.

![An imported theme that was refused](docs/images/import-refused.png)

A zip that fetches a stylesheet from another server, sends a request to a tracking address and carries a script. Each reason is listed, Install stays disabled, and nothing has been written to the themes folder.

![The Customise page](docs/images/customise.png)

Customise: copy one of the ten and change its colours, with a preview that repaints on every save.

## What it does

| Action | What happens on the gateway |
| --- | --- |
| Install all / Install selected | Writes the chosen themes' files under `config/resources/core/com.inductiveautomation.perspective/themes/` and runs one config scan. No restart. Re-running repairs a damaged copy. |
| Remove all / Remove selected | Deletes the chosen themes through `system.config.delete()`. Remove selected also deletes imported themes. Ignition's own themes and themes made on Customise are never touched. |
| Update / Restore | Optional. Adds themed scrollbars and a `color-scheme` line to Ignition's four on-disk stock variants without changing their look, and takes them back off. |
| Import | Checks a theme zip, shows the verdict and a preview, and installs it only if nothing was refused. |
| Customise | Makes a theme of your own from one of the ten and edits its colours. |
| Theme switcher | Two copy-me views, `SelectorPopup` and `ThemeDropdown`, that list whatever themes the gateway has. |

### What an import may contain

A zip of one theme: `index.css` and any `.css` files it imports, either at the top of the zip or in one folder. `README`, `LICENSE`, images, `config.json` and `resource.json` are left out; the last two are written fresh. The theme id comes from the folder or zip name and can be changed before installing.

| Refused | Listed as a warning |
| --- | --- |
| Any file other than `.css`; sub-folders; paths with `..`, absolute paths, symbolic links, encrypted entries | Text or control-edge colours under WCAG 2.1 AA (4.5:1 text, 3:1 edges) on the three container surfaces, worked out with what the theme inherits |
| `url()` to anything but an inline `data:` image or font; `image-set()` | No `color-scheme` declaration |
| `@import` other than `./file.css` in the zip, or `../<theme>/index.css` from `index.css` to a theme the gateway has | Building on nothing, or on a theme other than Ignition's own |
| `expression()`, `javascript:`, `vbscript:`, `-moz-binding`, `behavior:`, `</`, `@namespace`, `@document` | Text added with `content:` |
| Backslash escapes of letters or hex codes, which could spell `url(` unseen; an unclosed comment | |
| Not UTF-8; a zip over 2 MB, a file over 1 MB or 3 MB in all; over 40 entries | |
| An id that is already a theme on the gateway | |

The upload is kept on the gateway, and Install checks that copy again, so what is installed is what was checked. An imported theme's `resource.json` records the zip name, its SHA-256 and the date.

## How to use it

1. Gateway web UI → **Config → Projects → Import**, pick `Toolbox_Theme_Manager-<version>.zip` from the latest release.
2. Open `<gateway>/data/perspective/client/Toolbox_Theme_Manager`.
3. Press **Install all**, or select rows and press **Install selected**. The status column changes to Installed a couple of seconds later.
4. To bring in someone else's theme, press **Import...**, drop the zip on the box, read the findings, then press **Install**.

The project has no parent, no database and no tag provider, and runs on any 8.3 gateway. Deleting it leaves the themes in place; they are gateway config, not project resources.

---

## Building from source

The project sits at the repo root and is generated; edit the generator, not the `view.json` files.

```bash
tools/vendor-themes.sh [path/to/ignition-themes]  # copy the ten themes into tools/themes/
python3 tools/build_manager.py                    # regenerate the project
python3 tools/test_import.py                      # import checks: 40 zips, good and bad
tools/package.sh --release                        # dist/Toolbox_Theme_Manager-<VERSION>.zip
```

`tools/build_manager.py` appends `tools/insight_code.py`, `tools/editor_code.py` and `tools/import_code.py` to the generated `themepack` script. A release needs `VERSION` to match the tag.

Replaces the Theme Installer project from ignition-themes 1.17.x. A gateway with `Theme_Installer` on it can delete that project once this one is imported; the themes it installed stay where they are.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
