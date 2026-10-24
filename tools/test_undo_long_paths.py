"""Undo / Restore on backup paths longer than 260 characters, and the all-or-nothing restore (test afe4, 2026-10-24:
"Undo this Apply" failed with "[WinError 3] The system cannot find the path specified" moving a separator folder into
backups\\<stamp>-before-restore\\retired-separators\\<name>, a 269-character path, and stopped half-way).

ModOrganizer.exe 2.5.2 is not long-path aware, python.exe is; as in test_long_paths.py the process's PEB
IsLongPathAwareProcess bit is cleared so the plugin runs the way MO2 runs it, and the emulation is proved first.
The instance is deep enough that the 1.1.5 backup layout passes 260 characters AND the 1.1.6 short layout does too,
so the checks prove the long form, not only the shorter names.

Checks:
  1 Apply on the deep instance writes its backup (separators by number, seps.json naming them);
  2 a restore failed on purpose at EVERY step in turn (fail_at_step) is rolled back: the whole instance - profile,
    mods folder, backups - is byte for byte as before, and nothing is left half-done;
  3 a real failure mid-way (a file held open inside a separator folder the restore must move) is rolled back too;
  4 the check before writing refuses a restore that cannot be done (a read-only plugins.txt) and writes nothing;
  5 the full Undo: modlist.txt, plugins.txt and loadorder.txt are byte-identical to the backup, the mods folder is as
    it was before the Apply (created separators set aside, retired ones back, moved plugins back);
  6 the before-restore backup restores the Apply's state again (the restore can itself be restored);
  7 a backup in 1.1.5's layout (retired-separators\\<full name>, yyyymmdd-HHMMSS-before-restore) is listed and restored.

    py -3 tools\\test_undo_long_paths.py [--root DIR] [--no-emulate]      exit 0 = ALL PASS
Nothing outside --root (default: mm-undo-longpath-scratch in the temp folder) is written.
"""
import ctypes, ctypes.wintypes as wt, importlib.util, json, os, shutil, stat, struct, sys, tempfile, types

args = sys.argv[1:]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = args[args.index("--root") + 1] if "--root" in args else os.path.join(tempfile.gettempdir(), "mm-undo-longpath-scratch")
EMULATE = "--no-emulate" not in args
stub = types.ModuleType("mobase")
stub.__getattr__ = lambda n: type(n, (object,), {"__init__": lambda self, *a, **k: None})
sys.modules["mobase"] = stub

bad = 0


def ok(cond, what):
    global bad
    print(("PASS " if cond else "FAIL ") + what)
    bad += 0 if cond else 1


def X(p):
    return "\\\\?\\" + os.path.abspath(p)       # the test's own reads and writes go through the prefix


def plugin_bytes(masters):
    sub = b"HEDR" + struct.pack("<H", 12) + struct.pack("<fII", 1.7, 0, 0x800)
    for m in masters:
        name = m.encode("cp1252") + b"\x00"
        sub += b"MAST" + struct.pack("<H", len(name)) + name + b"DATA" + struct.pack("<H", 8) + b"\x00" * 8
    return b"TES4" + struct.pack("<IIIII", len(sub), 0, 0, 0, 0)[:20] + sub


# the instance folder: long enough that cache\backups\<stamp>r\seps\0\meta.ini passes 260, short enough that the
# profile and mod paths (not this test's subject) stay under it
NAME = "Skyrim Special Edition - A Portable Instance Folder With A Deliberately Long Name For Testing"
INST = os.path.join(ROOT, NAME)
while len(INST) < 196:
    INST = os.path.join(INST, "nested folder")
INST = INST[:196].rstrip(" \\")
GAME = os.path.join(ROOT, "game")
DATA = os.path.join(GAME, "Data")
MODS = os.path.join(INST, "mods")
PROF = os.path.join(INST, "profiles", "Default")
CACHE = os.path.join(INST, "plugins", "data", "MO2ModlistManager")
BASE = ["Skyrim.esm", "Update.esm", "Dawnguard.esm", "HearthFires.esm", "Dragonborn.esm"]
HANDMADE = "My Own Hand Made Separator Name_separator"


def put(p, data):
    os.makedirs(X(os.path.dirname(p)), exist_ok=True)
    open(X(p), "wb").write(data if isinstance(data, bytes) else data.encode("utf-8"))


def build():
    if os.path.isdir(X(ROOT)):
        shutil.rmtree(X(ROOT))
    for f in BASE:
        put(os.path.join(DATA, f), plugin_bytes([]))
    put(os.path.join(INST, "ModOrganizer.ini"),
        "[General]\ngameName=Skyrim Special Edition\ngamePath=@ByteArray(%s)\n[Settings]\n" % GAME.replace("\\", "\\\\"))
    os.makedirs(X(os.path.join(INST, "overwrite")), exist_ok=True)
    mods = [("A Plain Mod", "A Plain Mod.esp", BASE[:1]),
            ("SkyUI", "SkyUI_SE.esp", BASE[:1]),
            ("Needs A Missing Mod", "Needs A Missing Mod.esp", ["Skyrim.esm", "Not Installed Anywhere.esm"])]
    lines = []
    for folder, plugin, masters in mods:
        put(os.path.join(MODS, folder, "meta.ini"), "[General]\nmodid=0\nversion=1.0\n")
        put(os.path.join(MODS, folder, plugin), plugin_bytes(masters))
        lines.append("+" + folder)
    put(os.path.join(MODS, HANDMADE, "meta.ini"), "[General]\ncolor=#ff000000\nmodid=0\n")
    lines.append("+" + HANDMADE)
    put(os.path.join(PROF, "modlist.txt"), "# This file was automatically generated by Mod Organizer.\r\n"
        + "\r\n".join(reversed(lines)) + "\r\n")
    every = BASE + [p for _f, p, _m in mods]
    put(os.path.join(PROF, "loadorder.txt"), "# This file was automatically generated by Mod Organizer.\r\n" + "\r\n".join(every) + "\r\n")
    put(os.path.join(PROF, "plugins.txt"), "# This file was automatically generated by Mod Organizer.\r\n"
        + "".join("*" + p + "\r\n" for p in every if p not in BASE))


def snapshot(top=INST):
    """Every folder and every file's bytes under top."""
    out = {}
    for d, dirs, files in os.walk(X(top)):
        rel = os.path.relpath(d, X(top))
        out[rel + "\\"] = None
        for f in files:
            out[os.path.join(rel, f)] = open(os.path.join(d, f), "rb").read()
    return out


def diff(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k, 0) != b.get(k, 0))[:6]


def set_long_path_aware(on):
    class PBI(ctypes.Structure):
        _fields_ = [("ExitStatus", ctypes.c_void_p), ("PebBaseAddress", ctypes.c_void_p), ("Affinity", ctypes.c_void_p),
                    ("Priority", ctypes.c_void_p), ("Pid", ctypes.c_void_p), ("Parent", ctypes.c_void_p)]
    pbi = PBI()
    nt = ctypes.WinDLL("ntdll")
    nt.NtQueryInformationProcess(wt.HANDLE(-1), 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None)
    flags = ctypes.c_ubyte.from_address(pbi.PebBaseAddress + 3)
    flags.value = (flags.value | 0x80) if on else (flags.value & 0x7F)


build()
probe = os.path.join(CACHE, "backups", "261024-044106r", "seps", "0", "meta.ini")
put(probe, "x")
if EMULATE:
    set_long_path_aware(False)
    try:
        open(probe, "rb").close()
        ok(False, "emulation: a 260+ path still opens, so this run would not behave like MO2")
    except OSError as e:
        ok(isinstance(e, FileNotFoundError) and os.path.isfile(X(probe)),
           f"emulation: a {len(probe)}-character path that exists fails the way it does in MO2: {e!r}")
shutil.rmtree(X(os.path.join(CACHE, "backups")))

spec = importlib.util.spec_from_file_location("mm_under_test", os.path.join(HERE, "MO2ModlistManager.py"))
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)
print("plugin", mm.__version__, f"instance path {len(INST)} chars")

# 1 Apply
res = mm.run(INST, "Default", CACHE)
created, retired = list(res["facts"]["created"]), list(res["facts"]["retired"])
print(f"   plan: {len(created)} separators created, {len(retired)} retired, plugin moves "
      f"{len(res['plugin_state'].get('to_optional', []))}")
longest = max(created, key=len)
old_layout = os.path.join(CACHE, "backups", "20261024-044106-before-restore", "retired-separators", longest, "meta.ini")
new_layout = os.path.join(CACHE, "backups", "261024-044106r", "seps", "0", "meta.ini")
ok(len(old_layout) > 260 and len(new_layout) > 260,
   f"1 both layouts pass 260 characters here (1.1.5: {len(old_layout)}, 1.1.6: {len(new_layout)}), so the long form is what is tested")
ok(created and retired, f"1 the plan creates and retires separators (created {created[:2]}..., retired {retired})")
pre_apply = snapshot(MODS)
lists_before = {f: open(X(os.path.join(PROF, f)), "rb").read() for f in ("modlist.txt", "plugins.txt", "loadorder.txt")}
try:
    backup = mm.apply(res, INST, "Default", CACHE)
    ok(True, "1 Apply finished on the deep instance")
except Exception as exc:  # noqa: BLE001
    ok(False, f"1 Apply raised {exc!r}")
    print("FAILED: %d" % bad)
    sys.exit(1)
smap = json.load(open(X(os.path.join(backup, "seps", "seps.json")), encoding="utf-8"))
ok(sorted(smap.values()) == sorted(retired) and all(k.isdigit() for k in smap),
   f"1 the retired separators are in seps\\ by number, seps.json names them: {smap}")
ok(not os.path.exists(X(os.path.join(backup, "retired-separators"))), "1 no full-name retired-separators folder")
ok(not os.path.isfile(X(os.path.join(MODS, "Needs A Missing Mod", "Needs A Missing Mod.esp"))), "1 Apply moved the plugin")
after_apply = snapshot()

# 2 a failure at every step in turn is rolled back
k, total, bad2 = 1, None, 0
while k < 80:
    try:
        safety = mm.restore_backup(backup, INST, "Default", CACHE, fail_at_step=k)[0]
        total = k - 1
        break
    except mm.RestoreFailed as exc:
        now = snapshot()
        if not (exc.rolled_back and now == after_apply):
            ok(False, f"2 failure at step {k}: rolled back {exc.rolled_back}, differences {diff(after_apply, now)}; {exc}")
            bad2 += 1
        if k == 1:
            print("   message:", str(exc)[:200])
    k += 1
ok(total and total >= 8 and bad2 == 0, f"2 a failure at each of the {total} steps left the whole instance byte for byte as before")

# put the Apply state back for the remaining checks (step 2's last call made the full restore)
mm.restore_backup(safety, INST, "Default", CACHE)
shutil.rmtree(X(safety))
for n in os.listdir(X(os.path.join(CACHE, "backups"))):
    if n != os.path.basename(backup):
        shutil.rmtree(X(os.path.join(CACHE, "backups", n)))
ok(snapshot() == after_apply, "2 (set-up) the Apply state is back: " + str(diff(after_apply, snapshot())))

# 3 a real failure: a file held open inside the last separator the restore must move aside
held = open(X(os.path.join(MODS, sorted(created)[-1], "meta.ini")), "rb")
try:
    mm.restore_backup(backup, INST, "Default", CACHE)
    ok(False, "3 the restore went through although a separator folder could not be moved")
except mm.RestoreFailed as exc:
    ok(exc.rolled_back and snapshot() == after_apply,
       f"3 a real mid-way failure is rolled back, nothing half-done ({str(exc)[:150]}): {diff(after_apply, snapshot())}")
except Exception as exc:  # noqa: BLE001
    ok(False, f"3 the restore failed without a roll-back: {exc!r}")
finally:
    held.close()

# 4 the check before writing
pt = X(os.path.join(PROF, "plugins.txt"))
os.chmod(pt, stat.S_IREAD)
try:
    mm.restore_backup(backup, INST, "Default", CACHE)
    ok(False, "4 a restore onto a read-only plugins.txt was not refused")
except mm.RestoreFailed as exc:
    ok(exc.rolled_back and snapshot() == after_apply and "plugins.txt" in str(exc),
       f"4 refused before writing anything: {str(exc)[:160]}")
finally:
    os.chmod(pt, stat.S_IREAD | stat.S_IWRITE)

# 5 the full Undo
try:
    safety, aside, brought, undone = mm.restore_backup(backup, INST, "Default", CACHE)
    ok(True, f"5 Undo finished: {len(aside)} set aside, {len(brought)} brought back, {len(undone)} plugin(s) moved back")
except Exception as exc:  # noqa: BLE001
    ok(False, f"5 Undo raised {exc!r}")
    print("FAILED: %d" % bad)
    sys.exit(1)
for f, b in lists_before.items():
    ok(open(X(os.path.join(PROF, f)), "rb").read() == open(X(os.path.join(backup, f)), "rb").read() == b,
       f"5 {f} byte-identical to the backup")
ok(snapshot(MODS) == pre_apply, "5 the mods folder is as before the Apply: " + str(diff(pre_apply, snapshot(MODS))))
ok(os.path.basename(safety).endswith("r") and os.path.isfile(X(os.path.join(safety, "seps", "seps.json"))),
   f"5 the replaced state is a short-named backup with its separators by number: {os.path.basename(safety)}")
listed = mm.list_backups(CACHE, INST)
ok([b[0] for b in listed][:2] == [os.path.basename(safety), os.path.basename(backup)] and listed[0][4] == "before a restore",
   f"5 Restore backup lists both, newest first: {[(b[0], b[4]) for b in listed]}")

# 6 the restore can itself be restored
mm.restore_backup(safety, INST, "Default", CACHE)
want = set(os.listdir(X(MODS)))
ok(set(created) <= want and not (set(retired) & want), "6 restoring the before-restore backup brings the Apply's separators back")
ok(all(open(X(os.path.join(PROF, f)), "rb").read() == after_apply[os.path.join("profiles", "Default", f)]
       for f in ("modlist.txt", "plugins.txt", "loadorder.txt")), "6 and the Apply's lists, byte for byte")

# 7 a 1.1.5-layout backup
build()
res = mm.run(INST, "Default", CACHE)
b2 = mm.apply(res, INST, "Default", CACHE)
before7 = snapshot(MODS)
old = os.path.join(CACHE, "backups", "20261024-044106")
os.rename(X(b2), X(old))
m = json.load(open(X(os.path.join(old, "seps", "seps.json")), encoding="utf-8"))
os.makedirs(X(os.path.join(old, "retired-separators")))
for i, n in m.items():
    os.rename(X(os.path.join(old, "seps", i)), X(os.path.join(old, "retired-separators", n)))
shutil.rmtree(X(os.path.join(old, "seps")))
ok(any(b[0] == "20261024-044106" for b in mm.list_backups(CACHE, INST)), "7 a 1.1.5-named backup is listed")
mm.restore_backup(old, INST, "Default", CACHE)
ok(set(retired) <= set(os.listdir(X(MODS))) and not (set(created) & set(os.listdir(X(MODS)))),
   "7 a 1.1.5-layout backup restores: its retired separators are back, the created ones set aside")
ok(open(X(os.path.join(PROF, "modlist.txt")), "rb").read() == open(X(os.path.join(old, "modlist.txt")), "rb").read(),
   "7 its modlist.txt is back byte for byte")

print("ALL PASS" if not bad else "FAILED: %d" % bad)
sys.exit(1 if bad else 0)
