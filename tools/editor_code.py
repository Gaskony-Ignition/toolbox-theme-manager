# ---------------------------------------------------------------------------
# EDITOR -- read and write the theme files on this gateway.
#
# Hand-authored, commit-tracked, appended verbatim to themepack/code.py by
# build_installer.py (same pattern as insight/ and selector-popup/).
#
# WHY THIS EXISTS. Ectobox ship a Designer module that does exactly this, and
# it is a good tool, but a module is not wanted for it. Their module is one
# RPC interface of eleven filesystem methods over the same directory this
# file resolves, with "refresh" being an ordinary config scan -- nothing that
# needs a JVM, a Designer, or a signed .modl. So it lives here instead, and
# ships with the project import that already installs the themes.
#
# WHAT IT IS NOT. It is not a themes BUILD tool. The ten packs are generated
# from packs/*.json by build_theme.py and embedded in THEMES above; editing a
# file here changes what is on THIS gateway and nothing in the repo. Reinstall
# from the Installer page and your edit is gone -- which is the correct
# behaviour for a live-editing tool, and the reason read_file() reports whether
# a file still matches what the installer would write.
#
# EVERY function here re-asserts that the path it is about to touch is inside
# the themes root. The guard is not "the caller already checked" -- these are
# reachable from a Perspective page, which is reachable by anyone who can open
# the project.
# ---------------------------------------------------------------------------

# resource.json is the config-resource MANIFEST, not theme content. It is
# rewritten from the directory listing on every save (_stock_rewrite_manifest),
# so hand-editing it is at best pointless and at worst strands a theme: a
# stale lastModificationSignature makes the scan reject the whole resource.
# The editor refuses to open it rather than letting someone learn that.
EDITOR_PROTECTED = ["resource.json"]

# What the editor will open. Anything else in a theme directory is listed but
# not editable -- a font or an image has no business in a text box.
EDITOR_TEXT_SUFFIXES = [".css", ".json", ".txt", ".md", ".svg"]

# A theme file we will not let a save empty. Every one of these is load-bearing:
# an empty index.css is a theme that silently stops importing Ignition's own,
# which looks like the gateway broke rather than like a bad edit.
EDITOR_NEVER_EMPTY = ["index.css", "config.json"]


def _editor_root():
    """The themes root, normalised, with a trailing separator -- the prefix
    every guarded path is tested against."""
    root = os.path.abspath(_themes_root())
    if not root.endswith(os.sep):
        root = root + os.sep
    return root


def _editor_resolve(theme, filename=None):
    """Resolve theme[/filename] INSIDE the themes root, or raise.

    Path traversal is checked after normalisation, on the absolute path, with a
    prefix test -- not by inspecting the input for '..'. A name that survives
    normalisation and still starts with the root is safe by construction; one
    that does not is refused whatever it looks like.
    """
    root = _editor_root()
    parts = [theme] if filename is None else [theme, filename]
    for part in parts:
        if not part or not isinstance(part, basestring):
            raise ValueError("Empty name -- refusing")
        if os.sep in part or (os.altsep and os.altsep in part):
            raise ValueError("'%s' is a path, not a name -- refusing" % part)
    path = os.path.abspath(os.path.join(root, *parts))
    if not (path + os.sep).startswith(root):
        raise ValueError("'%s' resolves outside the themes root -- refusing"
                         % os.path.join(*parts))
    return path


def _editor_is_text(filename):
    lowered = filename.lower()
    for suffix in EDITOR_TEXT_SUFFIXES:
        if lowered.endswith(suffix):
            return True
    return False


def list_themes():
    """Every theme directory ON DISK, with what we know about each.

    'ours' means the id is one of the ten this project can install, so the
    Installer page can overwrite it. A theme that is not ours is still fully
    editable -- that includes the four on-disk stock variants. light and dark
    are served from inside the Perspective module jar and have no directory, so
    they do not appear here at all and cannot be edited; that is not a gap this
    file can close.
    """
    root = _themes_root()
    rows = []
    if not os.path.isdir(root):
        return rows
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        files = [f for f in sorted(os.listdir(path)) if f != "resource.json"]
        rows.append({
            "id": name,
            "ours": name in THEMES,
            "stock": name in STOCK_UPDATABLE,
            "files": len(files),
            "bytes": sum(os.path.getsize(os.path.join(path, f)) for f in files),
        })
    return rows


def list_files(theme):
    """The files in one theme directory. resource.json is listed, so the page
    can show it exists, but carries editable False."""
    d = _editor_resolve(theme)
    if not os.path.isdir(d):
        raise ValueError("No theme directory '%s' on this gateway" % theme)
    rows = []
    for name in sorted(os.listdir(d)):
        path = os.path.join(d, name)
        if not os.path.isfile(path):
            continue
        rows.append({
            "name": name,
            "bytes": os.path.getsize(path),
            "editable": _editor_is_text(name) and name not in EDITOR_PROTECTED,
            "protected": name in EDITOR_PROTECTED,
        })
    return rows


def read_file(theme, filename):
    """One file's text, plus whether it still matches what the installer would
    write for it.

    'modified' is the honest answer to "have I edited this?" and is None for a
    theme or file the installer does not ship -- absent, not false, because
    'not modified' would be a claim we cannot make about a file we have no
    reference copy of.
    """
    path = _editor_resolve(theme, filename)
    if not os.path.isfile(path):
        raise ValueError("No file '%s' in theme '%s'" % (filename, theme))
    if filename in EDITOR_PROTECTED:
        raise ValueError("'%s' is the resource manifest and is rewritten on "
                         "every save -- it is not editable" % filename)
    if not _editor_is_text(filename):
        raise ValueError("'%s' is not a text file" % filename)
    text = _read(path)
    shipped = None
    if theme in THEMES:
        shipped = THEMES[theme]["files"].get(filename)
    return {
        "theme": theme,
        "name": filename,
        "text": text,
        "bytes": len(text.encode("utf-8")),
        "modified": None if shipped is None else (text != shipped),
    }


def write_file(theme, filename, text, rescan=True):
    """Save one theme file, rewrite the manifest, and (by default) scan.

    The write is STAGED THEN RENAMED. A plain truncating write is a real hazard
    here and not a theoretical one: a config scan that reads a half-written
    file skips the resource silently and does not come back to it until
    something else in the directory changes. os.rename within one directory is
    atomic, so a reader sees either the old file or the new one.

    Pass rescan=False when saving several files in a row and scan once at the
    end -- a scan is not free, and one at the end is no less correct.
    """
    path = _editor_resolve(theme, filename)
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        raise ValueError("No theme directory '%s' on this gateway" % theme)
    if filename in EDITOR_PROTECTED:
        raise ValueError("'%s' is the resource manifest and is rewritten on "
                         "every save -- it is not editable" % filename)
    if not _editor_is_text(filename):
        raise ValueError("'%s' is not a text file" % filename)
    if text is None:
        raise ValueError("No text to write")
    if filename in EDITOR_NEVER_EMPTY and not text.strip():
        raise ValueError("'%s' is load-bearing -- refusing to save it empty"
                         % filename)
    if filename.lower().endswith(".json"):
        # Fail before writing, not after the scan has rejected it. A theme
        # whose config.json will not parse is a theme that vanishes from the
        # picker with nothing on the page to say why.
        try:
            json.loads(text)
        except (Exception, Throwable) as e:
            raise ValueError("'%s' is not valid JSON: %s" % (filename, e))

    staged = path + ".editor-staged"
    _write(staged, text)
    if os.path.exists(path):
        os.remove(path)          # Jython on Windows will not rename onto an
                                 # existing name; harmless on Linux.
    os.rename(staged, path)

    _stock_rewrite_manifest(d)
    if rescan:
        _rescan()
    return {"theme": theme, "name": filename,
            "bytes": len(text.encode("utf-8"))}


def create_file(theme, filename, text=""):
    """Add a file to a theme directory. Refuses to overwrite."""
    path = _editor_resolve(theme, filename)
    if not os.path.isdir(os.path.dirname(path)):
        raise ValueError("No theme directory '%s' on this gateway" % theme)
    if os.path.exists(path):
        raise ValueError("'%s' already exists in '%s'" % (filename, theme))
    if not _editor_is_text(filename):
        raise ValueError("'%s' is not a text file name" % filename)
    if filename in EDITOR_PROTECTED:
        raise ValueError("'%s' is the resource manifest -- it is written for "
                         "you" % filename)
    return write_file(theme, filename, text)


def delete_file(theme, filename):
    """Remove a file from a theme directory and rewrite the manifest.

    index.css and config.json are refused: deleting either leaves a directory
    that still registers as a theme and then renders as a broken one.
    """
    path = _editor_resolve(theme, filename)
    if filename in EDITOR_PROTECTED or filename in EDITOR_NEVER_EMPTY:
        raise ValueError("'%s' cannot be deleted -- the theme needs it"
                         % filename)
    if not os.path.isfile(path):
        return False
    os.remove(path)
    _stock_rewrite_manifest(os.path.dirname(path))
    _rescan()
    return True


def revert_file(theme, filename):
    """Put back what the installer ships for one file. Only for our ten
    themes -- there is no reference copy of anyone else's."""
    if theme not in THEMES:
        raise ValueError("'%s' is not one of this project's themes -- there is "
                         "nothing to revert to" % theme)
    shipped = THEMES[theme]["files"].get(filename)
    if shipped is None:
        raise ValueError("The installer does not ship '%s' for '%s'"
                         % (filename, theme))
    return write_file(theme, filename, shipped)


def search(theme, needle, ignore_case=True):
    """Find a string across one theme's editable files.

    Plain substring, not regex: the thing anyone actually searches a theme for
    is a token name or a colour, and a regex box is a way to get a confusing
    error instead of an answer.
    """
    if not needle:
        return []
    d = _editor_resolve(theme)
    if not os.path.isdir(d):
        raise ValueError("No theme directory '%s' on this gateway" % theme)
    target = needle.lower() if ignore_case else needle
    hits = []
    for name in sorted(os.listdir(d)):
        if name in EDITOR_PROTECTED or not _editor_is_text(name):
            continue
        path = os.path.join(d, name)
        if not os.path.isfile(path):
            continue
        for number, line in enumerate(_read(path).split("\n"), start=1):
            haystack = line.lower() if ignore_case else line
            if target in haystack:
                hits.append({"file": name, "line": number,
                             "text": line.strip()[:200]})
    return hits


def search_all(needle, ignore_case=True):
    """The same search across every theme on the gateway -- the question
    'which themes still say this' is the one worth asking before an edit."""
    hits = []
    for row in list_themes():
        for hit in search(row["id"], needle, ignore_case):
            hit = dict(hit)
            hit["theme"] = row["id"]
            hits.append(hit)
    return hits


def refresh():
    """Ask the gateway to re-read the theme directories.

    This is the whole of Ectobox's "one-click refresh": an ordinary config
    scan. A saved file is already on disk -- this is what makes the gateway
    notice. write_file() does it for you; this is for after an edit made some
    other way, or to prove to yourself that the scan is what applies a change.
    """
    _rescan()
    return True


# ---------------------------------------------------------------------------
# TOKEN EDITING -- the part that is better than a text box.
#
# A theme's variables.css is a flat list of `--name: value;` declarations, and
# that is the file people actually want to change: the colours. Editing it as
# text means typing hex into a wall of CSS and finding out whether you got it
# right by looking at a page. Editing it as a FORM means a labelled row, a
# swatch you can see, and a colour picker.
#
# The raw text editor stays for index.css and globals.css, which are structure
# rather than values and have no useful form representation.
#
# These reuse the insight functions above -- GROUPS, group_of, is_colour,
# swatch, _VAR_RE -- on purpose. The grouping that explains a theme on the
# Themes page is the grouping that should order it in the editor; two different
# groupings of the same tokens would be two things to keep in step.
# ---------------------------------------------------------------------------

def tokens(theme, filename="variables.css"):
    """Every custom property THIS FILE declares, in file order, grouped.

    Deliberately the file's own declarations, not the resolved stylesheet:
    this is an editor, and you can only edit what is written here. A token the
    theme inherits from the base it imports is not in this list because
    changing it here would mean ADDING a declaration, which is a different
    action and gets its own button.

    Last-wins is reported as a duplicate rather than hidden -- two
    declarations of one token is nearly always a mistake, and silently showing
    only the winner is how it survives.
    """
    doc = read_file(theme, filename)
    text = doc["text"]
    seen = {}
    rows = []
    for match in _VAR_RE.finditer(text):
        name = match.group(1)
        value = match.group(2).strip()
        line = text.count("\n", 0, match.start()) + 1
        row = {
            "name": name,
            "value": value,
            "line": line,
            "group": group_of(name, GROUPS),
            "colour": is_colour(value),
            "swatch": swatch(value),
            "duplicate": name in seen,
        }
        seen[name] = True
        rows.append(row)

    # Grouped in the order GROUPS declares, file order within a group. The
    # alphabetical version of this list was unreadable for the same reason it
    # was unreadable on the Themes page.
    order = dict((label, i) for i, (label, _) in enumerate(GROUPS))
    rows.sort(key=lambda r: (order.get(r["group"], len(order)), r["line"]))
    return rows


def token_groups(theme, filename="variables.css"):
    """tokens() folded into [{group, rows}] -- what a Perspective repeater of
    sections binds to directly, so the view does no grouping of its own."""
    sections = []
    for row in tokens(theme, filename):
        if not sections or sections[-1]["group"] != row["group"]:
            sections.append({"group": row["group"], "rows": []})
        sections[-1]["rows"].append(row)
    for section in sections:
        section["count"] = len(section["rows"])
    return sections


def _token_replace(text, name, value):
    """Replace the value of the LAST declaration of one token, in place.

    Surgical on purpose. Regenerating the file from a parsed token list would
    lose every comment in it -- and our variables.css carries the generated
    'why' comment beside each variable, which is the only explanation of what
    the token is for. An editor that silently strips the documentation is
    worse than no editor.
    """
    last = None
    for match in _VAR_RE.finditer(text):
        if match.group(1) == name:
            last = match
    if last is None:
        raise ValueError("'%s' is not declared in this file" % name)
    # group(2) is the value between ':' and ';'. Splice around it rather than
    # rebuilding the line, so leading whitespace and any trailing comment on
    # the same line survive untouched.
    start = last.start(2)
    end = last.end(2)
    return text[:start] + value + text[end:]


def set_token(theme, value_map_or_name, value=None, filename="variables.css"):
    """Change one token, or several at once, and save.

    Two shapes because the page needs both: set_token(theme, '--border',
    '#4c566a') for a single picker commit, and set_token(theme, {'--border':
    '#4c566a', '--label': '#d8dee9'}) for a Save that collects a form. The
    batch does ONE write and ONE scan.
    """
    if isinstance(value_map_or_name, dict):
        changes = value_map_or_name
    else:
        if value is None:
            raise ValueError("No value for '%s'" % value_map_or_name)
        changes = {value_map_or_name: value}
    if not changes:
        return {"changed": 0}

    doc = read_file(theme, filename)
    text = doc["text"]
    for name in sorted(changes):
        new = changes[name]
        if new is None or not str(new).strip():
            raise ValueError("No value for '%s' -- a token with an empty value "
                             "is not the same as a token that is absent, and "
                             "reads as a broken theme" % name)
        if ";" in str(new) or "}" in str(new):
            raise ValueError("'%s' is not a single CSS value" % new)
        text = _token_replace(text, name, str(new).strip())

    write_file(theme, filename, text)
    return {"changed": len(changes), "tokens": sorted(changes)}


def add_token(theme, name, value, filename="variables.css"):
    """Declare a token the file does not currently declare.

    Appended inside the LAST rule in the file rather than at the end of the
    text, because a declaration after the closing brace is not in any rule and
    does nothing -- silently, which is the worst way for this to fail.
    """
    if not name.startswith("--"):
        raise ValueError("'%s' is not a custom property name" % name)
    doc = read_file(theme, filename)
    text = doc["text"]
    for match in _VAR_RE.finditer(text):
        if match.group(1) == name:
            raise ValueError("'%s' is already declared -- edit it instead"
                             % name)
    close = text.rfind("}")
    if close == -1:
        raise ValueError("'%s' has no CSS rule to add a declaration to"
                         % filename)
    line = "  %s: %s;\n" % (name, str(value).strip())
    text = text[:close] + line + text[close:]
    write_file(theme, filename, text)
    return {"name": name, "value": value}


def tokens_compared(theme, against=None, filename="variables.css"):
    """tokens(), plus what another theme says for the same token.

    This is what the retired "Under the hood" page did, folded into the place
    where you can act on it: seeing that --border is repainted is more useful
    beside the field that changes it than on a page of its own.

    `against` defaults to the stock theme this one is built on, which answers
    "what did we change". Pass another theme id to answer "how do these two
    differ". Same defaulting as compare(), on purpose -- one rule to remember.

    The comparison reads the other theme's RESOLVED stylesheet (post-@import),
    not its files, because the question is what the browser ends up with. Our
    own side stays the file's declarations: you can only edit what is written
    here.
    """
    rows = tokens(theme, filename)
    if against is None:
        against = base_of(theme)
    if not against:
        # A base theme with nothing behind it. Return the rows unmarked rather
        # than inventing a comparison -- see headline().
        for row in rows:
            row["compared"] = ""
            row["state"] = ""
        return rows
    try:
        theirs = _vars_of(theme_css(against))
    except (Exception, Throwable):
        # A comparison we could not fetch must not take the editor down with
        # it: the rows are still editable without it.
        for row in rows:
            row["compared"] = ""
            row["state"] = "compare unavailable"
        return rows
    for row in rows:
        other = theirs.get(row["name"])
        row["compared"] = other or "-"
        if other is None:
            row["state"] = "new"
        elif other == row["value"]:
            row["state"] = "same as %s" % against
        else:
            row["state"] = "differs"
    return rows


def compare_options(theme=None):
    """Theme ids to offer in the editor's 'compare against' picker, base
    first -- the default comparison should be the first thing in the list, not
    something to hunt for."""
    ids = [r["id"] for r in list_themes()]
    for builtin in STOCK_BUILTIN:
        if builtin not in ids:
            ids.append(builtin)   # jar-served: comparable, just not editable
    base = base_of(theme) if theme else ""
    ordered = ([base] if base and base in ids else [])
    ordered += [i for i in ids if i != base and i != theme]
    return ordered


# ---------------------------------------------------------------------------
# USER THEMES -- create and delete a theme of your own.
#
# The editor page manages user-customised themes of their own. The
# Installer's buttons deliberately refuse any id outside the ten this
# project carries, which is what makes them safe to press; so a theme
# somebody makes here needs its own create and delete, and those must
# refuse the packaged and stock ids just as firmly in the other direction.
#
# Three kinds of theme, and the kind decides what may be done to it:
#   packaged  one of ours -- edit it, revert it, but the Installer owns its
#             lifecycle. Delete belongs on the Installer's Remove button.
#   stock     Ignition's own. Editable (that is a gateway operator's business)
#             but never created or deleted by us.
#   user      made here. The only kind this section will delete.
# ---------------------------------------------------------------------------

# A theme id becomes a directory name and a URL segment. Anything outside this
# is refused rather than sanitised -- a sanitiser that turns "../x" into "x"
# has silently created a theme somewhere the caller did not ask for.
EDITOR_ID_RE = re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$')


def theme_kind(name):
    """'packaged' | 'stock' | 'user' | 'missing'."""
    if name in THEMES:
        return "packaged"
    if name in STOCK_BUILTIN or name in STOCK_UPDATABLE:
        return "stock"
    if os.path.isdir(os.path.join(_themes_root(), name)):
        return "user"
    return "missing"


def start_points():
    """What a new theme can be started FROM, best first.

    One list, because there was no honest way to choose between two buttons.
    "New theme" built on a stock base, which ships no --st-* tokens at all --
    so the theme you got had none of the vocabulary this page is organised
    around, and the natural first click was the wrong door. The ten come
    first; the stock bases stay, last and labelled, for someone who means it.
    """
    out = []
    for name in THEME_ORDER:
        out.append({"id": name, "label": "%s  (one of ours)" % name,
                    "kind": "ours"})
    for name in user_themes():
        out.append({"id": name, "label": "%s  (yours)" % name, "kind": "user"})
    for name in list(STOCK_BUILTIN) + list(STOCK_UPDATABLE):
        out.append({"id": name, "label": "%s  (bare Ignition theme)" % name,
                    "kind": "stock"})
    return out


def start_warning(source):
    """The line shown under the picker when the choice costs you something."""
    if theme_kind(source) == "stock":
        return ("A bare Ignition theme ships none of the --st-* tokens or "
                "st/... classes, so your theme would have no accent, no card "
                "colour and nothing for a project to build against. Start "
                "from one of ours unless you specifically want that.")
    return ""


def make_theme(name, source):
    """Create a theme, from whatever you chose to start from.

    Copying one of ours and building on a bare Ignition theme were two
    buttons that looked like alternatives and were not comparable: one gives
    you a whole theme, the other an empty shell. One entry point, one list,
    and the difference stated where the choice is made.
    """
    if theme_kind(source) == "stock":
        return new_theme(name, source)
    return copy_theme(source, name)


def user_themes():
    """Every theme on disk that is neither ours nor Ignition's, id-sorted.

    The Installer's status table lists the ten and the six; a theme somebody
    made here belonged to neither list and so appeared on neither page --
    you could create one and then not find it anywhere but the dropdown that
    made it.
    """
    out = []
    root = _themes_root()
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        if not os.path.isdir(os.path.join(root, name)):
            continue
        if theme_kind(name) == "user":
            out.append(name)
    return out


def user_base_of(name):
    """'dark' or 'light' for a theme made here, read off its index.css.

    base_of() answers from THEMES and STOCK_DARK, so for a theme in neither it
    falls through to 'light' -- which labelled every copy of a dark theme
    Light in the status table.
    """
    try:
        text = read_file(name, "index.css")["text"]
    except (Exception, Throwable):
        return "light"
    return "dark" if re.search(r'@import\s+"\.\./dark/', text) else "light"


def _seed_variables(name, based_on, dark):
    """The starter variables.css: every variable the base declares, at the
    value it already has, grouped by what it affects.

    Read from the SERVED base stylesheet, because light and dark live inside
    the Perspective module and have no files to copy. If that read fails the
    file is still written, just without the list -- a theme with no starter
    values is worth less than one with them, but a create that fails outright
    is worth nothing.
    """
    head = ("/* %s -- your own theme, built on %s.\n"
            " * Every line below is what %s already says. Change one and only\n"
            " * that one changes; delete one and the base decides it again. */\n"
            % (name, based_on, based_on))
    body = ":root {\n  color-scheme: %s;\n" % ("dark" if dark else "light")
    try:
        values = _vars_of(theme_css(based_on))
    except (Exception, Throwable):
        values = {}
    rows = [(group_of(var, GROUPS), var, values[var]) for var in values]
    order = dict((label, i) for i, (label, _) in enumerate(GROUPS))
    rows.sort(key=lambda r: (order.get(r[0], len(order)), r[1]))
    last = None
    for group, var, value in rows:
        if group != last:
            body += "\n  /* %s */\n" % group
            last = group
        body += "  %s: %s;\n" % (var, value)
    return head + body + "}\n"


def new_theme(name, based_on="dark", description=""):
    """Create a theme of your own, built on a stock base like ours are.

    variables.css is seeded with the base's OWN values -- every variable it
    declares, at the value it already has. The theme therefore renders
    identically to the base, which is the point, but the page has a list to
    show and every line is yours to change.

    It is written fully populated rather than empty-but-for-a-comment: this
    page's whole proposition is a list of values you click, and an empty
    file would hand New theme a 550px void and a Save button with nothing
    to save. Empty is only defensible in a file editor, which this is not.

    globals.css stays empty. Its content is rules and classes, not values, and
    nothing on this page edits those except the Advanced text box.
    """
    if not name or not EDITOR_ID_RE.match(name):
        raise ValueError(
            "'%s' is not a usable theme id. Lower-case letters and digits, "
            "words joined by single hyphens -- for example 'ocean-dark'."
            % name)
    kind = theme_kind(name)
    if kind == "packaged":
        raise ValueError("'%s' is one of this project's own themes -- pick "
                         "another name" % name)
    if kind == "stock":
        raise ValueError("'%s' is one of Ignition's themes -- pick another "
                         "name" % name)
    if kind == "user":
        raise ValueError("'%s' already exists on this gateway" % name)

    bases = list(STOCK_BUILTIN) + list(STOCK_UPDATABLE)
    if based_on not in bases:
        raise ValueError("Build on one of: %s" % ", ".join(bases))

    theme_dir = _editor_resolve(name)
    os.makedirs(theme_dir)
    dark = STOCK_DARK.get(based_on, True)
    files = {
        "config.json": json.dumps(
            {"entrypoint": "index.css", "isPrivate": False}, indent=2) + "\n",
        "index.css": ('@import "../%s/index.css";\n'
                      '@import "./variables.css";\n'
                      '@import "./globals.css";\n' % based_on),
        # color-scheme is not optional and not decoration: without it Chrome's
        # auto dark mode repaints SVG fills client-side and charts come out
        # white on a dark page, with every server-side check reading correct.
        "variables.css": _seed_variables(name, based_on, dark),
        "globals.css": (
            "/* %s -- rules with no stock equivalent: scrollbars, component\n"
            " * chrome, the --st-* tokens and the st/... class contract.\n"
            " * Empty is fine; the base theme is still underneath. */\n"
            % name),
    }
    for filename, content in files.items():
        _write(os.path.join(theme_dir, filename), content)
    doc = {"scope": "G", "version": 1, "restricted": False,
           "overridable": True, "attributes": {},
           "files": sorted(files)}
    if description:
        doc["description"] = description
    else:
        doc["description"] = "%s -- created in the Theme Manager's editor" % name
    _write(os.path.join(theme_dir, "resource.json"), json.dumps(doc, indent=2))
    _rescan()
    return {"id": name, "based_on": based_on, "dark": dark}


def delete_theme(name):
    """Delete a theme made here. Refuses ours and Ignition's.

    Deletes the config resource AND the directory. system.config.delete on its
    own leaves the files, which the next scan reads straight back in -- the
    theme reappears and looks like the delete silently failed.
    """
    kind = theme_kind(name)
    if kind == "packaged":
        raise ValueError(
            "'%s' is one of this project's themes -- use Remove on the "
            "Installer page, which is the button that owns them" % name)
    if kind == "stock":
        raise ValueError("'%s' is one of Ignition's own themes and is never "
                         "deleted" % name)
    if kind == "missing":
        return False

    theme_dir = _editor_resolve(name)
    try:
        res = system.config.getResource(
            moduleId="com.inductiveautomation.perspective",
            typeId="themes", name=name)
        system.config.delete(
            moduleId="com.inductiveautomation.perspective",
            typeId="themes", name=name,
            signature=res.getSignature(), actor="theme-editor")
    except (Exception, Throwable):
        pass          # not registered; the directory removal below is the work
    if os.path.isdir(theme_dir):
        for entry in os.listdir(theme_dir):
            path = os.path.join(theme_dir, entry)
            if os.path.isfile(path):
                os.remove(path)
        os.rmdir(theme_dir)
    _rescan()
    return True


_GENERATED_HEADER = re.compile(r'\A\s*/\*.*?\*/\s*', re.S)


def _reheader(text, filename, source, name):
    """Replace a copied file's "DO NOT EDIT BY HAND" banner with the truth.

    That warning on every generated file makes it hard for people to change
    anything if they want to. On the ten themselves it is
    correct -- they are generated and Install overwrites them. On a COPY it is
    the opposite of correct: the copy is yours, nothing regenerates it, and
    carrying the banner over tells you not to do the one thing this page exists
    for. So the banner is rewritten, not stripped silently: the new header says
    where the file came from, which is the useful half of what it was saying.
    """
    if not filename.lower().endswith(".css"):
        return text
    match = _GENERATED_HEADER.match(text)
    body = text[match.end():] if (match and "DO NOT EDIT" in match.group(0)) \
        else text
    return ("/* %s -- YOUR COPY of %s, and yours to edit.\n"
            " * Nothing regenerates this file and Install does not overwrite\n"
            " * it. The original is generated from packs/%s.json in the\n"
            " * ignition-themes repo, which is why it says not to edit it.\n"
            " */\n" % (filename, source, source)) + body


def copy_theme(source, name):
    """Start a new theme from an existing one rather than from a bare base.

    The obvious way to make 'our nord-dark, but the accent is company red', and
    the reason the packaged themes stay safe to overwrite: copy first, edit the
    copy, and Install can still put ours back without touching yours.
    """
    if theme_kind(source) == "missing":
        raise ValueError("There is no theme '%s' on this gateway" % source)
    new_theme(name, based_on=base_of(source) or "dark",
              description="%s -- copied from %s" % (name, source))
    src_dir = _editor_resolve(source)
    dst_dir = _editor_resolve(name)
    copied = []
    for entry in sorted(os.listdir(src_dir)):
        if entry in EDITOR_PROTECTED or entry == "config.json":
            continue
        if not _editor_is_text(entry):
            continue
        text = _read(os.path.join(src_dir, entry))
        text = _reheader(text, entry, source, name)
        _write(os.path.join(dst_dir, entry), text)
        copied.append(entry)
    _stock_rewrite_manifest(dst_dir)
    _rescan()
    return {"id": name, "copied_from": source, "files": copied}


def base_options():
    """The stock themes a new theme can be built on."""
    return list(STOCK_BUILTIN) + list(STOCK_UPDATABLE)


# ---------------------------------------------------------------------------
# LIVE PREVIEW
#
# The customiser's whole premise is copy-one-and-tune-it, and tuning without
# seeing the result is guessing. The Installer's thumbnails are generated at
# BUILD time from the repo, so they cannot answer "what does it look like now
# that I changed the accent" -- this does, by reading the stylesheet the
# browser is actually being served and drawing the same mini screen from it.
#
# Same layout and the same palette keys as build_installer.py's preview_svg,
# deliberately: the picture on this page and the picture in the Installer's
# table have to be the same picture or neither can be trusted.
# ---------------------------------------------------------------------------

def _editor_declared(theme):
    """Every custom property the theme's OWN files declare, read off disk.

    The point is the timing. theme_css() fetches what the gateway is serving,
    which is the only way to see the base theme -- light and dark live inside
    the Perspective module, not on disk -- but it is a copy the gateway
    rebuilds after a scan, and a save beats the rebuild often enough that the
    preview showed the previous colour and looked broken. The files are
    authoritative the instant write_file() returns, so they go over the top.
    """
    values = {}
    for filename in EDITOR_COLOUR_FILES:
        try:
            values.update(_vars_of(read_file(theme, filename)["text"]))
        except (Exception, Throwable):
            continue                     # a theme need not have both files
    return values


def _colour_resolver(theme):
    """The theme's values, and a function that follows var() chains through
    them. Anything still unresolved comes back empty rather than literal: a
    var() reference painted as-is renders in the VIEWING page's colours and
    quietly shows the wrong thing.
    """
    values = {}
    try:
        values.update(_vars_of(theme_css(theme)))
    except (Exception, Throwable):
        # A theme made seconds ago is not being SERVED yet: the gateway 404s
        # its stylesheet until the scan lands and httpGet raises rather than
        # returning empty. Its BASE is already served and its own files are on
        # disk, so fall back to those -- otherwise everything downstream of
        # this (the preview picture, the swatch palette) is blank or in error
        # for the first half-minute of a theme's life, which is exactly when
        # somebody is looking at it.
        try:
            values.update(_vars_of(theme_css(user_base_of(theme))))
        except (Exception, Throwable):
            pass
    # Served copy for the inherited base, this theme's own files for anything
    # it sets itself -- so a save shows immediately instead of a scan later.
    values.update(_editor_declared(theme))

    return values, _resolver(values)


def _resolver(values):
    def resolve(value, hops=0):
        while value and value.startswith("var(") and hops < 6:
            found = re.match(r'var\(\s*(--[A-Za-z0-9_-]+)', value)
            if not found:
                return ""
            value = (values.get(found.group(1)) or "").strip()
            hops += 1
        return "" if (value or "").startswith("var(") else (value or "")
    return resolve


def live_palette(theme, values=None):
    """The dozen colours a preview is painted with, resolved from the LIVE
    stylesheet -- or from `values` when given, for a theme not installed."""
    if values is None:
        values, resolve = _colour_resolver(theme)
    else:
        resolve = _resolver(values)

    def pick(*names):
        for name in names:
            value = resolve((values.get(name) or "").strip())
            if value and value != "transparent":
                return value
        return ""

    page = pick("--st-page-solid", "--containerRoot")
    return {
        "page": page,
        "sidebar": pick("--st-sidebar-solid", "--containerNested", "--container"),
        "card": pick("--st-card", "--container"),
        "text": pick("--st-fg", "--label"),
        "muted": pick("--label--disabled", "--label"),
        "chromeFg": pick("--st-chrome-fg", "--label"),
        "accent": pick("--st-accent", "--callToAction"),
        "onAccent": pick("--st-on-accent") or "#ffffff",
        "border": pick("--st-chrome-border", "--border"),
        "headBg": pick("--st-head-solid", "--containerNested", "--container"),
        "headFg": pick("--st-head-fg", "--label"),
        "rowBg": pick("--st-row-bg") or page,
        "cellFg": pick("--st-cell-fg", "--label"),
    }


def live_preview_svg(theme, width=340, height=102, values=None):
    """The mini screen, drawn from live values, at whatever size is asked for."""
    pal = live_palette(theme, values)

    def c(key, fallback="#888888"):
        return pal.get(key) or fallback

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 200 60">' % (width, height)]

    def rect(x, y, w, h, fill, rx=0):
        parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" '
                     'rx="%s"/>' % (x, y, w, h, fill, rx))

    rect(0, 0, 200, 60, c("page"))
    rect(0, 0, 200, 11, c("sidebar"))
    rect(0, 11, 26, 49, c("sidebar"))
    for i in range(3):
        rect(5, 18 + i * 5, 16, 2, c("chromeFg"), 1)
    rect(32, 16, 92, 26, c("card"), 2)
    rect(36, 20, 54, 3, c("text"), 1)
    rect(36, 26, 44, 2, c("muted"), 1)
    rect(36, 32, 30, 7, c("accent"), 2)
    rect(40, 35, 22, 2, c("onAccent"), 1)
    rect(130, 16, 64, 26, c("headBg"), 2)
    rect(130, 16, 64, 7, c("headBg"), 2)
    rect(133, 19, 26, 2, c("headFg"), 1)
    for i in range(2):
        rect(130, 25 + i * 8, 64, 7, c("rowBg"))
        rect(133, 28 + i * 8, 30, 2, c("cellFg"), 1)
    rect(5, 4, 34, 3, c("chromeFg"), 1)
    parts.append("</svg>")
    return "".join(parts)


def live_preview_uri(theme, width=340, height=102, values=None):
    """base64 rather than percent-encoding: the SVG carries #rrggbb by the
    dozen and a raw '#' truncates a url() at the first colour."""
    import base64
    svg = live_preview_svg(theme, width, height, values)
    return "data:image/svg+xml;base64," + base64.b64encode(
        svg.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# WHAT MAY BE CHANGED
#
# The ten pre-packaged themes are generated from packs/*.json and their files
# say DO NOT EDIT BY HAND, which is the truth: Install overwrites them. A page
# that invites you to edit one is inviting work that disappears at the next
# install, so the customiser offers a COPY instead and the ten stay read-only.
# ---------------------------------------------------------------------------

def about_text(theme):
    """The same facts as one block of text, one per line.

    A table charged 30px a row plus a 30px header strip for four short facts
    and still needed a scrollbar on a laptop. Lines in a label cost their line
    height and nothing else, and there is no empty header band over them.
    """
    return "\n".join("%s:  %s" % (r["fact"], r["detail"]) for r in about(theme))


def about(theme):
    """The handful of facts about a theme that are worth a line each.

    Replaces a 69-row list of st/... class names. Every one of the ten
    publishes the SAME class set -- verified by comparing the sorted class
    lists across finance-ledger, nord-dark, glass-violet, industrial-light and
    leather-dark: identical -- so listing them per theme answered one yes/no
    question with a scroll, and said nothing about the theme you were on.
    """
    rows = []
    kind = theme_kind(theme)
    base = user_base_of(theme) if kind == "user" else base_of(theme)
    rows.append({"fact": "Built on", "detail": base or "nothing -- it IS a base"})
    try:
        classes = editor_classes(theme)
    except (Exception, Throwable):
        classes = []
    if classes:
        rows.append({"fact": "Style classes",
                     "detail": "%d, the standard contract"
                               % len(classes)})
    else:
        rows.append({"fact": "Style classes",
                     "detail": "none -- a stock base ships none"})
    try:
        found = [r for r in list_themes() if r["id"] == theme]
    except (Exception, Throwable):
        found = []
    if found:
        rows.append({"fact": "Files",
                     "detail": "%d files, %d KB"
                               % (found[0]["files"], found[0]["bytes"] / 1024)})
    # How to USE it. The page never said, so you finished a theme and were on
    # your own: no mention of a project, a session or the Theme menu anywhere
    # on it. It is installed the moment it exists -- there is no publish step.
    rows.append({"fact": "To use it",
                 "detail": "the Theme menu above, or your project's "
                           "session props"})
    return rows


def editor_css(theme):
    """What the browser WILL get: the served stylesheet with this theme's own
    files appended, so the last save counts even before the scan does.

    Appended, not substituted: the base theme lives inside the Perspective
    module and is only ever visible through the served copy. _vars_of takes
    the last definition, which is the same rule the browser applies, so the
    disk copy wins where both say something.
    """
    parts = []
    try:
        parts.append(theme_css(theme))
    except (Exception, Throwable):
        pass
    for filename in EDITOR_COLOUR_FILES:
        try:
            parts.append(read_file(theme, filename)["text"])
        except (Exception, Throwable):
            continue
    return "\n".join(parts)


def editor_contract(theme):
    """contract(), answered for a theme that may be seconds old."""
    return contract(theme, editor_css(theme))


def editor_classes(theme):
    """contract_classes(), read from the theme's own globals.css on disk."""
    try:
        css = read_file(theme, "globals.css")["text"]
    except (Exception, Throwable):
        return contract_classes(theme)
    return contract_classes(theme, css)


def is_editable(theme):
    """Only a theme made here may be changed from here."""
    return theme_kind(theme) == "user"


def why_not_editable(theme):
    """The sentence the page shows instead of an editor, or '' when editable."""
    kind = theme_kind(theme)
    if kind == "user":
        return ""
    if kind == "packaged":
        return ("This is one of the ten themes the project ships. Its files "
                "are generated from the repo and Install puts them back, so a "
                "change made here would disappear the next time anyone "
                "pressed Install. Make a copy and the copy is yours.")
    if kind == "stock":
        return ("This is one of Ignition's own themes, shared by every "
                "project on this gateway, and an Ignition upgrade replaces "
                "it. Make a copy and the copy is yours.")
    return "There is no theme selected."


# ---------------------------------------------------------------------------
# EVERY colour, across both files.
#
# tokens() reads one file, and the customiser first shipped pointed at
# variables.css -- which is where Ignition's OWN variable names are re-pointed,
# but NOT where the theme's identity lives. The --st-* tokens are declared in
# globals.css, so "make the accent our company red" -- the single most likely
# reason to open this page -- was the one thing the colour list could not do.
# ---------------------------------------------------------------------------

EDITOR_COLOUR_FILES = ["globals.css", "variables.css"]


def all_tokens(theme):
    """Every custom property the theme declares, from every file it declares
    them in, each row saying WHICH file so a save edits the right one.

    globals.css first: the --st-* tokens are the theme's own vocabulary and the
    reason someone is here, where variables.css is mostly Ignition's names
    re-pointed at them.
    """
    rows = []
    for filename in EDITOR_COLOUR_FILES:
        try:
            found = tokens(theme, filename)
        except (Exception, Throwable):
            continue                     # a theme need not have both files
        try:
            why = _reasons(theme)
        except (Exception, Throwable):
            why = {}
        for row in found:
            row = dict(row)
            row["file"] = filename
            # What the value is FOR, in a sentence -- kept here rather than a
            # separate read-only pane, which would only repeat the same
            # --st-* names with their resolved values.
            row["what"] = plain(row["name"], why.get(row["name"], ""))
            # The --st-* tokens have their OWN grouping. Run through GROUPS
            # (which classifies Ignition's variable names) they all land in
            # "Everything else", which is the least useful thing a grouped
            # list can say about the theme's own vocabulary.
            if filename == "globals.css":
                row["group"] = group_of(row["name"], TOKEN_GROUPS)
            rows.append(row)
    return rows


def token_file(theme, name):
    """Which of the theme's files declares this token. Last file wins, the
    same way the browser resolves it."""
    where = ""
    for filename in EDITOR_COLOUR_FILES:
        try:
            for row in tokens(theme, filename):
                if row["name"] == name:
                    where = filename
        except (Exception, Throwable):
            continue
    if not where:
        raise ValueError("'%s' is not declared in this theme" % name)
    return where


# The CSS colour keywords worth accepting by name. Not all 147: these are the
# ones somebody types on purpose, and an unknown name is refused with a message
# rather than written to a stylesheet where it silently does nothing.
EDITOR_COLOUR_WORDS = set("""
transparent currentcolor inherit initial unset black white red green blue
yellow orange purple pink brown grey gray silver gold navy teal olive maroon
lime aqua cyan magenta fuchsia beige ivory khaki coral salmon crimson firebrick
indigo violet turquoise tomato tan plum orchid linen lavender
darkred darkgreen darkblue darkgrey darkgray darkorange darkviolet darkcyan
lightgrey lightgray lightblue lightgreen lightyellow lightpink
whitesmoke gainsboro dimgrey dimgray slategrey slategray steelblue skyblue
midnightblue royalblue dodgerblue cornflowerblue seagreen forestgreen
""".split())


def looks_like_colour(value):
    """Whether a value will actually paint. Deliberately generous about FORM
    (hex, rgb/hsl, var(), a keyword) and strict about nonsense.

    Without this check, 'not-a-colour' would save with a cheerful
    'Saved --st-accent = not-a-colour', go into the served stylesheet, and
    every session using the theme would quietly lose its accent. A
    stylesheet does not report a bad value; this is the only place that can.
    """
    text = (value or "").strip()
    if not text:
        return False
    if re.match(r'^#[0-9A-Fa-f]{3,8}$', text):
        return True
    if re.match(r'^(rgb|rgba|hsl|hsla|var|color-mix|linear-gradient)\s*\(', text):
        return True
    return text.lower() in EDITOR_COLOUR_WORDS


# How many chips the page draws. Fixed, because Perspective cannot generate
# components from a list -- the page binds a fixed row at fixed indexes, so
# this list is always padded to exactly this length.
EDITOR_SWATCH_COUNT = 16

EDITOR_NOT_A_SWATCH = set(
    "transparent currentcolor inherit initial unset".split())


def swatches(theme, limit=EDITOR_SWATCH_COUNT):
    """The colours this theme already uses, most-used first, padded to a fixed
    length.

    Perspective ships no colour picker: ia.input.form declares a color-picker
    control type with no factory behind it, so a form using one renders as a
    single Component Error (measured on 8.3.8). This and the hex field beside
    it are therefore the whole of colour entry -- and picking from what the
    theme already contains is the better half of it anyway, since those are
    the colours that were chosen to sit together.
    """
    counts = {}
    try:
        values, resolve = _colour_resolver(theme)
        for name in values:
            value = resolve((values.get(name) or "").strip()).strip().lower()
            if value in EDITOR_NOT_A_SWATCH or not looks_like_colour(value):
                continue
            if value.startswith("linear-gradient"):
                continue                 # a chip cannot show one honestly
            counts[value] = counts.get(value, 0) + 1
    except (Exception, Throwable):
        counts = {}                      # padded empties below, never short
    # Most-used first: those are the theme's structural colours, and the tail
    # is one-off accents. Name as the tie-break so the row does not reshuffle
    # between visits.
    found = sorted(counts.keys(), key=lambda c: (-counts[c], c))[:limit]
    # ALWAYS exactly `limit` entries. The page binds a chip to a fixed index,
    # and a short list makes every one of those bindings error -- 16 red boxes
    # where the palette should be. Returning [] on failure did exactly that
    # for the first seconds of a new theme's life.
    return found + [""] * (limit - len(found))


def value_problem(name, old, new):
    """The sentence to refuse a save with, or '' to allow it.

    Judged against what the token ALREADY holds: a theme's values are colours,
    lengths and keywords all in one list, so 'is it a colour' is only a
    question for a token that currently is one.
    """
    text = (new or "").strip()
    if not text:
        return "%s cannot be empty. Type a value, or leave it alone." % name
    if ";" in text or "}" in text:
        return ("%s cannot contain ; or } -- that would break the rest of the "
                "file. Use Advanced if you mean to edit the CSS itself." % name)
    if is_colour(old) and not looks_like_colour(text):
        return ("'%s' is not a colour, so %s would stop working. Use a hex "
                "like #b81d38, a colour name like firebrick, or var(--other) "
                "to point at another value." % (text, name))
    return ""


def set_any_token(theme, name, value):
    """set_token, but it finds the file for you.

    The page cannot pass a filename it never showed the user, and guessing
    variables.css silently edited nothing for every --st-* token: the write
    went to a file that does not declare it, _token_replace raised, and the
    status line said so -- but only after the user had typed a colour and
    pressed Save.
    """
    filename = token_file(theme, name)
    old = ""
    for row in tokens(theme, filename):
        if row["name"] == name:
            old = row["value"]
    problem = value_problem(name, old, value)
    if problem:
        raise ValueError(problem)
    result = set_token(theme, name, value, filename=filename)
    # The value we replaced, so the page can offer to put it back. Nobody
    # remembers the hex they overwrote, and until now nothing else did either.
    if isinstance(result, dict):
        result["was"] = old
        return result
    return {"was": old}
