"""Writes MO2ModlistManager_strings\\translations\\<language>.txt ($KEY<TAB>text, UTF-16LE with a BOM - the shape of our SKSE
translation files, which .MD\\scripts\\translation-coverage.py reads).

English is read out of the plugin's own TR("KEY", "English") calls (the code is the one source of English). The other ten
languages are tools\\translations-src\\<language>.txt, one "KEY = text" line per key ("\\n" is a line break). Run from the
repo root after changing a string:  py -3 tools\\write_translations.py

It refuses to write when a language lacks a key, has one the code does not ask for, or changes a {placeholder}.
"""
import ast
import codecs
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "MO2ModlistManager.py")
SRC = os.path.join(ROOT, "tools", "translations-src")
OUT = os.path.join(ROOT, "MO2ModlistManager_strings", "translations")
LANGS = ["japanese", "korean", "chinese", "russian", "german", "french", "spanish", "italian", "polish", "czech"]


def english():
    tree = ast.parse(io.open(PLUGIN, encoding="utf-8-sig").read())
    out = {}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "TR" and len(n.args) >= 2
                and isinstance(n.args[0], ast.Constant) and isinstance(n.args[1], ast.Constant) and n.args[0].value != "KEY"):
            out.setdefault(n.args[0].value, n.args[1].value)
    return out


def read_src(lang):
    table = {}
    for ln in io.open(os.path.join(SRC, lang + ".txt"), encoding="utf-8").read().split("\n"):
        ln = ln.rstrip("\r")
        if not ln.strip():
            continue
        key, sep, text = ln.partition(" = ")
        if not sep:
            raise SystemExit("%s: line without ' = ': %r" % (lang, ln[:60]))
        table[key.strip()] = text
    return table


def esc(text):
    return text.replace("\n", "\\n")


def main():
    en = english()
    problems = []
    tables = {}
    for lang in LANGS:
        t = read_src(lang)
        tables[lang] = t
        for k in sorted(set(en) - set(t)):
            problems.append("%s: missing %s" % (lang, k))
        for k in sorted(set(t) - set(en)):
            problems.append("%s: not asked for by the code: %s" % (lang, k))
        for k in set(en) & set(t):
            a = sorted(re.findall(r"\{\w+\}", en[k]))
            b = sorted(re.findall(r"\{\w+\}", t[k].replace("\\n", "\n")))
            if a != b:
                problems.append("%s: %s placeholders %s != %s" % (lang, k, b, a))
    if problems:
        print("\n".join(problems))
        return 1
    os.makedirs(OUT, exist_ok=True)

    def write(lang, table):
        body = "".join("$%s\t%s\r\n" % (k, esc(table[k]) if lang == "english" else table[k]) for k in en)
        with open(os.path.join(OUT, lang + ".txt"), "wb") as fh:
            fh.write(codecs.BOM_UTF16_LE + body.encode("utf-16-le"))
    write("english", en)
    for lang in LANGS:
        write(lang, tables[lang])
    print("wrote %d files, %d keys each, to %s" % (1 + len(LANGS), len(en), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
