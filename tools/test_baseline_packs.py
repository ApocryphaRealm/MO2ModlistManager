"""R39, the baseline mesh and texture packs load near the start (2026-10-26).

The owner: "HPP and SMIM are baseline texture and mesh fixers, which should be low in the load order and overwritten by
most things." Until 1.1.6 their block (Mesh Improvements) opened the world tier, so every tier 0-2 mod sat below it:
SMIM beat Load Screen Shading Fix and Skyrim Landscape and Water Fixes, and High Poly Project beat SD's Horn Candles
(filed under Face) on the three horn candle meshes. R39 moves the block into tier 0, right after Unofficial Patches.
Patches made for a baseline pack still count it as a target (Markarth Fixed AF - UMF - SMIM QA [Patch] stays in
Patches), although tier 0-1 mods are otherwise nobody's target.

No instance is read.

Checks:
  1 Mesh Improvements is a tier 0 block, directly after Unofficial Patches;
  2 it comes before every other tier 0 block that ships art (Mesh and Texture Fixes, Bug Fixes) and before every
    character, world and content block, so those mods win its files;
  3 the world tier still starts with Presets - ENB and ReShade and keeps its own order;
  4 the baseline pack names stay in the block (BASELINE_ART: SMIM and its addons, High Poly Project, Cleaned Skyrim SE
    Textures) and a pack's add-on or a mod that merely mentions SMIM does not ("2K SMIM Whiterun Bench");
  5 a baseline pack is still a patch's target; Frameworks and User Interface are not.

    py -3 tools/test_baseline_packs.py [--plugin <MO2ModlistManager.py>]     exit 0 = ALL PASS
--plugin runs the same checks against another copy (git show 1db092d:MO2ModlistManager.py > old.py, 1.1.6 before R39:
checks 1, 2, 3 and 5 fail there).
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


pos, _headers = mm.category_order()
P = lambda c: pos.get(mm.norm(c), (99, 99))
mi = P("Mesh Improvements")

# 1
ok(mm.tier_of("Mesh Improvements") == 0 and mi == (P("Unofficial Patches")[0], P("Unofficial Patches")[1] + 1),
   f"Mesh Improvements is tier 0, right after Unofficial Patches: {mi} (Unofficial Patches {P('Unofficial Patches')})")

# 2
later = ["Essential Engine Fixes", "Bug Fixes", "Mesh and Texture Fixes", "User Interface", "Body", "Face",
         "Environment - Architecture", "Models and Textures - Clutter", "Collision", "PBR Textures", "Lighting",
         "Weapons", "Patches", "Generated Outputs"]
early = [c for c in later if P(c) <= mi]
ok(not early and P("Base Game") < mi, f"every fix, character, world and content block comes after it: {early or 'all after'}")

# 3
ok(P("Presets - ENB and ReShade") == (3, 0) and P("Presets - ENB and ReShade") < P("Environment - Weather") < P("Buildings"),
   f"the world tier opens with Presets - ENB and ReShade: {P('Presets - ENB and ReShade')}")

# 4
inside = ["Static Mesh Improvement Mod", "Static Mesh Improvement Mod Improvement Mod",
          "Static Mesh Improvement Mod - Complex Parallax Addon", "Static Mesh improvement Mod - SMIM - Quality Addon",
          "High Poly Project", "Cleaned Skyrim SE Textures"]
outside = ["2K SMIM Whiterun Bench", "High Poly Project - My fixes SE by Xtudo - Campfire Winterhold Restored [Patch]",
           "High Poly Solstheim Mushroom Trees"]
ok(all(mm.BASELINE_ART.search(n) for n in inside) and not any(mm.BASELINE_ART.search(n) for n in outside),
   "BASELINE_ART names the whole-game packs and only them")

# 5
eng = getattr(mm, "_engine_tier", None)
ok(eng is not None and not eng("Mesh Improvements") and eng("Frameworks") and eng("User Interface") and not eng("Face"),
   "a baseline pack is still a patch's target; tier 0-1 frameworks and UI are not")

print("ALL PASS" if not bad else f"{bad} FAILED")
sys.exit(1 if bad else 0)
