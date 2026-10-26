"""R38, the shout overhaul (2026-10-26): Stormcrown - A Shout Overhaul was filed under "Location Overhauls - Wilderness".

Its plugin alters 26 vanilla shouts and adds 2 with 6 words, and its 195 new spells and effects are those shouts' levels;
counted as plain magic they lost to the cells of its six new word walls and one cave. R38 counts ten or more shout records
(new or altered) as a shout overhaul whose spells are what the shouts do, and reads the cells it touches as where its
words are learnt, never as an overhaul of those places (as R31 reads where new equipment is put).

No instance is read: the record counts and votes below are Stormcrown's own, taken from the offline dry run of
2026-10-26 on Njordlinger Test.

Checks:
  1 Stormcrown's record counts give a strong Shouts record vote, not Magic;
  2 with its scope votes (the word-wall cells, the cave), decide() files it under Shouts;
  3 a mod with only a few new shout records keeps the plain "new shout/word records" vote (no overhaul);
  4 a spell pack that touches one or two shouts stays Magic - Spells & Enchantments;
  5 the cells of a mod that is NOT a shout overhaul keep their full weight.

    py -3 tools/test_shout_overhaul.py [--plugin <MO2ModlistManager.py>]     exit 0 = ALL PASS
--plugin runs the same checks against another copy of the plugin (git show 9831fee:MO2ModlistManager.py > old.py,
1.1.6 before R38: checks 1 and 2 fail there).
"""
import importlib.util, os, sys, types

args = sys.argv[1:]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = args[args.index("--plugin") + 1] if "--plugin" in args else os.path.join(HERE, "MO2ModlistManager.py")

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


STORMCROWN_RECORDS = {'TXST': 1, 'GLOB': 35, 'GLOB*': 1, 'SOUN': 1, 'MGEF*': 77, 'MGEF': 140, 'SPEL': 55, 'SPEL*': 88,
                      'ACTI': 7, 'ACTI*': 2, 'LIGH': 15, 'LIGH*': 3, 'STAT': 10, 'FURN': 1, 'NPC_': 6, 'PROJ': 12,
                      'PROJ*': 3, 'HAZD': 3, 'CELL~': 1542, 'WRLD~': 67131, 'DIAL*': 6, 'DIAL': 20, 'QUST': 1,
                      'QUST*': 1, 'IDLE': 2, 'FLST': 1, 'PERK': 37, 'MESG*': 3, 'MESG': 5, 'WOOP': 6, 'SHOU*': 26,
                      'SHOU': 2, 'SNDR': 1}
# its other votes in the dry run before R38 (the records vote is rebuilt from the counts above)
STORMCROWN_OTHER_VOTES = [("scope", "Location Overhauls - General", 3.0, "location overhaul: 52 of 94 references at 00000D74"),
                          ("scope", "Dungeons", 1.5, "references dungeon cells BleakcoastCave01"),
                          ("scope", "Location Overhauls - General", 2.4, "edits 7 exterior cells"),
                          ("text", "Shouts", 1.5, "says 'shout'")]


def mod(name, records, files=(), plugins=None):
    m = mm.Mod(name, True, 0)
    m.records = dict(records)
    m.files = list(files)
    m.plugins = plugins if plugins is not None else [(name + ".esp", ["Skyrim.esm"], False)]
    m.refs = {"cells_new": [], "cells_alt": ["BleakcoastCave01"], "worlds_new": [], "worlds_alt": ["Tamriel"],
              "ext": {}, "refs": {}}
    return m


# 1
sc = mod("Stormcrown - A Shout Overhaul", STORMCROWN_RECORDS, files=["stormcrown.bsa", "skse/plugins/customskills/dragonborn.json"])
rv = mm._records_vote(sc)
ok(rv is not None and rv[0] == "Shouts" and rv[1] == mm.W_RECORDS_STRONG, f"Stormcrown's records vote is a strong Shouts vote: {rv}")

# 2
votes = ([("records",) + tuple(rv)] if rv else []) + STORMCROWN_OTHER_VOTES
cat, why = mm.decide(sc, votes)[:2]
ok(cat == "Shouts", f"decide() files Stormcrown under Shouts: {cat} ({str(why)[:160]})")

# 3
few = mod("A Few Shouts", {"SHOU": 3, "WOOP": 9, "SPEL": 9, "MGEF": 9})
rv3 = mm._records_vote(few)
ok(rv3 is not None and rv3[0] == "Shouts" and "new shout/word records" in rv3[2] and "overhaul" not in rv3[2],
   f"three new shouts keep the plain shout vote: {rv3}")

# 4
spells = mod("A Spell Pack", {"SPEL": 120, "MGEF": 140, "SHOU*": 2})
rv4 = mm._records_vote(spells)
ok(rv4 is not None and rv4[0] == "Magic - Spells & Enchantments", f"a spell pack touching two shouts stays Magic: {rv4}")

# 5
place = mod("A Ruin Overhaul", {"STAT": 40, "CELL~": 5000})
votes5 = [("scope", "Location Overhauls - General", 3.0, "location overhaul: 300 of 400 references at X"),
          ("scope", "Location Overhauls - General", 2.4, "edits 7 exterior cells")]
res5 = mm.decide(place, votes5)
w5 = sum(v[2] for v in res5[2] if v[1] == "Location Overhauls - General")
ok(abs(w5 - 5.4) < 1e-6, f"a place mod's cells keep their full weight: {w5:.2f} ({res5[0]})")

print("ALL PASS" if not bad else f"{bad} FAILED")
sys.exit(1 if bad else 0)
