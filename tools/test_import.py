#!/usr/bin/env python3
"""Run import_code.check_import() under CPython against a good theme and one
zip per refusal. The gateway parts are replaced by two small functions.

Usage: python3 tools/test_import.py      exit 1 on any failure
"""

import io
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NS = {"re": re, "os": os, "json": __import__("json"), "Throwable": Exception,
      "EDITOR_ID_RE": re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$')}
exec(compile(open(os.path.join(HERE, "import_code.py")).read(),
             "import_code.py", "exec"), NS)
check = NS["check_import"]

KINDS = {"dark": "stock", "light": "stock", "nord-dark": "packaged",
         "mine": "user"}
BASE = {"--containerRoot": "#1a1a1a", "--container": "#222222",
        "--containerNested": "#2a2a2a", "--label": "#e8e8e8"}


def kind_of(name):
    return KINDS.get(name, "missing")


def zip_of(files, folder="", links=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(folder + name, text)
        for name in links:
            info = zipfile.ZipInfo(folder + name)
            info.external_attr = 0o120777 << 16
            zf.writestr(info, "../../etc/passwd")
    return buf.getvalue()


GOOD = {
    "index.css": '@import "../dark/index.css";\n@import "./variables.css";\n',
    "variables.css": ":root { color-scheme: dark; --label: #f0f0f0; "
                     "--callToAction: #4fa3ff; }\n"
                     ".x { background: url(\"data:image/png;base64,iVBOR\"); }\n",
    "README.md": "hello",
}


def run(files, *, folder="", zip_name="ocean-dark.zip", name=None, raw=None,
        links=()):
    data = raw if raw is not None else zip_of(files, folder, links)
    return check(data, zip_name, name, kind_of, lambda b: dict(BASE))


CASES = [
    # (label, kwargs, expect_ok, a substring one block or warning must have)
    ("good theme", dict(files=GOOD), True, None),
    ("good theme in a folder", dict(files=GOOD, folder="sea-light/"), True, None),
    ("scroll-behavior is fine", dict(files=dict(GOOD, **{"variables.css": ":root{color-scheme:dark}html{scroll-behavior:auto;overscroll-behavior:none}"})), True, None),
    ("escaped / in a class is fine", dict(files=dict(GOOD, **{"variables.css": ":root{color-scheme:dark}.psc-st\\/a\\/b{color:red}"})), True, None),
    ("remote url()", dict(files=dict(GOOD, **{"variables.css": ".a{background:url(https://x.test/a.png)}"})), False, "url("),
    ("protocol-relative url", dict(files=dict(GOOD, **{"variables.css": ".a{background:url(//x.test/a.png)}"})), False, "url("),
    ("relative url", dict(files=dict(GOOD, **{"variables.css": ".a{background:url(a.png)}"})), False, "url("),
    ("remote @import", dict(files=dict(GOOD, **{"index.css": '@import "https://x.test/a.css";'})), False, "@import"),
    ("@import url()", dict(files=dict(GOOD, **{"index.css": '@import url(//x.test/a.css);'})), False, "@import"),
    ("@import missing file", dict(files=dict(GOOD, **{"index.css": '@import "./nope.css";'})), False, "not in the zip"),
    ("@import base from non-index", dict(files=dict(GOOD, **{"variables.css": '@import "../dark/index.css";'})), False, "@import"),
    ("@import traversal", dict(files=dict(GOOD, **{"index.css": '@import "../../x/index.css";'})), False, "@import"),
    ("@import with media", dict(files=dict(GOOD, **{"index.css": '@import "./variables.css" print;'})), False, "media"),
    ("base missing on gateway", dict(files=dict(GOOD, **{"index.css": '@import "../nope/index.css";'})), False, "does not have"),
    ("expression()", dict(files=dict(GOOD, **{"variables.css": ".a{width:expression(alert(1))}"})), False, "expression"),
    ("javascript:", dict(files=dict(GOOD, **{"variables.css": ".a{x:javascript:alert(1)}"})), False, "javascript"),
    ("-moz-binding", dict(files=dict(GOOD, **{"variables.css": ".a{-moz-binding:x}"})), False, "binding"),
    ("behavior", dict(files=dict(GOOD, **{"variables.css": ".a{behavior:x}"})), False, "behavior"),
    ("close style", dict(files=dict(GOOD, **{"variables.css": "</style><script>"})), False, "</"),
    ("escaped url", dict(files=dict(GOOD, **{"variables.css": ".a{background:u\\72l(https://x.test)}"})), False, "escape"),
    ("image-set", dict(files=dict(GOOD, **{"variables.css": '.a{background:image-set("https://x.test/a.png" 1x)}'})), False, "image-set"),
    ("unclosed comment", dict(files=dict(GOOD, **{"variables.css": "/* never closed url(https://x)"})), False, "comment"),
    ("script file", dict(files=dict(GOOD, **{"evil.js": "alert(1)"})), False, ".css files"),
    ("svg file", dict(files=dict(GOOD, **{"logo.svg": "<svg/>"})), False, ".css files"),
    ("traversal path", dict(files=dict(GOOD, **{"../evil.css": "a{}"})), False, "leaves"),
    ("absolute path", dict(files=dict(GOOD, **{"/etc/evil.css": "a{}"})), False, "leaves"),
    ("sub-folder", dict(files=dict(GOOD, **{"sub/a.css": "a{}"})), False, "sub-folders"),
    ("symlink", dict(files=GOOD, links=("link.css",)), False, "symbolic"),
    ("no index", dict(files={"variables.css": ":root{--a:#fff}"}), False, "index.css"),
    ("not utf-8", dict(files=dict(GOOD, **{"variables.css": b"\xff\xfe\x00a"})), False, "UTF-8"),
    ("id clash with ours", dict(files=GOOD, zip_name="nord-dark.zip"), False, "already"),
    ("id clash with stock", dict(files=GOOD, name="dark"), False, "already"),
    ("id clash with user", dict(files=GOOD, name="mine"), False, "already"),
    ("bad id", dict(files=GOOD, name="../x"), False, "usable theme id"),
    ("not a zip", dict(files={}, raw=b"hello"), False, "Not a zip"),
    ("too big", dict(files={}, raw=b"x" * (2 * 1024 * 1024 + 1)), False, "limit"),
    ("too many entries", dict(files=dict(("f%d.css" % i, "a{}") for i in range(50))), False, "entries"),
]


def main():
    failures = 0
    for label, kwargs, expect_ok, needle in CASES:
        report = run(**kwargs)
        said = report["blocks"] + report["warnings"]
        good = report["ok"] == expect_ok and (
            needle is None or any(needle in s for s in said))
        if expect_ok and report["blocks"]:
            good = False
        failures += not good
        print("%-4s %-28s ok=%s %s" % ("pass" if good else "FAIL", label,
                                       report["ok"], "; ".join(said)[:110]))
    big = run(files=dict(GOOD, **{"variables.css": "a{}" + " " * (1024 * 1024 + 10)}))
    ok = not big["ok"] and any("limit" in b for b in big["blocks"])
    failures += not ok
    print("%-4s %-28s %s" % ("pass" if ok else "FAIL", "file too big", big["blocks"]))
    # Quality warnings, not blocks.
    low = run(files=dict(GOOD, **{"variables.css": ":root{--label:#333333}"}))
    ok = low["ok"] and low["contrast"] and any("color-scheme" in w for w in low["warnings"])
    failures += not ok
    print("%-4s %-28s contrast=%s" % ("pass" if ok else "FAIL", "low contrast warns",
                                      low["contrast"][:2]))
    good = run(files=GOOD)
    ok = good["id"] == "ocean-dark" and good["dark"] is True and good["ignored"] == ["README.md"] \
        and sorted(good["files"]) == ["index.css", "variables.css"]
    failures += not ok
    print("%-4s %-28s id=%s dark=%s files=%s" % ("pass" if ok else "FAIL", "good theme details",
                                                good["id"], good["dark"], sorted(good["files"])))
    print("%d failure(s)" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
