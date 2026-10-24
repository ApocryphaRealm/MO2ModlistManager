"""The master cascade (Nexus report, 2026-10-24: "It disabled half of the plugins out of 1080 ... a chain reaction: the
'manager' stumbles on some master and, down the chain, disables every thing connected to it").

A synthetic instance, nothing outside --root is written. Its masters live where MO2 finds them but no mod folder holds
them: the game's Data folder (Creation Club plugins listed in Skyrim.ccc - the four USSEP 4.3 needs on an Anniversary
Edition game - and a plugin installed straight into Data), and MO2's Overwrite folder. MO2 2.5.2 builds the right pane
from the whole virtual Data folder (pluginlist.cpp PluginList::refresh), so all of them load. A chain of plugins is
built on them. One master is truly absent, with a chain of its own, as the control.

Checks:
  1 nothing whose masters are in the game's Data folder or Overwrite is moved or switched off;
  2 the truly missing master is still found, and its chain is reported as a chain from it;
  3 a disabled duplicate copy of a master (the 2026-10-21 to-do: a disabled test build) changes nothing;
  4 Apply with plugins kept as they are moves no file and keeps every plugin's tick as it was;
  5 Apply, then Restore backup, gives back modlist.txt, plugins.txt and loadorder.txt byte for byte, and the moved
    plugin files are back in their mods' roots.

    py -3 tools\\test_master_cascade.py [--plugin <MO2ModlistManager.py>] [--root DIR]     exit 0 = ALL PASS
--plugin runs the same checks against another copy of the plugin (git show v1.1.5:MO2ModlistManager.py > old.py).
"""
import importlib.util, os, shutil, struct, sys, tempfile, types

args = sys.argv[1:]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = args[args.index("--plugin") + 1] if "--plugin" in args else os.path.join(HERE, "MO2ModlistManager.py")
ROOT = args[args.index("--root") + 1] if "--root" in args else os.path.join(tempfile.gettempdir(), "mm-cascade-scratch")

stub = types.ModuleType("mobase")
stub.__getattr__ = lambda n: type(n, (object,), {"__init__": lambda self, *a, **k: None})
sys.modules["mobase"] = stub
spec = importlib.util.spec_from_file_location("mm_under_test", PLUGIN)
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)
print("plugin under test:", PLUGIN, "version", getattr(mm, "__version__", "?"))

bad = 0


def ok(cond, what):
    global bad
    print(("PASS " if cond else "FAIL ") + what)
    bad += 0 if cond else 1


def plugin_bytes(masters, esm=False, light=False):
    """A TES4 header with MAST/DATA pairs and nothing else - what read_header reads."""
    sub = b"HEDR" + struct.pack("<H", 12) + struct.pack("<fII", 1.7, 0, 0x800)
    for m in masters:
        name = m.encode("cp1252") + b"\x00"
        sub += b"MAST" + struct.pack("<H", len(name)) + name + b"DATA" + struct.pack("<H", 8) + b"\x00" * 8
    flags = (1 if esm else 0) | (0x200 if light else 0)
    return b"TES4" + struct.pack("<IIIII", len(sub), flags, 0, 0, 0)[:20] + sub


INST = os.path.join(ROOT, "instance")
GAME = os.path.join(ROOT, "game")
DATA = os.path.join(GAME, "Data")
MODS = os.path.join(INST, "mods")
OVER = os.path.join(INST, "overwrite")
PROF = os.path.join(INST, "profiles", "Default")
CACHE = os.path.join(INST, "plugins", "data", "MO2ModlistManager")
BASE = ["Skyrim.esm", "Update.esm", "Dawnguard.esm", "HearthFires.esm", "Dragonborn.esm"]
CC = ["ccBGSSSE001-Fish.esm", "ccQDRSSE001-SurvivalMode.esl", "ccBGSSSE037-Curios.esl", "ccBGSSSE025-AdvDSGS.esm"]
USSEP = "Unofficial Skyrim Special Edition Patch.esp"


def build_instance(with_disabled_copy=False):
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT)
    for d in (DATA, MODS, OVER, PROF, CACHE):
        os.makedirs(d)
    for f in BASE + CC:
        open(os.path.join(DATA, f), "wb").write(plugin_bytes([], esm=True, light=f.endswith(".esl")))
    open(os.path.join(GAME, "Skyrim.ccc"), "w", newline="\r\n").write("\n".join(CC) + "\n")
    open(os.path.join(DATA, "Installed Into Data.esp"), "wb").write(plugin_bytes(BASE[:1]))     # an unmanaged plugin
    open(os.path.join(OVER, "Generated In Overwrite.esp"), "wb").write(plugin_bytes(BASE[:1]))  # a tool's output
    open(os.path.join(INST, "ModOrganizer.ini"), "w").write(
        "[General]\ngameName=Skyrim Special Edition\ngamePath=@ByteArray(%s)\n[Settings]\n" % GAME.replace("\\", "\\\\"))
    mods = [  # (folder, plugin, masters), top of the left pane first
        ("A Plain Mod", "A Plain Mod.esp", BASE[:1]),          # loads on any version: the lists are never empty
        ("Unofficial Skyrim Special Edition Patch", USSEP, BASE + CC),
        ("Built On USSEP", "Built On USSEP.esp", BASE[:2] + [USSEP]),
        ("Second Link", "Second Link.esp", ["Skyrim.esm", "Built On USSEP.esp"]),
        ("Third Link", "Third Link.esp", ["Skyrim.esm", "Second Link.esp", USSEP]),
        ("Needs The Data Plugin", "Needs The Data Plugin.esp", ["Skyrim.esm", "Installed Into Data.esp"]),
        ("Needs The Overwrite Plugin", "Needs The Overwrite Plugin.esp", ["Skyrim.esm", "Generated In Overwrite.esp"]),
        ("Needs A Missing Mod", "Needs A Missing Mod.esp", ["Skyrim.esm", "Not Installed Anywhere.esm"]),
        ("Chain From The Missing One", "Chain From The Missing One.esp", ["Skyrim.esm", "Needs A Missing Mod.esp"]),
    ]
    if with_disabled_copy:   # a disabled test build that ships the same master, ABOVE the enabled one
        mods.insert(0, ("test Unofficial Skyrim Special Edition Patch", USSEP, BASE + CC + ["Not Installed Anywhere.esm"]))
    lines = []
    for folder, plugin, masters in mods:
        d = os.path.join(MODS, folder)
        os.makedirs(d)
        open(os.path.join(d, "meta.ini"), "w").write("[General]\nmodid=0\nversion=1.0\n")
        open(os.path.join(d, plugin), "wb").write(plugin_bytes(masters))
        lines.append(("-" if folder.startswith("test ") else "+") + folder)
    open(os.path.join(PROF, "modlist.txt"), "w", newline="\r\n").write(
        "# This file was automatically generated by Mod Organizer.\n" + "\n".join(reversed(lines)) + "\n")
    every = BASE + CC + ["Installed Into Data.esp", "Generated In Overwrite.esp"] + [p for f, p, _ in mods if not f.startswith("test ")]
    open(os.path.join(PROF, "loadorder.txt"), "w", newline="\r\n").write(
        "# This file was automatically generated by Mod Organizer.\n" + "\n".join(every) + "\n")
    open(os.path.join(PROF, "plugins.txt"), "w", newline="\r\n").write(
        "# This file was automatically generated by Mod Organizer.\n" + "\n".join("*" + p for p in every if p not in BASE + CC) + "\n")


def parked(res):
    ps = res["plugin_state"]
    return {f: why for f, _m, why in ps.get("to_optional", []) + ps.get("keep_off", [])}


def files():
    return {f: open(os.path.join(PROF, f), "rb").read() for f in ("modlist.txt", "plugins.txt", "loadorder.txt")}


build_instance()
res = mm.run(INST, "Default", CACHE)
out = parked(res)
print("   parked:", {k: v[:70] for k, v in out.items()})
for p in (USSEP, "Built On USSEP.esp", "Second Link.esp", "Third Link.esp"):
    ok(p not in out, f"1 {p}: masters in the game's Data folder (Skyrim.ccc) - not moved")
ok("Needs The Data Plugin.esp" not in out, "1 a master installed straight into Data - not moved")
ok("Needs The Overwrite Plugin.esp" not in out, "1 a master in Overwrite - not moved")
ok("Needs A Missing Mod.esp" in out and "Not Installed Anywhere.esm" in out.get("Needs A Missing Mod.esp", ""),
   "2 a master in no mod, Data or Overwrite is still found: " + out.get("Needs A Missing Mod.esp", "(not found)"))
chain = res["plugin_state"].get("chain", {})
ok("chain from the missing one.esp" in chain or "Chain From The Missing One.esp" in chain,
   "2 its dependent is reported as a chain from that master: " + str(chain))
ok("Chain From The Missing One.esp" in out and "chain" in out.get("Chain From The Missing One.esp", "").lower(),
   "2 the chain's reason names it: " + out.get("Chain From The Missing One.esp", "(not found)"))

build_instance(with_disabled_copy=True)
res2 = mm.run(INST, "Default", CACHE)
ok(set(parked(res2)) == set(out), "3 a disabled copy of a master changes nothing: " + str(sorted(set(parked(res2)) ^ set(out))))

# 4 keep plugins as they are
build_instance()
res = mm.run(INST, "Default", CACHE)
before = files()
try:
    mm.apply(res, INST, "Default", CACHE, plugin_moves=False)
    still = all(os.path.isfile(os.path.join(MODS, f, p)) for f, p in (("Needs A Missing Mod", "Needs A Missing Mod.esp"),
                                                                      ("Chain From The Missing One", "Chain From The Missing One.esp")))
    ok(still, "4 'leave plugins as they are': no plugin file moved")
    star = lambda b: {ln[1:] for ln in b.decode("cp1252").splitlines() if ln.startswith("*")}
    ok(star(files()["plugins.txt"]) == star(before["plugins.txt"]), "4 every plugin keeps the tick it had: "
       + str(sorted(star(files()["plugins.txt"]) ^ star(before["plugins.txt"]))))
    # Main Agent, 2026-10-24: plugin_moves=false still reordered plugins.txt. The right pane is left alone entirely;
    # the left pane (separators, mod order) is still written - that part of Apply is the manager's purpose
    after4 = files()
    ok(after4["plugins.txt"] == before["plugins.txt"] and after4["loadorder.txt"] == before["loadorder.txt"],
       "4 'leave plugins as they are': plugins.txt and loadorder.txt byte for byte as before (order and ticks)")
    ok(not os.path.exists(os.path.join(PROF, "plugingroups.txt")), "4 and no plugingroups.txt written")
    made = [n for n in res["facts"]["created"] if os.path.isdir(os.path.join(MODS, n))]
    ok(made and after4["modlist.txt"] != before["modlist.txt"],
       f"4 the left pane is still sorted: {len(made)} separator(s) created, modlist.txt rewritten")
    line = mm.left_pane_line(res)
    ok(str(len(res["facts"]["created"])) in line and "plugins.txt" in line, "4 the preview says it plainly: " + line[:140])
except TypeError as exc:
    ok(False, f"4 Apply cannot leave plugins as they are ({exc})")

# 5 Apply with the moves, then restore
build_instance()
res = mm.run(INST, "Default", CACHE)
before = files()
backup = mm.apply(res, INST, "Default", CACHE)
moved = not os.path.isfile(os.path.join(MODS, "Needs A Missing Mod", "Needs A Missing Mod.esp"))
ok(moved, "5 Apply moved the plugin with the missing master to Optional ESPs")
applied = files()
ticked = {ln[1:] for ln in applied["plugins.txt"].decode("cp1252").splitlines() if ln.startswith("*")}
listed = set(applied["loadorder.txt"].decode("utf-8").splitlines())
for p in ("Installed Into Data.esp", "Generated In Overwrite.esp"):
    ok(p in ticked and p in listed, f"5 Apply keeps {p} (no mod folder ships it) ticked in plugins.txt and in loadorder.txt")
ok(USSEP in ticked and "Third Link.esp" in ticked, "5 Apply keeps the USSEP chain ticked")
mm.restore_backup(backup, INST, "Default", CACHE)
after = files()
for f in before:
    ok(after[f] == before[f], f"5 restore: {f} byte for byte")
ok(os.path.isfile(os.path.join(MODS, "Needs A Missing Mod", "Needs A Missing Mod.esp"))
   and os.path.isfile(os.path.join(MODS, "Chain From The Missing One", "Chain From The Missing One.esp")),
   "5 restore: the moved plugins are back in their mods' roots")

# 6 the window: Apply shows every plugin it would switch off, with Cancel; Undo puts the files back in one click
if "--no-ui" not in args and hasattr(mm, "RulerDialog"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        from PyQt5.QtWidgets import QApplication, QMessageBox
    build_instance()
    app = QApplication.instance() or QApplication([])
    app.setProperty("dataPath", INST.replace("\\", "/"))

    load_orders = []

    class PluginList:
        def setLoadOrder(self, order): load_orders.append(list(order))

    class Org:
        def basePath(self): return INST.replace("\\", "/")
        def modsPath(self): return MODS.replace("\\", "/")
        def overwritePath(self): return OVER.replace("\\", "/")
        def profilePath(self): return PROF.replace("\\", "/")
        def profileName(self): return "Default"
        def refresh(self, save=True): pass
        def managedGame(self): raise RuntimeError("no game in the test")
        def pluginSetting(self, plugin, key): return None
        def setPluginSetting(self, plugin, key, value): pass
        def pluginList(self): return PluginList()

    p = mm.MO2ModlistManager()
    p._organizer = Org()
    p._verify_groups_later = lambda result: None
    shown = {}
    choice = {"button": None}
    real_exec = QMessageBox.exec

    box_info = {}

    def fake_exec(box):
        shown["text"], shown["details"] = box.text(), box.detailedText()
        box_info["info"] = box.informativeText()
        want = choice["button"]
        for b in box.buttons():
            if (want == "cancel" and box.buttonRole(b) == QMessageBox.ButtonRole.RejectRole) or b.text() == want:
                b.click()
                break
        return 0
    QMessageBox.exec = fake_exec
    try:
        dlg = mm.RulerDialog(p)
        before = files()
        choice["button"] = "cancel"
        dlg.apply()
        ok(files() == before and os.path.isfile(os.path.join(MODS, "Needs A Missing Mod", "Needs A Missing Mod.esp")),
           "6 Cancel writes nothing")
        ok("Needs A Missing Mod.esp" in shown.get("details", "") and "Chain From The Missing One.esp" in shown.get("details", "")
           and "chain" in shown.get("details", ""), "6 the preview lists every plugin it would switch off, with the reason")
        ok("1 of them" in shown.get("text", ""), "6 the preview counts the chain links: " + shown.get("text", "")[:120])
        choice["button"] = mm.TR("MM_SwitchOffKeep", "Apply, leave plugins as they are")
        load_orders.clear()
        dlg.apply()
        ok(not load_orders and files()["plugins.txt"] == before["plugins.txt"] and files()["loadorder.txt"] == before["loadorder.txt"],
           f"6 'Apply, leave plugins as they are' sets no load order in MO2 ({len(load_orders)} call(s)) and leaves both files as they were")
        ok("re-sorts the left" in shown.get("text", "") + box_info.get("info", ""), "6 the box says Apply adds separators and re-sorts the left pane")
        ok(os.path.isfile(os.path.join(MODS, "Needs A Missing Mod", "Needs A Missing Mod.esp")),
           "6 'Apply, leave plugins as they are' moved nothing")
        ok(dlg.b_undo.isVisibleTo(dlg), "6 Undo this Apply is offered after an Apply")
        dlg.b_undo.click()
        ok(files() == before, "6 Undo this Apply: the three lists are back byte for byte")
        ok(not dlg.b_undo.isVisibleTo(dlg), "6 Undo is withdrawn once used")
        choice["button"] = mm.TR("MM_SwitchOffYes", "Apply and switch them off")
        dlg.apply()
        ok(not os.path.isfile(os.path.join(MODS, "Needs A Missing Mod", "Needs A Missing Mod.esp")),
           "6 'Apply and switch them off' moves the plugin")
        dlg.b_undo.click()
        ok(files() == before and os.path.isfile(os.path.join(MODS, "Needs A Missing Mod", "Needs A Missing Mod.esp")),
           "6 Undo after switching off: lists byte for byte and the plugin back in its mod")
        dlg.close()
    finally:
        QMessageBox.exec = real_exec

print("ALL PASS" if not bad else "FAILED: %d" % bad)
sys.exit(1 if bad else 0)
