# ---------------------------------------------------------------------------
# IMPORT A THEME SOMEONE ELSE MADE
#
# A theme is CSS that every Perspective session on the gateway loads, so a zip
# from a stranger is checked before anything reaches the themes folder:
#
#   blocked  -- anything that fetches from elsewhere, runs code, hides what it
#               says, or lands outside its own folder. The import stops.
#   warned   -- quality: contrast under WCAG 2.1 AA, no color-scheme, no base
#               theme. Shown in the report; the admin decides.
#
# The upload is STAGED on the gateway and Install re-checks the staged copy, so
# what installs is what was checked, not whatever the page holds by then.
# resource.json and config.json are written here, never taken from the zip.
#
# check_import() touches nothing on the gateway: what it needs to know about
# the gateway arrives as two functions, so the same code runs under CPython in
# tools/test_import.py.
# ---------------------------------------------------------------------------

import hashlib
import shutil
import zipfile

try:
    from StringIO import StringIO as _BytesIO      # Jython 2.7
except ImportError:                                # CPython, tests only
    from io import BytesIO as _BytesIO

IMPORT_MAX_ZIP = 2 * 1024 * 1024
IMPORT_MAX_FILE = 1024 * 1024
IMPORT_MAX_TOTAL = 3 * 1024 * 1024
IMPORT_MAX_ENTRIES = 40
# Carried along in theme zips, read for nothing, never installed.
IMPORT_IGNORED = re.compile(
    r'^(readme|licen[cs]e|notice|changelog)(\.(md|txt))?$|^resource\.json$|'
    r'^config\.json$|^\.ds_store$|\.(png|jpe?g|gif|webp)$', re.I)
IMPORT_MARK = "Imported by Toolbox Theme Manager"

# @import may name another file of this theme, or the base theme it builds on.
_IMP_LOCAL = re.compile(r'^\./([A-Za-z0-9_][A-Za-z0-9_.-]*\.css)$')
_IMP_BASE = re.compile(r'^\.\./([a-z][a-z0-9]*(?:-[a-z0-9]+)*)/index\.css$')
_IMPORT_RE = re.compile(
    r'@import\s+(?:url\(\s*)?(["\']?)([^"\')\s;]*)\1\s*\)?\s*([^;]*);', re.I)
_URL_RE = re.compile(r'url\(\s*(["\']?)(.*?)\1\s*\)', re.I | re.S)
# Inline images and fonts only. Anything else in url() is a fetch from
# somewhere, which a theme loaded by every session must not make.
_URL_OK = re.compile(
    r'^data:(image/(png|jpeg|gif|webp|svg\+xml)|font/(woff2?|ttf|otf)|'
    r'application/(font-woff2?|x-font-woff))[;,]', re.I)
_DANGER = [
    (re.compile(r'expression\s*\(', re.I), "expression() runs script in old browsers"),
    (re.compile(r'javascript\s*:', re.I), "javascript: URL"),
    (re.compile(r'vbscript\s*:', re.I), "vbscript: URL"),
    (re.compile(r'-moz-binding', re.I), "-moz-binding loads code"),
    # Not scroll-behavior or overscroll-behavior, which are ordinary.
    (re.compile(r'(?<![\w-])behaviou?r\s*:', re.I), "behavior: loads code"),
    (re.compile(r'</', re.I), "'</' could close the page's style element "
     "(base64 an inline SVG)"),
    # Takes bare strings as well as url(), so it can fetch without url().
    (re.compile(r'image-set\s*\(', re.I), "image-set() can fetch from elsewhere"),
    (re.compile(r'@namespace|@document|@-moz-document', re.I), "at-rule a theme has no use for"),
    # A hex or letter escape can spell url( or @import so no pattern above
    # sees it. Escaped punctuation cannot, and Perspective style-class
    # selectors need it: .psc-st\/alarms\/list.
    (re.compile(r'\\[0-9A-Za-z]'),
     "backslash escape of a letter or hex code -- can disguise url() or @import"),
]

_IMPORT_TEXT = ["--label", "--label--disabled", "--neutral-100",
                "--error", "--warning", "--success", "--info"]
_IMPORT_SURFACES = ["--containerRoot", "--container", "--containerNested"]
_IMPORT_EDGES = ["--checkbox--unchecked", "--radio--unselected",
                 "--toggleSwitch--unselected"]


def _imp_colour(value):
    """(r, g, b, a) for hex or rgb()/rgba(), else None."""
    value = (value or "").strip()
    m = re.match(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', value)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    m = re.match(r'^rgba?\(([^)]+)\)$', value)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", ",").split(",")]
        try:
            rgb = tuple(float(p) for p in parts[:3])
            a = float(parts[3]) if len(parts) > 3 else 1.0
        except ValueError:
            return None
        return rgb + (a,)
    return None


def _imp_over(fg, bg):
    """fg composited over an opaque bg."""
    a = fg[3]
    return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3)) + (1.0,)


def _imp_ratio(a, b):
    def lum(c):
        out = []
        for v in c[:3]:
            v = v / 255.0
            out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _imp_resolve(values, name):
    value, hops = values.get(name), 0
    while value and hops < 8:
        m = re.match(r'^var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,[^)]*)?\)$', value.strip())
        if not m:
            break
        value, hops = values.get(m.group(1)), hops + 1
    return value


def import_contrast(values):
    """WCAG 2.1 AA misses for the stock variables every Perspective component
    reads: text 4.5:1 and control edges 3:1 on the three surfaces."""
    page = _imp_colour(_imp_resolve(values, "--containerRoot"))
    white = (255.0, 255.0, 255.0, 1.0)
    page = _imp_over(page, white) if page else white
    misses, unchecked = [], []
    for fgs, floor in ((_IMPORT_TEXT, 4.5), (_IMPORT_EDGES, 3.0)):
        for fg in fgs:
            for bg in _IMPORT_SURFACES:
                f = _imp_colour(_imp_resolve(values, fg))
                b = _imp_colour(_imp_resolve(values, bg))
                if not f or not b:
                    if values.get(fg) and values.get(bg):
                        unchecked.append("%s on %s" % (fg, bg))
                    continue
                b = _imp_over(b, page)
                ratio = _imp_ratio(_imp_over(f, b), b)
                if ratio < floor:
                    misses.append({"fg": fg, "bg": bg,
                                   "ratio": round(ratio, 2), "floor": floor})
    return misses, unchecked


def _imp_vars(css):
    """Custom properties a file declares, last wins. Unlike _vars_of this
    does not need one per line: a stranger's CSS may be minified."""
    found = {}
    for m in re.finditer(r'(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+)', css):
        found[m.group(1)] = m.group(2).strip()
    return found


def _imp_strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _imp_check_css(filename, css, files, kind_of, blocks, notes):
    """Block-level checks on one stylesheet. Returns the base theme it
    @imports, if any."""
    base = None
    body = _imp_strip_comments(css)
    if "/*" in body:
        blocks.append("%s: a comment is never closed" % filename)
    for pattern, why in _DANGER:
        if pattern.search(body):
            blocks.append("%s: %s" % (filename, why))
    for m in _IMPORT_RE.finditer(body):
        target, media = m.group(2), m.group(3).strip()
        local, other = _IMP_LOCAL.match(target), _IMP_BASE.match(target)
        if media:
            blocks.append("%s: @import with a media or layer condition (%s)"
                          % (filename, media))
        elif local:
            if local.group(1) not in files:
                blocks.append("%s: @import of %s, which is not in the zip"
                              % (filename, local.group(1)))
        elif other and filename == "index.css":
            kind = kind_of(other.group(1))
            if kind == "missing":
                blocks.append("index.css builds on '%s', which this gateway "
                              "does not have" % other.group(1))
            elif kind != "stock":
                notes.append("Builds on '%s' rather than one of Ignition's "
                             "own themes; removing that theme would break "
                             "this one." % other.group(1))
            if base and base != other.group(1):
                blocks.append("index.css builds on two themes")
            base = other.group(1)
        else:
            blocks.append("%s: @import of '%s' -- only ./file.css or "
                          "../<theme>/index.css (from index.css) is allowed"
                          % (filename, target))
    # Every @import must be one the pattern above understood.
    if len(re.findall(r'@import', body, re.I)) != len(_IMPORT_RE.findall(body)):
        blocks.append("%s: an @import this check cannot read" % filename)
    for m in _URL_RE.finditer(body):
        if not _URL_OK.match(m.group(2).strip()):
            shown = m.group(2).strip()
            blocks.append("%s: url(%s) -- only inline data: images and fonts "
                          "are allowed; a theme must not fetch anything"
                          % (filename, shown[:60] + ("..." if len(shown) > 60 else "")))
    if re.search(r'\bcontent\s*:\s*["\'][^"\']*[A-Za-z]{3}', body):
        notes.append("%s adds text to the page with content: -- read it "
                     "before installing." % filename)
    return base


def check_import(data, zip_name, name=None, kind_of=None, base_vars=None):
    """Check a theme zip. Returns the report; installs nothing.

    data      the zip as a byte string
    name      the theme id to install as; defaults to the zip's folder or name
    kind_of   id -> 'packaged' | 'stock' | 'user' | 'missing'
    base_vars id -> {variable: value} the gateway serves for that theme
    """
    kind_of = kind_of or theme_kind
    report = {"ok": False, "id": "", "dark": None, "base": None, "files": {},
              "blocks": [], "warnings": [], "ignored": [],
              "contrast": [], "sha256": hashlib.sha256(data).hexdigest(),
              "zip": zip_name}
    blocks, notes = report["blocks"], report["warnings"]
    if len(data) > IMPORT_MAX_ZIP:
        blocks.append("The zip is %d KB; the limit is %d KB"
                      % ((len(data) + 1023) // 1024, IMPORT_MAX_ZIP // 1024))
        return report
    try:
        zf = zipfile.ZipFile(_BytesIO(data))
        infos = zf.infolist()
    except Exception:
        blocks.append("Not a zip file this can read")
        return report
    if len(infos) > IMPORT_MAX_ENTRIES:
        blocks.append("%d entries in the zip; a theme has a handful"
                      % len(infos))
        return report

    # Either the files at the top, or all of them in one folder.
    names = [i.filename for i in infos if not i.filename.endswith("/")]
    tops = set(n.split("/")[0] for n in names if "/" in n)
    folder = tops.pop() if len(tops) == 1 and all("/" in n for n in names) else ""
    total = 0
    for info in infos:
        path = info.filename
        if path.endswith("/"):
            continue
        rel = path[len(folder) + 1:] if folder else path
        mode = (info.external_attr >> 16) & 0o170000
        if ("\\" in path or path.startswith("/") or ".." in path.split("/")
                or ":" in path):
            blocks.append("%s: path leaves the theme folder" % path)
            continue
        if mode == 0o120000:
            blocks.append("%s: symbolic link" % path)
            continue
        if info.flag_bits & 0x1:
            blocks.append("%s: encrypted" % path)
            continue
        if "/" in rel:
            blocks.append("%s: sub-folders are not part of a theme" % path)
            continue
        if IMPORT_IGNORED.search(rel):
            report["ignored"].append(rel)
            continue
        if not re.match(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*\.css$', rel):
            blocks.append("%s: only .css files are installed; scripts, "
                          "markup and other files are refused" % rel)
            continue
        if info.file_size > IMPORT_MAX_FILE:
            blocks.append("%s is %d KB; the limit is %d KB"
                          % (rel, (info.file_size + 1023) // 1024, IMPORT_MAX_FILE // 1024))
            continue
        # Read one byte past the limit: the header's size can lie.
        raw = zf.open(info).read(IMPORT_MAX_FILE + 1)
        total += len(raw)
        if len(raw) > IMPORT_MAX_FILE or total > IMPORT_MAX_TOTAL:
            blocks.append("%s: larger than its header says, or the theme is "
                          "over %d KB in all" % (rel, IMPORT_MAX_TOTAL // 1024))
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            blocks.append("%s is not UTF-8 text" % rel)
            continue
        if "\x00" in text:
            blocks.append("%s contains NUL characters" % rel)
            continue
        report["files"][rel] = text

    files = report["files"]
    if "index.css" not in files:
        blocks.append("No index.css -- the gateway loads a theme through it")

    stem = re.sub(r'\.zip$', '', (zip_name or "").split("/")[-1], flags=re.I)
    theme_id = (name or folder or stem or "").strip().lower()
    theme_id = re.sub(r'[\s_]+', '-', theme_id)
    report["id"] = theme_id
    if not EDITOR_ID_RE.match(theme_id):
        blocks.append("'%s' is not a usable theme id -- lower-case letters "
                      "and digits, words joined by single hyphens; give it "
                      "a name" % theme_id)
    else:
        kind = kind_of(theme_id)
        if kind != "missing":
            blocks.append("A theme called '%s' is already on this gateway "
                          "(%s) -- give the import another name"
                          % (theme_id, {"packaged": "one of ours",
                                        "stock": "one of Ignition's",
                                        "user": "made or imported here"}
                             .get(kind, kind)))

    base = None
    for filename in sorted(files):
        found = _imp_check_css(filename, files[filename], files, kind_of,
                               blocks, notes)
        base = base or found
    report["base"] = base

    own = {}
    for filename in sorted(files):
        if filename != "index.css":
            own.update(_imp_vars(_imp_strip_comments(files[filename])))
    own.update(_imp_vars(_imp_strip_comments(files.get("index.css", ""))))
    scheme = re.search(r'color-scheme\s*:\s*([a-z ]+)',
                       _imp_strip_comments("".join(files.values())))
    if base:
        report["dark"] = "dark" in base
    if scheme:
        report["dark"] = "dark" in scheme.group(1) and "light" not in scheme.group(1)
    else:
        notes.append("No color-scheme declaration. Without one Chrome's auto "
                      "dark mode can repaint charts white.")
    if not base:
        notes.append("index.css does not build on another theme, so every "
                     "variable it leaves out has no value and those parts "
                     "of Perspective render unstyled.")

    values = {}
    if base and base_vars:
        try:
            values.update(base_vars(base))
        except Exception:
            notes.append("Could not read '%s' to check contrast against "
                         "what it inherits." % base)
    values.update(own)
    misses, unchecked = import_contrast(values)
    report["contrast"] = misses
    if misses:
        notes.append("%d text or control-edge pairs are under WCAG 2.1 AA "
                     "contrast (listed below)." % len(misses))
    if unchecked:
        notes.append("%d pairs could not be checked (gradients or keywords)."
                     % len(unchecked))
    report["values"] = values
    report["ok"] = not blocks
    return report


# ---- gateway side: stage, report, install ----------------------------------

def _import_dir():
    path = os.path.join(_data_dir(), "theme-manager", "imports")
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _import_base_vars(base):
    return _vars_of(theme_css(base))


def import_bytes(file_bytes):
    """A Perspective upload's Java byte[] as a byte string. Not
    StringUtil.fromBytes: in Ignition's Jython that returns unicode, and the
    zip reader then sees mangled bytes."""
    return file_bytes.tostring()


def _staged(token):
    if not re.match(r'^[0-9a-f]{24}$', token or ""):
        raise ValueError("No staged import")
    return os.path.join(_import_dir(), token + ".zip")


def _import_report(data, zip_name, name, token):
    """The report for the page: findings, file names and a preview, not the
    file text or a few hundred variables."""
    report = check_import(data, zip_name, name, theme_kind, _import_base_vars)
    report["token"] = token
    report["preview"] = import_preview_uri(report) if report["ok"] else ""
    report["files"] = sorted(report["files"])
    report.pop("values", None)
    return report


def stage_import(data, zip_name, name=None):
    """Keep an upload on the gateway and check it. Kept even when refused, so
    a new name can be tried without uploading again. Staged copies older than
    a day are cleared out here."""
    import time
    root = _import_dir()
    for old in os.listdir(root):
        path = os.path.join(root, old)
        if time.time() - os.path.getmtime(path) > 86400:
            os.remove(path)
    if len(data) > IMPORT_MAX_ZIP:
        return check_import(data, zip_name, name, theme_kind, _import_base_vars)
    token = hashlib.sha256(data).hexdigest()[:24]
    _write_bytes(_staged(token), data)
    return _import_report(data, zip_name, name, token)


def recheck_import(token, zip_name, name=None):
    return _import_report(_read_bytes(_staged(token)), zip_name, name, token)


def _write_bytes(path, data):
    fh = open(path, "wb")
    try:
        fh.write(data)
    finally:
        fh.close()


def _read_bytes(path):
    fh = open(path, "rb")
    try:
        return fh.read()
    finally:
        fh.close()


def import_preview_uri(report, width=340, height=102):
    """The same mini screen as the status table, from the checked values."""
    return live_preview_uri(None, width, height, values=report.get("values") or {})


def install_import(token, zip_name, name=None):
    """Re-check the staged zip and install it. Refuses unless it passes."""
    path = _staged(token)
    data = _read_bytes(path)
    report = check_import(data, zip_name, name, theme_kind, _import_base_vars)
    if not report["ok"] or report["sha256"][:24] != token:
        raise ValueError("The staged theme no longer passes: %s"
                         % ("; ".join(report["blocks"]) or "changed on disk"))
    theme_dir = os.path.join(_themes_root(), report["id"])
    # Staged then renamed into place: a scan that reads a half-written theme
    # skips it silently and does not come back to it.
    stage = theme_dir + ".importing"
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    files = dict(report["files"])
    files["config.json"] = json.dumps(
        {"entrypoint": "index.css", "isPrivate": False}, indent=2) + "\n"
    for filename, text in files.items():
        _write(os.path.join(stage, filename), text)
    import datetime
    doc = {"scope": "G", "version": 1, "restricted": False,
           "overridable": True, "attributes": {},
           "description": "%s from %s (sha256 %s) on %s" % (
               IMPORT_MARK, zip_name, report["sha256"][:16],
               datetime.date.today().isoformat()),
           "files": sorted(files)}
    _write(os.path.join(stage, "resource.json"), json.dumps(doc, indent=2))
    os.rename(stage, theme_dir)
    os.remove(path)
    _rescan()
    return report["id"]


def imported_themes():
    """Ids of themes this page imported, read off their resource.json."""
    out = []
    for name in user_themes():
        try:
            doc = json.loads(_read(os.path.join(_themes_root(), name,
                                                "resource.json")))
        except (Exception, Throwable):
            continue
        if (doc.get("description") or "").startswith(IMPORT_MARK):
            out.append(name)
    return out


def remove_imported(names):
    """Delete the named themes if, and only if, this page imported them."""
    mine = set(imported_themes())
    done = [n for n in (names or []) if n in mine]
    for name in done:
        delete_theme(name)
    return done


# What fits the popup at 1366x640 without clipping.
IMPORT_SHOWN = 8


def import_view(report, error=None):
    """What the Import popup shows, as plain strings it can bind to."""
    report = report or {}
    if error:
        return {"ok": False, "token": "", "id": "", "preview": "",
                "verdict": "Not checked: %s" % error, "details": "",
                "findings": ""}
    blocks = report.get("blocks") or []
    if report.get("ok"):
        verdict = "Passes the checks. Installs as '%s'." % report["id"]
    else:
        verdict = ("Refused: %d problem%s below. Nothing has been written to "
                   "the themes folder." % (len(blocks),
                                           "" if len(blocks) == 1 else "s"))
    mode = {True: "dark", False: "light"}.get(report.get("dark"), "unknown")
    details = "%s  |  builds on %s  |  %s  |  files %s" % (
        report.get("zip") or "", report.get("base") or "nothing", mode,
        ", ".join(report.get("files") or []) or "nothing")
    if report.get("ignored"):
        details += "  |  left out: %s" % ", ".join(report["ignored"])
    lines = ["Refused: " + b for b in blocks]
    lines += ["Warning: " + w for w in report.get("warnings") or []]
    lines += ["  %s on %s is %.2f:1, needs %.1f:1" % (
        c["fg"], c["bg"], c["ratio"], c["floor"])
        for c in report.get("contrast") or []]
    if len(lines) > IMPORT_SHOWN:
        lines = lines[:IMPORT_SHOWN - 1] + [
            "... and %d more" % (len(lines) - IMPORT_SHOWN + 1)]
    return {"ok": bool(report.get("ok")), "token": report.get("token") or "",
            "id": report.get("id") or "", "preview": report.get("preview") or "",
            "verdict": verdict, "details": details,
            "findings": "\n".join(lines) or "No warnings."}
