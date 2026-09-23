"""MO2 Modlist Manager - a Mod Organizer 2 plugin that generates the order of the left pane and the right.

The owner, 2026-09-22: "a new plugin for mo2 that generates separators and their names and puts all the mods in the
right order and separator", after the tier-and-guess sorter on Nexus scattered a hand-built pane.

What it does, and only from evidence a mod carries:
  * every mod's Nexus category is read from Nexus (v2 GraphQL, twenty mods a request, no key needed, cached);
    a mod with no Nexus id is placed by what it IS - a generated output, a test build, a base-game folder, or what
    it ships - or left under "Uncategorised", never guessed from words in its name; an "unpublished " build of the
    owner's sits in its proper category like any other mod (his placement rule);
  * separators are generated: one group header per group of categories, one separator per category, in a fixed
    load-order sequence (engine and fixes first, patches and outputs last);
  * inside a separator the current order is kept, except where a plugin's MASTER (read from the TES4 header) lives
    below it - then the dependent mod moves under its master, and the move is listed;
  * the plugin list follows the pane: plugins in mod order, masters first where the header says so, written to
    plugins.txt / loadorder.txt; before/after/first/last rules for plugins and for mods are the generator's own
    (profiles/<profile>/modlist_order_rules.json), nothing here depends on another plugin;
  * nothing is written until Apply: the dialog lists every separator created and retired and every mod that
    changes separator or order, and backs up the profile's lists and the retired separators first.

Copyright (C) 2026 ApocryphaRealm. GPL-3.0-or-later - see LICENSE and NOTICE.md.
"""
__version__ = "1.0.0"

import configparser
import json
import os
import re
import shutil
import struct
import time
import urllib.error
import urllib.request

# --- the taxonomy: group header -> the Nexus category names under it, in load order ----------------------------------
OTHER_GROUP_HEADER = "--- OTHER ---"   # a category the table does not know sits here, under its own name
GROUPS = [
    # "Uncategorised" sits FIRST on purpose: a mod nothing can place is put where the edges pull it - it is displaced
    # down to wherever its override winners are and relabelled there - whereas a late "unknown" group would drag every
    # mod that wins over an unknown one down to the tail (2026-09-22: 331 mods followed one unplaced patch).
    ("--- CORE ---", ["Base Game", "Uncategorised", "Utilities", "Bug Fixes", "Modders Resources", "Save Games", "VR"]),
    ("--- USER INTERFACE ---", ["User Interface"]),
    ("--- AUDIO ---", ["Audio"]),
    ("--- VISUALS ---", ["Models and Textures", "Visuals and Graphics", "Environmental", "Presets - ENB and ReShade"]),
    ("--- CHARACTER ---", ["Body, Face, and Hair", "Races, Classes, and Birthsigns", "Animation"]),
    ("--- NPCS & CREATURES ---", ["NPC", "Followers & Companions", "Followers & Companions - Creatures", "Creatures and Mounts"]),
    ("--- GAMEPLAY ---", ["Gameplay", "Overhauls", "Immersion", "Combat", "Stealth", "Skills and Leveling", "Magic - Gameplay",
                          "Magic - Spells & Enchantments", "Shouts", "Alchemy", "Crafting", "Guilds/Factions", "Cheats and God items"]),
    ("--- ITEMS & EQUIPMENT ---", ["Weapons and Armour", "Armour", "Armour - Shields", "Weapons", "Clothing and Accessories",
                                   "Items and Objects - Player", "Items and Objects - World", "Collectables, Treasure Hunts, and Puzzles"]),
    ("--- WORLD & CONTENT ---", ["Cities, Towns, Villages, and Hamlets", "Buildings", "Player homes", "Dungeons", "Locations - New",
                                 "Locations - Vanilla", "Quests and Adventures", "Miscellaneous"]),
    (OTHER_GROUP_HEADER, []),                 # categories the table does not know (the owner's own MO2 categories)
    ("--- PATCHES ---", ["Patches"]),
    ("--- OUTPUTS ---", ["Generated Outputs"]),
    ("--- LOCAL ---", ["Test Builds"]),
]
NODELETE_SEP = "[NoDelete]"            # kept as the last separator with its contents untouched (Wabbajack's convention)
TAG_NODELETE = re.compile(r"^\s*\[nodelete\]", re.I)
TAG_PATCH = re.compile(r"^\s*\[patch\]", re.I)
BASE_MASTERS = {"skyrim.esm", "update.esm", "dawnguard.esm", "hearthfires.esm", "dragonborn.esm"}
PLUGIN_EXT = (".esp", ".esm", ".esl")
OUTPUT_TOOLS = re.compile(r"\b(dyndolod|texgen|xlodgen|occlusion|pgpatcher|parallaxgen|nemesis|pandora|synthesis|bodyslide)\b.*\boutput\b"
                          r"|\bsynthesis\.esp\b|\bbashed patch\b|\bsmashed patch\b", re.I)
# THE SIX-TIER INDEX (Auto Sort's override hierarchy, kept; measured against a 2,300-mod tested list it agrees on
# 77% of cross-tier file conflicts and its misses are Nexus labels, not the hierarchy). A tier is assigned from the
# Nexus category, or from what a mod ships when Nexus cannot place it - never from words in its name.
#   0 engine, fixes, frameworks   1 interface   2 bodies, skeletons, animation   3 world, textures, systems
#   4 items, places, people       5 patches     6 generated outputs (and test builds)
TIERS = {
    0: ("Base Game", "Utilities", "Bug Fixes", "Modders Resources", "VR", "Uncategorised"),
    1: ("User Interface", "Save Games"),
    2: ("Body, Face, and Hair", "Animation", "Races, Classes, and Birthsigns"),
    3: ("Models and Textures", "Visuals and Graphics", "Environmental", "Audio", "Overhauls", "Gameplay", "Immersion",
        "Skills and Leveling", "Magic - Gameplay", "Combat", "Stealth", "Guilds/Factions", "Alchemy", "Miscellaneous",
        "Presets - ENB and ReShade"),
    4: ("Armour", "Armour - Shields", "Weapons", "Weapons and Armour", "Clothing and Accessories", "Items and Objects - Player",
        "Items and Objects - World", "Creatures and Mounts", "NPC", "Followers & Companions", "Followers & Companions - Creatures",
        "Quests and Adventures", "Collectables, Treasure Hunts, and Puzzles", "Player homes", "Buildings",
        "Cities, Towns, Villages, and Hamlets", "Dungeons", "Locations - New", "Locations - Vanilla",
        "Magic - Spells & Enchantments", "Crafting", "Shouts", "Cheats and God items"),
    5: ("Patches",),
    6: ("Test Builds",),
    7: ("Generated Outputs",),
}
TIER_HEADERS = {0: "--- 0 ENGINE, FIXES & FRAMEWORKS ---", 1: "--- 1 INTERFACE ---", 2: "--- 2 BODIES & ANIMATION ---",
                3: "--- 3 WORLD, TEXTURES & SYSTEMS ---", 4: "--- 4 ITEMS, PLACES & PEOPLE ---", 5: "--- 5 PATCHES ---",
                6: "--- 6 TEST BUILDS ---", 7: "--- 7 GENERATED OUTPUTS ---"}
# blocks that stand on their own: never merged into a neighbour, never take a neighbour's mods (the owner, 2026-09-22:
# the outputs had been folded into Test Builds, and Test Builds must hold every "test "-prefixed mod and nothing else)
FIXED_BLOCKS = ("base game", "test builds", "generated outputs", "[nodelete]")
INDEX_TIER = {norm_key: t for t, names in TIERS.items() for norm_key in (re.sub(r"\s+", " ", n).strip().lower() for n in names)}


def index_tier(category, mod=None):
    """The six-tier index of a category; an unknown category is tier 3 (the middle) and says so in the report.

    With the mod given, one evidence-based refinement: a mod filed under a tier-4 CONTENT category (Buildings, Cities,
    Armour, ...) that ships no plugin and only meshes/textures cannot add anything - it is a replacer, tier 3. On a
    tested list 84 of the 218 index-vs-list disagreements were exactly this (farmhouse and city mesh replacers filed
    under Buildings, which SMIM and the PBR packs then override)."""
    k = re.sub(r"\s+", " ", category or "").strip().lower()
    if k == NODELETE_SEP.lower():
        return 8
    t = INDEX_TIER.get(k, 3)
    if t == 4 and mod is not None and not mod.plugins and mod.files:
        exts = {os.path.splitext(f)[1] for f in mod.files}
        if exts <= {".nif", ".dds", ".tri", ".hkx", ".bsa", ".txt", ".ini", ".json"} and exts & {".nif", ".dds"}:
            return 3
    return t


GRAPHQL = "https://api.nexusmods.com/v2/graphql"
BATCH = 20
GAME_IDS = {"skyrimspecialedition": 1704, "skyrim": 110, "fallout4": 1151, "starfield": 4187, "oblivion": 101, "falloutnv": 130}


def norm(cat):
    """Nexus spells 'Locations -  New' with two spaces; match on collapsed whitespace, lower case."""
    return re.sub(r"\s+", " ", cat or "").strip().lower()


def folder_safe(display):
    """A separator is a folder: no slash, backslash, colon, star, question mark, quote, angle bracket or pipe in its name (Nexus has 'Guilds/Factions')."""
    out = re.sub(r"\s*/\s*", " and ", display)
    return out.translate(str.maketrans({c: "-" for c in '\\:*?"<>|'}))


def sep_name(display):
    return folder_safe(display) + "_separator"


def is_sep(name):
    return name.endswith("_separator")


def category_order():
    """{category name: (group index, index in group)} and the group header names in order."""
    order, headers = {}, []
    for gi, (header, cats) in enumerate(GROUPS):
        headers.append(header)
        for ci, c in enumerate(cats):
            order[norm(c)] = (gi, ci)
    return order, headers


TIER_NAMES = {gi: h.strip("- ").title() for gi, (h, _c) in enumerate(GROUPS)}


def tier_of(category):
    """The override tier of a category = its group's index (Auto Sort's tier idea, decided by the category)."""
    order, headers = category_order()
    k = norm(category)
    if k == NODELETE_SEP.lower():
        return len(GROUPS) + 1
    return order[k][0] if k in order else headers.index(OTHER_GROUP_HEADER)


# --- evidence ---------------------------------------------------------------------------------------------------------
def read_header(path):
    """(masters, description, is_esm) from a plugin's TES4 header. ([], "", False) when unreadable."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
            if len(head) < 24 or head[:4] != b"TES4":
                return [], "", False
            size = struct.unpack("<I", head[4:8])[0]
            flags = struct.unpack("<I", head[8:12])[0]
            data = fh.read(min(size, 4 * 1024 * 1024))
    except OSError:
        return [], "", False
    masters, description, pos = [], "", 0
    while pos + 6 <= len(data):
        sig = data[pos:pos + 4]
        sub = struct.unpack("<H", data[pos + 4:pos + 6])[0]
        pos += 6
        if sig == b"XXXX" and sub == 4:
            real = struct.unpack("<I", data[pos:pos + 4])[0]
            pos += 4
            if pos + 6 > len(data):
                break
            sig = data[pos:pos + 4]
            pos += 6
            sub = real
        payload = data[pos:pos + sub]
        pos += sub
        if sig == b"MAST":
            masters.append(payload.split(b"\x00", 1)[0].decode("cp1252", "replace"))
        elif sig == b"SNAM":
            description = payload.split(b"\x00", 1)[0].decode("cp1252", "replace")
    return masters, description, bool(flags & 1)


def read_meta(mod_dir):
    """(nexus mod id or 0, MO2 category ids) from meta.ini."""
    p = os.path.join(mod_dir, "meta.ini")
    cp = configparser.RawConfigParser(strict=False)
    try:
        cp.read(p, encoding="utf-8")
        modid = int(str(cp.get("General", "modid", fallback="0")).strip('" ') or 0)
        cats = [c for c in str(cp.get("General", "category", fallback="")).strip('" ').split(",") if c and c not in ("0", "-1")]
    except (configparser.Error, ValueError):
        modid, cats = 0, []
    return modid, cats


ASSET_EXTS = (".dds", ".nif", ".hkx", ".dll", ".esl", ".esp", ".esm", ".bsa", ".pex", ".seq", ".ini", ".json", ".swf",
              ".wav", ".xwm", ".fuz", ".tri", ".txt")
IGNORED_FILES = {"meta.ini", "readme.txt", "read me.txt", "changelog.txt", "changes.txt", "license.txt", "licence.txt",
                 "credits.txt", "desktop.ini", "thumbs.db"}


class Mod:
    __slots__ = ("name", "enabled", "index", "nexus_id", "mo2_cats", "plugins", "optional", "category", "why", "group", "flags", "files")

    def __init__(self, name, enabled, index):
        self.name, self.enabled, self.index = name, enabled, index
        self.nexus_id, self.mo2_cats, self.plugins = 0, [], []      # plugins: [(file, [masters], is_esm)]
        self.optional = []                                          # the same, for the mod's optional folder (MO2's Optional ESPs)
        self.category, self.why, self.group, self.flags, self.files = None, "", None, set(), []

    @property
    def tier(self):
        return tier_of(self.category) if self.category else None


def scan_files(mod_dir):
    """Relative asset paths, lower-cased, forward slashes - what can collide in the virtual file system."""
    out = []
    root_len = len(mod_dir.rstrip("\\/")) + 1
    for dirpath, dirnames, filenames in os.walk(mod_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            low = f.lower()
            if low.endswith(ASSET_EXTS) and low not in IGNORED_FILES:
                out.append(os.path.join(dirpath, f)[root_len:].replace("\\", "/").lower())
    return out


def read_modlist(path):
    """[(name, enabled)] top of the pane first (the file is stored bottom-first), plus the header comment lines."""
    text = open(path, "rb").read().decode("utf-8-sig")
    lines = text.replace("\r\n", "\n").split("\n")
    header = [l for l in lines if l.startswith("#")]
    rows = [(l[1:], l[0] == "+") for l in lines if l[:1] in ("+", "-")]
    rows.reverse()
    return rows, header


def write_modlist(path, rows, header):
    """rows top-first -> file bottom-first, CRLF, like MO2 writes it."""
    body = [("+" if en else "-") + nm for nm, en in reversed(rows)]
    open(path, "wb").write(("\r\n".join(header + body) + "\r\n").encode("utf-8"))


def scan(mods_dir, rows, progress=None):
    mods = []
    for i, (name, enabled) in enumerate(rows):
        m = Mod(name, enabled, i)
        mods.append(m)
        if is_sep(name):
            continue
        d = os.path.join(mods_dir, name)
        if not os.path.isdir(d):
            m.flags.add("missing")
            continue
        m.nexus_id, m.mo2_cats = read_meta(d)
        try:
            for f in os.listdir(d):
                if f.lower().endswith(PLUGIN_EXT) and os.path.isfile(os.path.join(d, f)):
                    masters, _desc, esm = read_header(os.path.join(d, f))
                    # a .esl-EXTENSION file loads in the master block whatever its header says, as does a .esm
                    m.plugins.append((f, masters, esm or f.lower().endswith((".esm", ".esl"))))
            opt = os.path.join(d, "optional")
            if os.path.isdir(opt):
                for f in os.listdir(opt):
                    if f.lower().endswith(PLUGIN_EXT) and os.path.isfile(os.path.join(opt, f)):
                        masters, _desc, esm = read_header(os.path.join(opt, f))
                        m.optional.append((f, masters, esm or f.lower().endswith((".esm", ".esl"))))
            if enabled:
                m.files = scan_files(d)
        except OSError:
            pass
        if progress and not progress(i, len(rows), name):
            break
    return mods


# --- Nexus categories, twenty a request, cached --------------------------------------------------------------------------
def fetch_categories(mod_ids, cache_path, domain="skyrimspecialedition", progress=None, log=None):
    cache = {}
    if os.path.isfile(cache_path):
        try:
            cache = json.load(open(cache_path, encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    game = GAME_IDS.get(domain, 1704)
    todo = [i for i in sorted(set(mod_ids)) if i and str(i) not in cache]
    queue = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    done, failures = 0, 0
    while queue and failures < 3:
        chunk = queue.pop(0)
        query = "{ " + " ".join(f"m{i}: mod(modId: {i}, gameId: {game}) {{ modCategory {{ name }} }}" for i in chunk) + " }"
        try:
            req = urllib.request.Request(GRAPHQL, data=json.dumps({"query": query}).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "User-Agent": "MO2ModlistManager/" + __version__})
            with urllib.request.urlopen(req, timeout=30) as fh:
                reply = json.loads(fh.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            failures += 1
            if log:
                log(f"nexus: batch failed ({exc}); {failures} in a row")
            continue
        data = reply.get("data") or {}
        if reply.get("errors") and not data and len(chunk) > 1:     # one dead id can sink a batch: split it
            half = len(chunk) // 2
            queue[:0] = [chunk[:half], chunk[half:]]
            continue
        failures = 0
        for i in chunk:
            node = data.get(f"m{i}") or {}
            cat = ((node.get("modCategory") or {}).get("name")) if node else None
            cache[str(i)] = cat or ""          # "" = asked, Nexus has nothing (hidden, removed, off-site)
        done += len(chunk)
        if progress and not progress(done, len(todo), "nexus"):
            break
        time.sleep(0.2)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), indent=0)
    return cache, len(todo), done


# --- placing every mod ----------------------------------------------------------------------------------------------------
def place(mods, categories, mo2_category_names=None, under_nodelete=(), pins=None):
    """Set .category / .why on every mod. Returns nothing; every decision is a fact the dialog can show."""
    order, _headers = category_order()
    pins = pins or {}
    for m in mods:
        if is_sep(m.name):
            continue
        n = m.name
        if n in pins:
            m.category, m.why = pins[n], "pinned by a rule"
            continue
        if TAG_NODELETE.match(n):
            m.category, m.why = NODELETE_SEP, "carries the [NoDelete] tag - stays in the NoDelete block"
            continue
        low = n.lower()
        if low.startswith("test "):
            m.category, m.why = "Test Builds", "name starts with 'test '"
            continue
        if m.plugins and all(f.lower() in BASE_MASTERS or f.lower().startswith("cc") for f, _, _ in m.plugins) and not m.nexus_id:
            m.category, m.why = "Base Game", "every plugin is a base-game or Creation Club file"
            continue
        if not m.nexus_id and OUTPUT_TOOLS.search(n):
            m.category, m.why = "Generated Outputs", "no Nexus page and a tool's output name"
            continue
        cat = categories.get(str(m.nexus_id), "") if m.nexus_id else ""
        if cat:
            m.category, m.why = cat, f"Nexus category of mod {m.nexus_id}"
            continue
        # the [Patch] prefix only places a mod Nexus could not: USSEP is tagged [Patch] by name yet is "Bug Fixes" on
        # Nexus and a master to dozens of mods - filing it under Patches dragged them all below it
        if TAG_PATCH.match(n):
            m.category, m.why = "Patches", "[Patch] prefix (MO2 Patch Tagger), no Nexus category"
            continue
        if m.mo2_cats and mo2_category_names:
            for c in m.mo2_cats:
                name = mo2_category_names.get(c)
                if not name or norm(name) == "unpublished":      # "unpublished" is a state, not a place (the owner's rule)
                    continue
                if norm(name) == "test":
                    m.category, m.why = "Test Builds", "MO2 category 'test'"
                else:
                    m.category, m.why = name, f"MO2 category '{name}'"
                break
            if m.category:
                continue
        cat, why = class_from_files(m)
        if cat:
            m.category, m.why = cat, why
            continue
        m.category, m.why = "Uncategorised", ("no Nexus page" if not m.nexus_id else f"Nexus has no category for mod {m.nexus_id}")
    for m in mods:
        if m.category:
            m.group = tier_of(m.category)


def class_from_files(m):
    """(category, why) from what a mod ships, for a mod Nexus cannot place. Ordered by how much a hit proves: a DLL is
    an SKSE plugin whatever else is in the folder; a texture only says 'art'. ("", "") when nothing decisive."""
    files = m.files or []
    if not files:
        return "", ""
    exts = {os.path.splitext(f)[1] for f in files}
    tops = {f.split("/", 1)[0] for f in files if "/" in f}
    if ".dll" in exts:
        return "Utilities", "ships a DLL (SKSE plugin)"
    if "interface" in tops or ".swf" in exts:
        return "User Interface", "ships interface files"
    if ".hkx" in exts:
        return "Animation", "ships animations / behaviours"
    if exts & {".wav", ".xwm", ".fuz"} and not exts & {".dds", ".nif"}:
        return "Audio", "ships sound files"
    if exts & {".dds", ".nif"}:
        return "Models and Textures", "ships meshes or textures"
    if ".pex" in exts:
        return "Utilities", "ships scripts and nothing visual"
    return "", ""


def read_nexus_catmap(instance_dir):
    """{nexus category name (normalised): MO2 category id} from nexuscatmap.dat (mo2 id | name | nexus id) -
    the table MO2 fills when categories are imported from Nexus. Rows with MO2 id -1 are unmapped."""
    out = {}
    p = os.path.join(instance_dir, "nexuscatmap.dat")
    try:
        for line in open(p, encoding="utf-8", errors="ignore"):
            parts = line.rstrip("\n").split("|")
            if len(parts) >= 3 and parts[0].lstrip("-").isdigit() and int(parts[0]) > 0:
                out[norm(parts[1])] = int(parts[0])
    except OSError:
        pass
    return out


def plan_mo2_category_updates(mods, categories, instance_dir):
    """[(mod name, meta.ini path, MO2 category id, Nexus category name)] for every mod that has a Nexus page whose
    category Nexus reports, and no MO2 category of its own. MO2's own "import categories from Nexus" only fills the
    mapping table; a mod is categorised only when MO2 queries it, which 1,960 of the owner's 2,110 never were."""
    catmap = read_nexus_catmap(instance_dir)
    mods_dir = os.path.join(instance_dir, "mods")
    out = []
    for m in mods:
        if is_sep(m.name) or not m.nexus_id or m.mo2_cats:
            continue
        cat = categories.get(str(m.nexus_id), "")
        mo2_id = catmap.get(norm(cat)) if cat else None
        if mo2_id:
            out.append((m.name, os.path.join(mods_dir, m.name, "meta.ini"), mo2_id, cat))
    return out


def apply_mo2_category_updates(updates, log=None):
    """Write category="<id>," into each meta.ini (the form MO2 writes), keeping every other line as it is."""
    done = 0
    for name, path, mo2_id, cat in updates:
        try:
            text = open(path, "rb").read().decode("utf-8-sig")
            nl = "\r\n" if "\r\n" in text else "\n"
            lines = text.split(nl)
            new = 'category="{0},"'.format(mo2_id)
            replaced = False
            for i, line in enumerate(lines):
                if line.startswith("category="):
                    lines[i] = new
                    replaced = True
                    break
            if not replaced:
                for i, line in enumerate(lines):
                    if line.strip() == "[General]":
                        lines.insert(i + 1, new)
                        replaced = True
                        break
            if not replaced:
                lines.insert(0, "[General]")
                lines.insert(1, new)
            open(path, "wb").write(nl.join(lines).encode("utf-8"))
            done += 1
        except OSError as exc:
            if log:
                log(f"category update failed for {name}: {exc}")
    if log:
        log(f"MO2 categories written for {done} of {len(updates)} mod(s)")
    return done


def read_mo2_categories(instance_dir):
    names = {}
    p = os.path.join(instance_dir, "categories.dat")
    try:
        for line in open(p, encoding="utf-8", errors="ignore"):
            parts = line.rstrip("\n").split("|")
            if len(parts) >= 2 and parts[0].isdigit():
                names[parts[0]] = parts[1]
    except OSError:
        pass
    return names


def build(mods, rules=None, keep_winners=True, mode="index", min_run=8):
    """The new pane: [(name, enabled)] top-first, plus the facts.

    The order is a topological sort (Kahn, with a heap): every edge is a fact - a MASTER must load above its
    dependent, and with keep_winners today's winner of every shared file stays below its loser - and the tie-break is
    the taxonomy (group, category, then today's position), so mods fall into their category's block unless an edge
    holds them lower. A mod held below its group is DISPLACED: it is relabelled to the category it lands in, with the
    reason, so the separators stay whole and the dialog says why. The owner's rules (after/before/first/last) are
    edges and pins on top of that. Without keep_winners the flips are only reported.

    mode "spine" (the default for a list that has been played): today's order is the tie-break for EVERY mod, so the
    sort changes only what a master, a winner or a rule demands, and the separators are generated over that order -
    a run of one category becomes its separator, and a run shorter than min_run inside a longer run of another
    category is absorbed into it (listed as "absorbed"). No block is imposed, so nothing is displaced.
    mode "blocks": the category blocks are imposed in the list's own tier order and today's winners are kept by
    displacing mods below their block (listed as "displaced"). On the owner's list this moved ~500 mods."""
    import heapq
    order, headers = category_order()
    other = headers.index(OTHER_GROUP_HEADER)
    rules = rules or []
    real = [m for m in mods if not is_sep(m.name) and "missing" not in m.flags]
    by_name = {m.name: m for m in real}

    def taxonomy_rank(cat):
        k = norm(cat)
        if k == NODELETE_SEP.lower():
            return (len(GROUPS) + 1, 0)
        return order.get(k, (other, 0))

    cat_rank = {}          # filled by learn_order() once the edges are known; taxonomy order until then

    def rank(m):
        k = norm(m.category)
        if mode == "spine":
            if k == NODELETE_SEP.lower():
                return (1, 0, m.index)              # NoDelete stays the tail
            return (0, 0, m.index)
        if mode == "index":
            # tier, then the category's place in that tier's own list, then today's position. Until 2026-09-23 the
            # order inside a tier was today's position alone, and the blocks were labels stamped over runs of it -
            # 496 of 2,191 mods sat in a block of another category (the owner: "many mods seem out of place").
            # Now every category is one block; the tested same-tier override winners are kept by the keep-winners
            # edges below, which pull a winner down under its loser and relabel it there (the 'displaced' list).
            t = index_tier(m.category, m)
            names = TIERS.get(t, ())
            k = norm(m.category)
            ci = next((i for i, n in enumerate(names) if norm(n) == k), len(names))
            return (t, ci, m.index)
        if k in cat_rank:
            return (cat_rank[k], 0, m.index)
        gi, ci = taxonomy_rank(m.category)
        return (gi * 1000 + ci, 0, m.index)

    # --- edges: x above y ----------------------------------------------------------------------------------------
    above = {}                     # above[y] = {x}
    reason = {}                    # (x, y) -> why
    def edge(x, y, why):
        if x is y or x.category == NODELETE_SEP or y.category == NODELETE_SEP:
            return
        above.setdefault(y.name, set()).add(x.name)
        reason.setdefault((x.name, y.name), why)
    # the owner of a plugin is the mod MO2 actually takes it from: the LOWEST enabled mod that ships it (a patch
    # collection re-shipping a main plugin, "Cleaned Plugin" variants); anchoring to the upper copy put the child's
    # edge on a mod whose file never loads (2026-09-22 audit: 25 plugins out of pane order for this reason)
    owner = {}
    for m in real:
        for f, _masters, _esm in m.plugins:
            k = f.lower()
            if m.enabled or k not in owner:
                owner[k] = m
    fixes = []
    for m in real:
        for f, masters, _esm in m.plugins:
            for mast in masters:
                o = owner.get(mast.lower())
                if o and o is not m:
                    edge(o, m, f"{f} needs its master {mast}")
                    if o.index > m.index:
                        fixes.append((m.name, o.name))
    if mode == "index":
        outputs = [m for m in real if norm(m.category) == norm("Generated Outputs")]
        for o in outputs:
            for m in real:
                if m is not o and m.enabled and norm(m.category) not in (norm("Generated Outputs"), norm("Test Builds"), NODELETE_SEP.lower()):
                    edge(m, o, "generated output loads last")
    def would_cycle(x, y):
        """True when y is already (transitively) above x, so 'x above y' would close a loop. Rules are the only edges
        that can be inconsistent with the structural ones (masters, outputs last, settings loaders, kept winners), so
        each rule is checked against everything before it and skipped - and reported - rather than obeyed: 527
        review rules written under an old order made 9 cycles that froze the pane (2026-09-23)."""
        stack, seen = [x], set()
        while stack:
            n = stack.pop()
            if n == y:
                return True
            if n in seen:
                continue
            seen.add(n)
            stack.extend(above.get(n, ()))
        return False

    owners = {}
    for m in real:
        if m.enabled:
            for f in m.files:
                owners.setdefault(f, []).append(m)
    # SETTINGS LOADERS (the owner, 2026-09-23: "the settings loaders are higher than their target mod"). A loader
    # ships MCM\Config\<mod>\settings.ini beside the mod's own MCM script and translations; it only does its job
    # when it WINS those files, so it sits below every enabled mod it shares a file with - whatever the tiers say
    # (its Nexus category is usually User Interface, tier 1, which had put it above a tier-3 target). The
    # displacement pass then lists it under the target's block.
    loader_re = re.compile(r"(^|/)mcm/config/[^/]+/settings\.ini$")
    loader_only_re = re.compile(r"^(mcm/config/|interface/translations/|scripts/)")
    name_re = re.compile(r"settings loader", re.I)

    def is_settings_loader(m):
        # by name, or by shape: nothing but MCM config, translations and the MCM script, with a settings.ini. A mod
        # that ships its OWN MCM/Config/<mod>/settings.ini beside meshes or a DLL (True Directional Movement, TrueHUD,
        # Photo Mode) is not a loader - reading it as one put it under Norden UI and made a cycle (2026-09-23)
        if name_re.search(m.name):
            return True
        return any(loader_re.search(f) for f in m.files) and all(loader_only_re.search(f) for f in m.files)
    loaders = 0
    loader_pairs = set()          # (loader, target): the loader rule decides these pairs, not today's winner
    for a_mod in real:
        if not a_mod.enabled or not a_mod.files:
            continue
        if not is_settings_loader(a_mod):
            continue
        shared = {}
        for f in a_mod.files:
            for b_mod in owners.get(f, []):
                if b_mod is not a_mod and b_mod.enabled and not name_re.search(b_mod.name):
                    shared[b_mod.name] = shared.get(b_mod.name, 0) + 1
        for b_name, n in shared.items():
            edge(by_name[b_name], a_mod, f"settings loader: must win {n} file(s) of {b_name}")
        # no shared file (the target ships its MCM under other names): the loader's own name says whose it is
        base = re.sub(r"\s*-\s*settings loader.*$", "", a_mod.name, flags=re.I).strip()
        # the target may carry a suffix of its own ("Farmhouse Chimneys SE (main)"): the shortest enabled mod named
        # base, "base (...)" or "base - ..." that is not itself a loader or a patch
        cands = [m for m in real if m.enabled and m is not a_mod and not name_re.search(m.name) and not TAG_PATCH.match(m.name)
                 and (norm(m.name) == norm(base) or m.name.lower().startswith(base.lower() + " (") or m.name.lower().startswith(base.lower() + " - "))]
        target = min(cands, key=lambda m: len(m.name)) if cands else None
        if target is not None and target.name not in shared:
            edge(target, a_mod, f"settings loader for {target.name} (by name)")
            shared[target.name] = 0
        loader_pairs.update((a_mod.name, b) for b in shared)
        if shared:
            loaders += 1
    pairs = {}
    for f, ms in owners.items():
        if len(ms) < 2 or len(ms) > 40:
            continue
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                a, b = ms[i], ms[j]
                k = (a.name, b.name) if a.name < b.name else (b.name, a.name)
                pairs[k] = pairs.get(k, 0) + 1
    winners = {}
    winners_yielded = []
    for (a, b), n in pairs.items():
        loser, winner = (a, b) if by_name[a].index < by_name[b].index else (b, a)
        winners[(loser, winner)] = n
        if (loser, winner) in loader_pairs or (winner, loser) in loader_pairs:
            continue                  # a settings loader's pair is settled by the loader rule above
        if keep_winners and (mode != "index" or index_tier(by_name[loser].category, by_name[loser]) == index_tier(by_name[winner].category, by_name[winner])):
            # in index mode only SAME-tier winners are kept: a cross-tier flip is the hierarchy doing its job.
            # A winner that would loop against a master or loader edge yields to it (JS Knapsacks won 36 files over
            # Wet and Cold today while its own patch plugin needs WetandCold.esp as a master - 2026-09-23)
            if would_cycle(loser, winner):
                winners_yielded.append((winner, loser, n, reason.get((winner, loser), "a master or loader edge says the opposite")))
                continue
            edge(by_name[loser], by_name[winner], f"keeps winning {n} shared file(s) over {loser}")
    rule_moves = []
    rules_ignored = []

    for r in rules:
        a, b, kind = by_name.get(r.get("mod", "")), by_name.get(r.get("target", "")), r.get("type", "")
        if a is None or not r.get("enabled", True):
            continue
        # a rule that says the opposite of a structural edge is ignored and reported, never obeyed: 527 review rules
        # written under the old order pinned settings loaders ABOVE their targets and mods after generated outputs,
        # and every one of them became a cycle that froze the pane (2026-09-23)
        if kind == "after" and b is not None:
            if would_cycle(b.name, a.name):
                rules_ignored.append((a.name, f"after {b.name}", reason.get((a.name, b.name), "would loop through other edges")))
                continue
            edge(b, a, f"rule: after {b.name}")
            rule_moves.append((a.name, f"after {b.name}"))
        elif kind == "before" and b is not None:
            if would_cycle(a.name, b.name):
                rules_ignored.append((a.name, f"before {b.name}", reason.get((b.name, a.name), "would loop through other edges")))
                continue
            edge(a, b, f"rule: before {b.name}")
            rule_moves.append((a.name, f"before {b.name}"))
    firsts = {r.get("mod") for r in rules if r.get("type") == "first" and r.get("enabled", True)}
    lasts = {r.get("mod") for r in rules if r.get("type") == "last" and r.get("enabled", True)}

    # --- the category order, learned from the winners ------------------------------------------------------------
    # Between two categories, count (in shared files) how often the list says "A above B" against "B above A".
    # Start from the taxonomy order and swap neighbours while a swap lowers the total weight of contradicted pairs:
    # the tier order the list itself has been tested with, with the table deciding only where the list is silent.
    cats = sorted({norm(m.category) for m in real}, key=lambda c: taxonomy_rank(c))
    weight = {}
    for (a, b), n in pairs.items():
        ma, mb = by_name[a], by_name[b]
        loser, winner = (ma, mb) if ma.index < mb.index else (mb, ma)
        ca, cb = norm(loser.category), norm(winner.category)
        if ca != cb and ca != NODELETE_SEP.lower() and cb != NODELETE_SEP.lower():
            weight[(ca, cb)] = weight.get((ca, cb), 0) + n       # ca must come before cb, n files say so
    def cost(seq):
        pos = {c: i for i, c in enumerate(seq)}
        return sum(n for (a, b), n in weight.items() if pos[a] > pos[b])
    # The list's own tier order: each category takes the MEDIAN of its members' positions today, so the order of
    # blocks is the order the tested list already uses (base game at the top, outputs at the bottom, meshes where
    # the list keeps them). A pure minimum-feedback-arc order over shared-file weights was tried and put
    # "Miscellaneous" first and "Base Game" thirty-eighth - a handful of big mesh packs outweighed everything.
    # Insertion sweeps on the shared-file weight were tried too and undid the shape (Utilities to the tail).
    import statistics
    members = {}
    for m in real:
        members.setdefault(norm(m.category), []).append(m.index)
    seq = sorted(cats, key=lambda c: (statistics.median(members[c]) if members.get(c) else 10**9, taxonomy_rank(c)))
    # the fixed ends stay fixed: base game first, outputs and test builds last, whatever the medians say
    for c, front in ((norm("Base Game"), True), (norm("Generated Outputs"), False), (norm("Test Builds"), False)):
        if c in seq:
            seq.remove(c)
            seq.insert(0, c) if front else seq.append(c)
    best = cost(seq)          # the weight the block order cannot satisfy: those pairs become displacements
    for i, c in enumerate(seq):
        cat_rank[c] = i
    learned = [(c, taxonomy_rank(c)) for c in seq]
    moved_cats = [c for i, (c, _t) in enumerate(learned) if i != sorted(range(len(learned)), key=lambda j: learned[j][1]).index(i)]

    # --- Kahn with a heap on the learned rank -----------------------------------------------------------------------
    def key(m):
        gi, ci, idx = rank(m)
        return (gi, ci, 0 if m.name in firsts else 2 if m.name in lasts else 1, idx)
    indeg = {m.name: 0 for m in real}
    children = {}
    for y, xs in above.items():
        for x in xs:
            if x in indeg and y in indeg:
                indeg[y] += 1
                children.setdefault(x, []).append(y)
    ready = [(key(m), m.name) for m in real if indeg[m.name] == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        _k, nm = heapq.heappop(ready)
        ordered.append(by_name[nm])
        for c in children.get(nm, ()):
            indeg[c] -= 1
            if indeg[c] == 0:
                heapq.heappush(ready, (key(by_name[c]), c))
    cycles = [m for m in real if m.name not in {x.name for x in ordered}]
    cycle_names = {m.name for m in cycles}
    cycle_edges = [(x, y, reason.get((x, y), "")) for y in cycle_names for x in above.get(y, ()) if x in cycle_names]
    ordered += sorted(cycles, key=key)          # a cycle among edges: those mods keep today's relative order

    # --- displaced mods take the category they land in (blocks mode) ------------------------------------------------
    displaced = []
    absorbed = []
    # displacement first, so the run merging below sees every mod's final category
    displaced = []
    cur = None
    for m in (ordered if mode in ("blocks", "index") else []):
        if m.category == NODELETE_SEP or norm(m.category) in FIXED_BLOCKS:
            continue
        gi = rank(m)[0]
        if cur is None:
            cur = m
            continue
        if gi < rank(cur)[0]:
            # held here by an edge: name the latest predecessor that holds it
            holders = [x for x in above.get(m.name, ()) if x in by_name]
            why = ""
            if holders:
                h = max(holders, key=lambda x: ordered.index(by_name[x]))
                why = reason.get((h, m.name), "")
            displaced.append((m.name, m.category, cur.category, why))
            m.category, m.why = cur.category, f"displaced under '{cur.category}': {why} ({m.why})"
        else:
            cur = m

    if mode in ("spine", "index"):
        # runs of one category over the kept order; the SHORTEST run is merged into the larger of its two neighbours
        # (whatever their category) until every run has at least min_run mods - so the separators stay few and each
        # absorbed mod is listed with the category it really has
        runs = []
        for m in ordered:
            if m.category == NODELETE_SEP:
                continue
            if runs and norm(runs[-1][0]) == norm(m.category):
                runs[-1][1].append(m)
            else:
                runs.append([m.category, [m]])
        # a run's tier is the tier its mods were ORDERED by (rank), not the tier of its label re-derived from its first
        # mod: an asset-only 'Weapons' mod ranks as tier 3 while the label says 4, and comparing labels left small
        # same-tier runs unmerged ('Armour' with 5 mods between two 'Weapons' runs)
        for m in real:
            m.group = rank(m)[0]

        def run_tier(r):
            # the tier most of the run's mods were ordered by - not its first mod, which is often one a master pulled
            # down from another tier (a tier-0 fix at the head of a tier-4 run stopped every merge beside it)
            from collections import Counter
            return Counter(m.group for m in r[1]).most_common(1)[0][0]

        # a category with at least min_run mods in its tier keeps its own block even when kept winners split it into
        # short runs - the owner, 2026-09-23: "pelt cloaks should be in clothing": all eight Clothing and Accessories
        # mods had been absorbed into Weapons blocks because no single run of them reached eight. Only a category
        # that is genuinely tiny in its tier is folded into a neighbour as a minority.
        cat_total = {}
        for r in runs:
            cat_total[norm(r[0])] = cat_total.get(norm(r[0]), 0) + len(r[1])
        largest = {}                       # (tier, category) -> the biggest run of it: the one that keeps its separator
        for r in runs:
            key_ = (run_tier(r), norm(r[0]))
            if key_ not in largest or len(r[1]) > len(largest[key_][1]):
                largest[key_] = r
        for key_, r in largest.items():
            if len(r) == 2 and norm(r[0]) not in FIXED_BLOCKS and cat_total.get(norm(r[0]), 0) >= min_run and len(r[1]) < min_run:
                r.append("keep")       # the category's home block; its splinters elsewhere are absorbed as minorities

        def same_tier(a, b):
            if a is None or b is None:
                return True
            if norm(a[0]) in FIXED_BLOCKS or norm(b[0]) in FIXED_BLOCKS:
                return False
            return mode != "index" or run_tier(a) == run_tier(b)
        while len(runs) > 1:
            i = min(range(len(runs)), key=lambda j: (10**6 if (len(runs[j]) > 2 or norm(runs[j][0]) in FIXED_BLOCKS) else len(runs[j][1]), j))
            if len(runs[i][1]) >= min_run or len(runs[i]) > 2 or norm(runs[i][0]) in FIXED_BLOCKS:
                break
            left = runs[i - 1] if i > 0 and same_tier(runs[i - 1], runs[i]) else None
            right = runs[i + 1] if i + 1 < len(runs) and same_tier(runs[i], runs[i + 1]) else None
            if left is None and right is None:
                # a short run alone in its tier keeps its own separator; mark it so the loop moves on
                runs[i].append("keep")
                if all(len(r[1]) >= min_run or len(r) > 2 for r in runs):
                    break
                continue
            into = left if (right is None or (left is not None and len(left[1]) >= len(right[1]))) else right
            if into is left:
                left[1].extend(runs[i][1])
            else:
                right[1][0:0] = runs[i][1]
            del runs[i]
            # merging can make two same-category runs adjacent: join them
            j = 0
            while j + 1 < len(runs):
                if norm(runs[j][0]) == norm(runs[j + 1][0]):
                    runs[j][1].extend(runs[j + 1][1])
                    del runs[j + 1]
                else:
                    j += 1
        # every block is named for the category MOST of its mods carry; the rest are listed as the minority they are
        from collections import Counter
        for run in runs:
            counts = Counter(m.category for m in run[1])
            label = counts.most_common(1)[0][0]
            run[0] = label
            tier = run_tier(run)
            for m in run[1]:
                # the whole run sits under one tier header: re-deriving the tier per mod from the block's label split a
                # 16-mod tier-3 'Weapons' run in two when a member with a plugin re-derived as tier 4 (2026-09-22)
                m.group = tier
                if norm(m.category) != norm(label):
                    absorbed.append((m.name, m.category, label))
                    m.category, m.why = label, f"in a '{label}' block; its own category is different ({m.why})"
    # --- separators (a group header is written whenever the group changes; the learned order may interleave) --------
    rows = []
    cur_header, cur_cat = None, None
    written_headers = set()
    block_uses = {}          # a category that heads more than one block gets a numbered name from its second block on
    for m in ordered:
        k = norm(m.category)
        if k == NODELETE_SEP.lower():
            header = None
        elif mode == "index":
            header = TIER_HEADERS[m.group if m.group in TIER_HEADERS else index_tier(m.category, m)]
        else:
            gi = order.get(k, (other, 0))[0]
            header = headers[gi]
        if header != cur_header and header is not None:
            if header not in written_headers:           # the learned order can interleave groups: one header each
                rows.append((sep_name(header), False))
                written_headers.add(header)
            cur_header = header
        if norm(m.category) != norm(cur_cat or ""):
            if k == NODELETE_SEP.lower():
                existing = [x.name for x in mods if is_sep(x.name) and re.sub(r"[\s\[\]\-_.]", "", x.name[:-len("_separator")]).lower() == "nodelete"]
                rows.append((existing[0] if existing else sep_name(NODELETE_SEP), False))
            else:
                # the same category can head several blocks (five 'Utilities' runs in tier 0, split by masters); a
                # repeated name is numbered - the owner, 2026-09-23: "there are duplicate plugin group names" - so every
                # block, and so every BPM group made from it, has a name of its own
                n = block_uses[norm(m.category)] = block_uses.get(norm(m.category), 0) + 1
                rows.append((sep_name(m.category if n == 1 else f"{m.category} ({n})"), False))
            cur_cat = m.category
        rows.append((m.name, m.enabled))
    for m in mods:
        if "missing" in m.flags:
            rows.append((m.name, m.enabled))
    old_nodelete = [m.name for m in mods if is_sep(m.name) and re.sub(r"[\s\[\]\-_.]", "", m.name[:-len("_separator")]).lower() == "nodelete"]
    if old_nodelete and not any(is_sep(nm) and nm == old_nodelete[0] for nm, _ in rows):
        rows.append((old_nodelete[0], False))       # the NoDelete home stays, empty, at the bottom
    new_pos = {nm: i for i, (nm, _) in enumerate(rows)}
    flips = []
    for (l, w), n in winners.items():
        if new_pos.get(w, 0) < new_pos.get(l, 0):
            tw, tl = index_tier(by_name[w].category, by_name[w]), index_tier(by_name[l].category, by_name[l])
            if tw != tl:
                kind = f"hierarchy: tier {tl} ({by_name[l].category}) over tier {tw} ({by_name[w].category})"
            else:
                kind = f"specificity: {len(by_name[l].files)} files over {len(by_name[w].files)}"
            flips.append((w, l, n, kind))
    flips.sort(key=lambda x: -x[2])
    # advice: same-tier pairs where the mod that ships MORE files wins - usually right (a broad pack under a
    # targeted one), sometimes wrong (a broad pack that must win), so it is shown, never applied
    advice = []
    for (l, w), n in winners.items():
        ml, mw = by_name[l], by_name[w]
        if index_tier(ml.category, ml) == index_tier(mw.category, mw) and len(mw.files) > len(ml.files) and mw.files and ml.files:
            advice.append((w, l, n, f"the larger mod ({len(mw.files)} files) wins over the smaller ({len(ml.files)}) - check it is meant to"))
    advice.sort(key=lambda x: -x[2])
    new_seps = {nm for nm, _ in rows if is_sep(nm)}
    old_seps = {m.name for m in mods if is_sep(m.name)}
    return rows, {"fixes": fixes, "rule_moves": rule_moves, "flips": flips, "conflict_pairs": len(pairs),
                  "displaced": displaced, "absorbed": absorbed, "advice": advice, "mode": mode, "cycles": [m.name for m in cycles], "cycle_edges": cycle_edges, "rules_ignored": rules_ignored, "winners_yielded": winners_yielded,
                  "category_order": seq, "category_moves": moved_cats, "contradicted_files": best,
                  "created": sorted(new_seps - old_seps), "retired": sorted(old_seps - new_seps)}


def plugin_order(rows, mods_by_name, ruler_user_rules=()):
    """Plugins in pane order (ESMs first among themselves), then a stable topological pass so every master loads
    before its dependents and the generator's own before/after/first/last plugin rules hold."""
    import heapq
    # a plugin shipped by two enabled mods is placed where its WINNING copy sits (the lower mod, the one MO2 loads),
    # and that copy's header decides whether it is a master-block plugin (SGEyebrows.esp: flagged in one mod only)
    winning, masters_of = {}, {}
    for pos, (nm, en) in enumerate(rows):
        m = mods_by_name.get(nm)
        if not m or not en:
            continue
        for f, masters, is_esm in m.plugins:
            winning[f.lower()] = (pos, f, is_esm)
            masters_of[f.lower()] = [x.lower() for x in masters]
    ordered = sorted(winning.values())
    base = [f for _pos, f, is_esm in ordered if is_esm] + [f for _pos, f, is_esm in ordered if not is_esm]
    present = {f.lower(): f for f in base}
    edges = {}            # edges[y] = {x}: x loads before y
    for f in base:
        for mst in masters_of.get(f.lower(), ()):
            if mst in present:
                edges.setdefault(f.lower(), set()).add(mst)
    first, last = set(), set()
    for r in ruler_user_rules:
        if not r.get("enabled", True):
            continue
        p, t, k = str(r.get("plugin", "")).lower(), str(r.get("target", "")).lower(), r.get("type", r.get("rule_type", ""))
        if p not in present:
            continue
        if k == "before" and t in present:
            edges.setdefault(t, set()).add(p)
        elif k == "after" and t in present:
            edges.setdefault(p, set()).add(t)
        elif k == "first":
            first.add(p)
        elif k == "last":
            last.add(p)
    rank = {f.lower(): i for i, f in enumerate(base)}

    def key(f):
        return (0 if f in first else 2 if f in last else 1, rank[f])
    indeg = {f.lower(): 0 for f in base}
    children = {}
    for y, xs in edges.items():
        for x in xs:
            if x in indeg and y in indeg:
                indeg[y] += 1
                children.setdefault(x, []).append(y)
    ready = [(key(f), f) for f in indeg if indeg[f] == 0]
    heapq.heapify(ready)
    out = []
    while ready:
        _k, f = heapq.heappop(ready)
        out.append(present[f])
        for c in children.get(f, ()):
            indeg[c] -= 1
            if indeg[c] == 0:
                heapq.heappush(ready, (key(c), c))
    if len(out) != len(base):        # a cycle: keep the pane order for the rest
        done = {f.lower() for f in out}
        out += [f for f in base if f.lower() not in done]
    return out


RULES_FILE = "modlist_order_rules.json"


def read_active_plugins(profile_dir):
    """Plugins MO2 will load: the '*' lines of plugins.txt plus the game's forced masters and CC content, which MO2
    lists without a star."""
    active = set()
    p = os.path.join(profile_dir, "plugins.txt")
    if os.path.isfile(p):
        for line in open(p, encoding="utf-8-sig"):
            line = line.strip()
            if line.startswith("*"):
                active.add(line[1:].lower())
            elif line and not line.startswith("#") and (line.lower() in BASE_MASTERS or line.lower().startswith("cc")):
                active.add(line.lower())
    return active | BASE_MASTERS


def plan_plugin_state(mods, profile_dir, plugin_rules=()):
    """Every plugin ends up in one of two places (the owner, 2026-09-23): a plugin whose masters are all here is in the
    mod's root and ACTIVE; one that cannot load - a master it needs is in no enabled mod - waits in the mod's
    optional folder (MO2's Optional ESPs). And the way back: an optional plugin whose masters have since arrived
    (a mod you added) is moved back beside the mod's files and activated. A plugin rule of type "off" keeps a plugin
    in Optional ESPs whatever its masters. Returns {"activate": [(plugin, mod, why)], "to_optional": [...],
    "from_optional": [...]} and rewrites each Mod's plugins/optional lists to the planned state, so the plugin
    order and BPM groups computed afterwards describe the pane as it will be."""
    active = read_active_plugins(profile_dir)
    off = {str(r.get("plugin", "")).lower() for r in plugin_rules if r.get("type") == "off" and r.get("enabled", True)}
    root, opt = {}, {}                          # plugin name -> (mod, entry): the LOWEST enabled mod wins, as in MO2
    for m in mods:
        if not m.enabled or is_sep(m.name):
            continue
        for e in m.plugins:
            root[e[0].lower()] = (m, e)
        for e in m.optional:
            opt.setdefault(e[0].lower(), (m, e))
    # loadable = every master is a base master, or a candidate (root or optional) that is itself loadable and not off
    cands = {k: v[1][1] for k, v in root.items()}
    cands.update({k: v[1][1] for k, v in opt.items() if k not in cands})
    loadable = {k: True for k in cands}
    changed = True
    while changed:
        changed = False
        for k, masters in cands.items():
            if not loadable[k]:
                continue
            for ms in masters:
                mk = ms.lower()
                if mk in BASE_MASTERS:
                    continue
                if mk in off or mk not in cands or not loadable[mk]:
                    loadable[k] = False
                    changed = True
                    break

    def missing(masters):
        return [ms for ms in masters if ms.lower() not in BASE_MASTERS and not loadable.get(ms.lower(), False)]

    plan = {"activate": [], "to_optional": [], "from_optional": []}
    for k, (m, e) in root.items():
        f, masters, _esm = e
        if k in off:
            plan["to_optional"].append((f, m.name, "rule: kept off"))
        elif not loadable[k]:
            plan["to_optional"].append((f, m.name, "needs " + ", ".join(missing(masters)) + " - not in any enabled mod"))
        elif k not in active:
            plan["activate"].append((f, m.name, "every master is present"))
    for k, (m, e) in opt.items():
        f, masters, _esm = e
        if k in root or k in off or not loadable[k]:
            continue
        # only a plugin that DEPENDS on another mod comes back - "a mod that uses the optional esp". One whose
        # masters are all base game (an author's preview or examples plugin) sits in Optional ESPs by design
        needs = [ms for ms in masters if ms.lower() not in BASE_MASTERS]
        if not needs:
            continue
        plan["from_optional"].append((f, m.name, "its masters are present now: " + ", ".join(needs[:4])))
    # rewrite the mods to the planned state
    for f, mod_name, _why in plan["to_optional"]:
        for m in mods:
            if m.name == mod_name:
                moved = [e for e in m.plugins if e[0] == f]
                m.plugins = [e for e in m.plugins if e[0] != f]
                m.optional.extend(moved)
    for f, mod_name, _why in plan["from_optional"]:
        for m in mods:
            if m.name == mod_name:
                moved = [e for e in m.optional if e[0] == f]
                m.optional = [e for e in m.optional if e[0] != f]
                m.plugins.extend(moved)
    return plan


def apply_plugin_state(plan, mods_dir, backup_dir, log=None):
    """Move the files: root <-> optional. Every move is recorded in the backup folder (plugin-moves.json) so it can
    be undone by hand."""
    moves = []
    for f, mod_name, why in plan.get("to_optional", []):
        src, dst_dir = os.path.join(mods_dir, mod_name, f), os.path.join(mods_dir, mod_name, "optional")
        if os.path.isfile(src):
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, f)
            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)
            moves.append({"plugin": f, "mod": mod_name, "from": "root", "to": "optional", "why": why})
    for f, mod_name, why in plan.get("from_optional", []):
        src, dst = os.path.join(mods_dir, mod_name, "optional", f), os.path.join(mods_dir, mod_name, f)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.move(src, dst)
            moves.append({"plugin": f, "mod": mod_name, "from": "optional", "to": "root", "why": why})
    if moves:
        json.dump(moves, open(os.path.join(backup_dir, "plugin-moves.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if log:
        log(f"plugins: {len(plan.get('activate', []))} activated, {len(plan.get('to_optional', []))} to Optional ESPs, "
            f"{len(plan.get('from_optional', []))} back from Optional ESPs")
    return moves


def load_rules(profile_dir):
    """The generator's own rules: {"rules": [mod rules], "plugin_rules": [plugin rules], "pins": {mod: separator}}.
    A rule is {"type": after|before|first|last, "mod"|"plugin": name, "target": name, "enabled": bool}."""
    ours = {"rules": [], "plugin_rules": [], "pins": {}}
    p = os.path.join(profile_dir, RULES_FILE)
    if os.path.isfile(p):
        try:
            ours.update(json.load(open(p, encoding="utf-8")))
        except (OSError, ValueError):
            pass
    ours.setdefault("rules", [])
    ours.setdefault("plugin_rules", [])
    ours.setdefault("pins", {})
    for key_ in ("rules", "plugin_rules"):          # an older build let "Keep" write the same rule twice
        seen, kept = set(), []
        for r in ours[key_]:
            sig = json.dumps({k: v for k, v in r.items() if k != "comment"}, sort_keys=True)
            if sig not in seen:
                seen.add(sig)
                kept.append(r)
        ours[key_] = kept
    return ours, ours["plugin_rules"]


def save_rules(profile_dir, ours):
    json.dump(ours, open(os.path.join(profile_dir, RULES_FILE), "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def plugin_groups(rows, mods_by_name):
    """{plugin file: group name} for Bethesda Plugin Manager - each plugin takes the block its mod sits under in the
    new pane (the separator's name without "_separator"; a tier header is skipped in favour of the block under it).
    BPM keeps groups in profiles/<profile>/plugingroups.txt as "plugin|group" lines, one plugin per line."""
    groups = {}
    block = None
    for nm, en in rows:
        if is_sep(nm):
            if not nm.startswith("---"):
                block = nm[:-len("_separator")]
            continue
        m = mods_by_name.get(nm)
        if not m or not en or block is None:
            continue
        for f, _masters, is_esm in m.plugins:
            # the game hoists every master-block plugin (.esm, .esl, ESM flag) above the first .esp, so a block's
            # masters and its .esp files can never sit together; giving the masters their own group keeps each
            # group in one piece instead of the same name heading two places in the right pane
            # the LOWEST enabled mod shipping a plugin is the one MO2 loads, so its block is the plugin's group;
            # taking the first (upper) mod's block put a one-plugin island of another group inside a block
            groups[f] = block + " - Masters" if is_esm else block
    return groups


def bpm_installed(instance_dir):
    """Bethesda Plugin Manager is present when its DLL sits in the instance's plugins folder (bsplugins.dll). Only it
    reads plugingroups.txt, so without it no group file is written and the dialog says so."""
    d = os.path.join(instance_dir, "plugins")
    try:
        return any(n.lower().startswith("bsplugins") and n.lower().endswith(".dll") for n in os.listdir(d))
    except OSError:
        return False


def write_plugin_groups(path, groups, order):
    """plugingroups.txt in BPM's form: the MO2 header comment, then plugin|group in load order, CRLF."""
    lines = ["# This file was automatically generated by Mod Organizer."]
    for f in order:
        g = groups.get(f)
        if g:
            lines.append(f"{f}|{g}")
    open(path, "wb").write(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return len(lines) - 1


def ruler_rules(mods):
    """The master facts as rule rows, for reading: plugin AFTER each master (from the TES4 headers)."""
    rules = []
    for m in mods:
        for f, masters, _esm in m.plugins:
            for mast in masters:
                if mast.lower() in BASE_MASTERS:
                    continue
                rules.append({"rule_type": "after", "plugin": f, "target": mast, "comment": "master (TES4 header)",
                              "enabled": True, "source": "auto:master"})
    return rules


def diff(mods, rows):
    """Per mod: (name, old separator, new separator, old index, new index) for everything that changes."""
    def heads(seq):
        h, cur = {}, None
        for nm in seq:
            if is_sep(nm):
                cur = nm
            else:
                h[nm] = cur
        return h
    old_names = [m.name for m in mods]
    new_names = [nm for nm, _ in rows]
    ho, hn = heads(old_names), heads(new_names)
    oi = {nm: i for i, nm in enumerate(old_names)}
    ni = {nm: i for i, nm in enumerate(new_names)}
    out = []
    for nm in old_names:
        if is_sep(nm) or nm not in ni:
            continue
        if ho.get(nm) != hn.get(nm) or oi[nm] != ni[nm]:
            out.append((nm, ho.get(nm), hn.get(nm), oi[nm], ni[nm]))
    return out


def run(instance_dir, profile, cache_dir, domain="skyrimspecialedition", progress=None, log=None, keep_winners=True, mode="index", min_run=8):
    """Everything up to (not including) writing. Returns a dict the dialog and the offline runner both use."""
    mods_dir = os.path.join(instance_dir, "mods")
    ml = os.path.join(instance_dir, "profiles", profile, "modlist.txt")
    rows, header = read_modlist(ml)
    mods = scan(mods_dir, rows, progress)
    cats, asked, got = fetch_categories([m.nexus_id for m in mods], os.path.join(cache_dir, "nexus-categories.json"), domain, progress, log)
    under = set()
    inside = False
    for nm, _ in rows:
        if is_sep(nm):
            inside = re.sub(r"[\s\[\]\-_.]", "", nm[:-len("_separator")]).lower() == "nodelete"
        elif inside:
            under.add(nm)
    ours, theirs = load_rules(os.path.join(instance_dir, "profiles", profile))
    plugin_state = plan_plugin_state(mods, os.path.join(instance_dir, "profiles", profile), theirs)
    place(mods, cats, read_mo2_categories(instance_dir), under, ours.get("pins"))
    new_rows, facts = build(mods, ours.get("rules"), keep_winners, mode, min_run)
    by_name = {m.name: m for m in mods}
    plugins = plugin_order(new_rows, by_name, theirs)
    return {"mods": mods, "rows": new_rows, "header": header, "facts": facts, "moves": diff(mods, new_rows),
            "category_updates": plan_mo2_category_updates(mods, cats, instance_dir),
            "plugin_groups": plugin_groups(new_rows, by_name), "bpm": bpm_installed(instance_dir),
            "plugin_state": plugin_state,
            "plugins": plugins, "rules": ruler_rules(mods), "mod_rules": ours,
            "nexus": f"{len(cats)} categories cached, {got} of {asked} fetched now",
            "modlist_path": ml, "mods_dir": mods_dir}


def apply(result, instance_dir, profile, cache_dir, log=None):
    """Write it: backups, separator folders, modlist.txt, plugins.txt/loadorder.txt, the rules file."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(cache_dir, "backups", stamp)
    prof = os.path.join(instance_dir, "profiles", profile)
    os.makedirs(backup, exist_ok=True)
    for f in ("modlist.txt", "plugins.txt", "loadorder.txt", "plugingroups.txt", RULES_FILE):
        p = os.path.join(prof, f)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(backup, f))
    mods_dir = result["mods_dir"]
    # a new separator takes the colour the existing ones use (the most common color= line among them); without it
    # MO2 draws its default grey - the owner, 2026-09-22: "It changed all the separators' colors to gray instead of
    # black" after 151 of his black separators were retired and 40 colourless ones created
    colours = {}
    for name in os.listdir(mods_dir):
        if name.endswith("_separator"):
            try:
                for line in open(os.path.join(mods_dir, name, "meta.ini"), encoding="utf-8", errors="ignore"):
                    if line.startswith("color="):
                        colours[line.strip()] = colours.get(line.strip(), 0) + 1
            except OSError:
                pass
    colour = max(colours, key=colours.get) if colours else None
    for name in result["facts"]["created"]:
        d = os.path.join(mods_dir, name)
        if not os.path.isdir(d):
            os.makedirs(d)
            head = "[General]\n" + (colour + "\n" if colour else "")
            open(os.path.join(d, "meta.ini"), "w", encoding="utf-8").write(
                head + "modid=0\nversion=\nnewestVersion=\ncategory=0\ninstallationFile=\n\n[installedFiles]\nsize=0\n")
    retired_dir = os.path.join(backup, "retired-separators")
    for name in result["facts"]["retired"]:
        d = os.path.join(mods_dir, name)
        if os.path.isdir(d):
            os.makedirs(retired_dir, exist_ok=True)
            shutil.move(d, os.path.join(retired_dir, name))
    write_modlist(result["modlist_path"], result["rows"], result["header"])
    apply_plugin_state(result.get("plugin_state", {}), mods_dir, backup, log)
    plugins = result["plugins"]
    open(os.path.join(prof, "loadorder.txt"), "wb").write(("# This file was automatically generated by Mod Organizer.\r\n" + "\r\n".join(plugins) + "\r\n").encode("utf-8"))
    # plugins.txt: every plugin left in a mod's root is active - what must not load now sits in optional - except the
    # game's forced masters and CC content, which MO2 lists without a star and which keep the line they had
    p = os.path.join(prof, "plugins.txt")
    forced_line = {}
    if os.path.isfile(p):
        for line in open(p, encoding="utf-8-sig"):
            line = line.strip()
            k = line.lstrip("*").lower()
            if k in BASE_MASTERS or k.startswith("cc"):
                forced_line[k] = line
    open(p, "wb").write(("# This file was automatically generated by Mod Organizer.\r\n"
                         + "\r\n".join(forced_line.get(f.lower(), "*" + f) for f in plugins) + "\r\n").encode("utf-8"))
    ours, _ = load_rules(prof)
    ours["auto_master_rules"] = result["rules"]          # the facts the order was built on, for reading; never edited
    save_rules(prof, ours)
    # Bethesda Plugin Manager's groups: the right pane shows the same blocks as the left - only when BPM is there
    if bpm_installed(instance_dir):
        n_groups = write_plugin_groups(os.path.join(prof, "plugingroups.txt"), result.get("plugin_groups", {}), plugins)
        if log:
            log(f"plugin groups written for {n_groups} plugins ({len(set(result.get('plugin_groups', {}).values()))} groups)")
    elif log:
        log("Bethesda Plugin Manager not installed: no plugingroups.txt written")
    if log:
        log(f"applied: {len(result['rows'])} rows, {len(result['facts']['created'])} separators created, "
            f"{len(result['facts']['retired'])} retired, {len(plugins)} plugins ordered, {len(result['rules'])} auto rules; backups in {backup}")
    return backup


# --- MO2 -------------------------------------------------------------------------------------------------------------------
try:
    import mobase
except ImportError:      # the offline runner
    mobase = None

if mobase is not None:
    try:
        from PyQt6.QtCore import QSize, Qt, QTimer
        from PyQt6.QtGui import QAction, QIcon
        from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView,
                                     QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
                                     QToolButton, QTreeView, QVBoxLayout, QWidget)
    except ImportError:
        from PyQt5.QtCore import QSize, Qt, QTimer
        from PyQt5.QtGui import QIcon
        from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView,
                                     QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
                                     QToolButton, QTreeView, QVBoxLayout, QWidget)
        from PyQt5.QtWidgets import QAction

    class RulerDialog(QDialog):
        def __init__(self, plugin, parent=None):
            super().__init__(parent)
            self._p = plugin
            self._result = None
            self.setWindowTitle("MO2 Modlist Manager")
            self.resize(1100, 720)
            root = QVBoxLayout(self)
            self.summary = QLabel("Reading the list and asking Nexus for categories...")
            self.summary.setWordWrap(True)
            root.addWidget(self.summary)
            self.tabs = QTabWidget()
            root.addWidget(self.tabs, 1)
            self.t_moves = self._table(["Mod", "Was under", "Goes under", "Line", "New line"])
            self.t_seps = self._table(["Separator", "Change"])
            self.t_disp = self._table(["Mod", "Its category", "In the block", "Because"])
            self.t_conf = self._table(["Wins today", "Would lose to", "Shared files", "The index says"])
            self.t_conf.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.t_conf.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.t_place = self._table(["Mod", "Tier", "Separator", "Why"])
            self.tabs.addTab(self.t_moves, "Moves")
            self.tabs.addTab(self.t_seps, "Separators")
            self.tabs.addTab(self.t_disp, "Minorities / displaced")
            conf_page = QWidget()
            cl = QVBoxLayout(conf_page)
            cl.addWidget(QLabel("Where today's order disagrees with the index. Each row is a call to make once: keep today's "
                                "winner (written as an 'after' rule, so it holds on every run) or let the index decide."))
            cl.addWidget(self.t_conf, 1)
            row = QHBoxLayout()
            b_all = QPushButton("Select all")
            b_all.clicked.connect(self.t_conf.selectAll)
            b_none = QPushButton("Select none")
            b_none.clicked.connect(self.t_conf.clearSelection)
            b_keep = QPushButton("Keep today's winner for the selected rows (add rules)")
            b_keep.clicked.connect(self._keep_selected_winners)
            row.addWidget(b_all)
            row.addWidget(b_none)
            row.addWidget(b_keep, 1)
            cl.addLayout(row)
            self.tabs.addTab(conf_page, "Review")
            self.tabs.addTab(self.t_place, "Every placement")
            self.t_plug = self._table(["Plugin", "Mod", "Action", "Why"])
            self.tabs.addTab(self.t_plug, "Plugins")
            self.tabs.addTab(self._rules_tab(), "Rules")
            opts = QHBoxLayout()
            opts.addWidget(QLabel("Order:"))
            self.cb_mode = QComboBox()
            self.cb_mode.addItem("the six-tier index - tier by evidence, general before specific, masters and outputs enforced; today's winners reported", "index")
            self.cb_mode.addItem("keep today's order - separators generated over it", "spine")
            self.cb_mode.addItem("category blocks in the list's own tier order - winners kept by displacing", "blocks")
            opts.addWidget(self.cb_mode, 3)
            opts.addWidget(QLabel("Smallest block:"))
            self.sp_run = QSpinBox()
            self.sp_run.setRange(1, 60)
            self.sp_run.setValue(8)
            opts.addWidget(self.sp_run)
            self.c_keep = QCheckBox("keep today's override winners")
            self.c_keep.setChecked(True)          # on by default (the owner, 2026-09-23): tested winners stay unless he says otherwise
            opts.addWidget(self.c_keep)
            root.insertLayout(1, opts)
            self.cb_mode.currentIndexChanged.connect(lambda _i: self.compute())
            self.sp_run.valueChanged.connect(lambda _v: self.compute())
            self.c_keep.toggled.connect(lambda _c: self.compute())
            self.status = QLabel()
            self.status.setWordWrap(True)
            root.addWidget(self.status)
            buttons = QHBoxLayout()
            buttons.addStretch(1)
            self.b_cats = QPushButton("Update MO2 categories from Nexus")
            self.b_cats.setToolTip("Write each mod's Nexus category into its meta.ini as its MO2 category, for mods that have none")
            self.b_cats.clicked.connect(self.update_categories)
            buttons.addWidget(self.b_cats)
            self.b_refresh = QPushButton("Compute again")
            self.b_apply = QPushButton("Apply")
            self.b_close = QPushButton("Close")
            for b in (self.b_refresh, self.b_apply, self.b_close):
                buttons.addWidget(b)
            root.addLayout(buttons)
            self.b_refresh.clicked.connect(self.compute)
            self.b_apply.clicked.connect(self.apply)
            self.b_close.clicked.connect(self.close)
            self.b_apply.setEnabled(False)
            QApplication.processEvents()
            self.compute()

        def _rules_tab(self):
            w = QWidget()
            v = QVBoxLayout(w)
            v.addWidget(QLabel("A rule beats the evidence and is kept in the profile (mod_ruler_rules.json). "
                               "after / before: the mod sits beside the target and joins its separator. first / last: top or bottom of its own "
                               "separator. pin: the mod goes under the named separator whatever Nexus says."))
            self.t_rules = self._table(["Kind", "Mod", "Target / separator", "On"])
            v.addWidget(self.t_rules, 1)
            form = QHBoxLayout()
            self.r_kind = QComboBox()
            self.r_kind.addItems(["after", "before", "first", "last", "pin", "plugin after", "plugin before", "plugin first", "plugin last", "plugin off"])
            self.r_mod = QLineEdit()
            self.r_mod.setPlaceholderText("mod name - or plugin file name for a plugin rule")
            self.r_target = QLineEdit()
            self.r_target.setPlaceholderText("target mod / plugin, or separator name for pin")
            b_add = QPushButton("Add")
            b_del = QPushButton("Remove selected")
            b_sel = QPushButton("Use selected mod")
            for x in (self.r_kind, self.r_mod, self.r_target, b_sel, b_add, b_del):
                form.addWidget(x)
            v.addLayout(form)
            b_add.clicked.connect(self._rule_add)
            b_del.clicked.connect(self._rule_del)
            b_sel.clicked.connect(self._rule_pick)
            return w

        def _rules_rows(self):
            r = self._p.rules()
            rows = [(x.get("type", ""), x.get("mod", ""), x.get("target", ""), "yes" if x.get("enabled", True) else "no") for x in r.get("rules", [])]
            rows += [("plugin " + x.get("type", ""), x.get("plugin", ""), x.get("target", ""), "yes" if x.get("enabled", True) else "no") for x in r.get("plugin_rules", [])]
            rows += [("pin", m, sep, "yes") for m, sep in r.get("pins", {}).items()]
            return rows

        def _rule_add(self):
            kind, mod, target = self.r_kind.currentText(), self.r_mod.text().strip(), self.r_target.text().strip()
            if not mod or (kind in ("after", "before", "pin") and not target):
                return
            r = self._p.rules()
            if kind == "pin":
                r.setdefault("pins", {})[mod] = target
            elif kind.startswith("plugin "):
                r.setdefault("plugin_rules", []).append({"type": kind[7:], "plugin": mod, "target": target, "enabled": True})
            else:
                r.setdefault("rules", []).append({"type": kind, "mod": mod, "target": target, "enabled": True})
            self._p.save_rules(r)
            self._fill(self.t_rules, self._rules_rows())
            self.compute()

        def _rule_del(self):
            rows = sorted({i.row() for i in self.t_rules.selectedIndexes()}, reverse=True)
            if not rows:
                return
            r = self._p.rules()
            table = self._rules_rows()
            for i in rows:
                kind, mod, target, _on = table[i]
                if kind == "pin":
                    r.get("pins", {}).pop(mod, None)
                elif kind.startswith("plugin "):
                    r["plugin_rules"] = [x for x in r.get("plugin_rules", []) if not (x.get("type") == kind[7:] and x.get("plugin") == mod and x.get("target", "") == target)]
                else:
                    r["rules"] = [x for x in r.get("rules", []) if not (x.get("type") == kind and x.get("mod") == mod and x.get("target", "") == target)]
            self._p.save_rules(r)
            self._fill(self.t_rules, self._rules_rows())
            self.compute()

        def _keep_selected_winners(self):
            rows = sorted({i.row() for i in self.t_conf.selectedIndexes()})
            if not rows or not self._result:
                return
            r = self._p.rules()
            table = self._result["facts"]["flips"] + self._result["facts"]["advice"]
            have = {(x.get("type"), x.get("mod"), x.get("target")) for x in r.get("rules", [])}
            for i in rows:
                w, l, _n, _k = table[i]
                if ("after", w, l) in have:
                    continue
                r.setdefault("rules", []).append({"type": "after", "mod": w, "target": l, "enabled": True,
                                                  "comment": "kept today's winner (review)"})
            self._p.save_rules(r)
            self._fill(self.t_rules, self._rules_rows())
            self.compute()

        def _rule_pick(self):
            """The mod selected in MO2's list goes into the form."""
            name = self._p.selected_mod()
            if name:
                self.r_mod.setText(name)

        def _table(self, cols):
            t = QTableWidget(0, len(cols))
            t.setHorizontalHeaderLabels(cols)
            t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            t.verticalHeader().setVisible(False)
            return t

        def _fill(self, t, rows):
            t.setRowCount(len(rows))
            for i, r in enumerate(rows):
                for j, v in enumerate(r):
                    t.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))

        def compute(self):
            self.b_apply.setEnabled(False)
            self.summary.setText("Reading the list and asking Nexus for categories...")
            QApplication.processEvents()
            try:
                def progress(done, total, what):
                    # the first run asks Nexus for every mod's category, twenty a request - a couple of minutes on a
                    # 2,000-mod list; say so instead of sitting on "reading the list"
                    if what == "nexus":
                        self.summary.setText(f"Asking Nexus for categories: {done} of {total} mods (cached after this run)...")
                    elif total and done % 200 == 0:
                        self.summary.setText(f"Reading the list: {done} of {total}...")
                    QApplication.processEvents()
                    return True
                self._result = self._p.compute(progress, self.c_keep.isChecked(), self.cb_mode.currentData(), self.sp_run.value())
            except Exception as exc:  # noqa: BLE001
                self._p._log(f"compute failed: {exc!r}")
                self.summary.setText(f"Failed: {exc}")
                return
            r = self._result
            mods = [m for m in r["mods"] if not is_sep(m.name)]
            self.b_cats.setText(f"Update MO2 categories from Nexus ({len(r.get('category_updates', []))} without one)")
            self.summary.setText(
                f"{len(mods)} mods - {r['nexus']} - {len(r['moves'])} mod(s) change separator or line - "
                f"{len(r['facts']['created'])} separator(s) created, {len(r['facts']['retired'])} retired - "
                f"{len(r['facts']['absorbed'])} in a block of another category, {len(r['facts']['displaced'])} displaced by a master or a kept winner - "
                f"{len(r['facts']['flips'])} override winner(s) would flip - {len(r['plugins'])} plugins ordered"
                f" ({len(r.get('plugin_state', {}).get('activate', []))} to activate, {len(r.get('plugin_state', {}).get('to_optional', []))} to Optional ESPs, "
                f"{len(r.get('plugin_state', {}).get('from_optional', []))} back from Optional ESPs)"
                + (f" into {len(set(r.get('plugin_groups', {}).values()))} BPM groups" if r.get("bpm") else " (no Bethesda Plugin Manager: no groups)"))
            self._fill(self.t_moves, [(n, (o or "")[:-len("_separator")] if o else "", (w or "")[:-len("_separator")] if w else "", a, b) for n, o, w, a, b in r["moves"]])
            self._fill(self.t_seps, [(s[:-len("_separator")], "created") for s in r["facts"]["created"]] + [(s[:-len("_separator")], "retired (folder moved to the backup)") for s in r["facts"]["retired"]])
            self._fill(self.t_disp, [(a, b, c, "") for a, b, c in r["facts"]["absorbed"]] + r["facts"]["displaced"])
            self._fill(self.t_conf, r["facts"]["flips"] + r["facts"]["advice"])
            # the box and the selection agree: ticked = every review row selected, unticked = none (the owner, 2026-09-23)
            if self.c_keep.isChecked():
                self.t_conf.selectAll()
            else:
                self.t_conf.clearSelection()
            self._fill(self.t_place, [(m.name, f"{index_tier(m.category, m)} " + TIER_HEADERS.get(index_tier(m.category, m), "NoDelete").strip("- ").title(), m.category, m.why) for m in mods])
            self._fill(self.t_rules, self._rules_rows())
            ps = r.get("plugin_state", {})
            self._fill(self.t_plug, [(f, m, "activate", w) for f, m, w in ps.get("activate", [])]
                       + [(f, m, "move to Optional ESPs", w) for f, m, w in ps.get("to_optional", [])]
                       + [(f, m, "back from Optional ESPs, activate", w) for f, m, w in ps.get("from_optional", [])])
            n_plug = sum(len(ps.get(k, [])) for k in ("activate", "to_optional", "from_optional"))
            self.tabs.setTabText(self.tabs.indexOf(self.t_plug), f"Plugins ({n_plug})" if n_plug else "Plugins")
            self.b_apply.setEnabled(bool(r["moves"] or r["facts"]["created"] or r["facts"]["retired"] or n_plug))
            self.status.setText("Nothing is written until Apply. Apply backs up modlist.txt, plugins.txt, loadorder.txt and the retired separators first.")

        def update_categories(self):
            if not self._result:
                return
            ups = self._result.get("category_updates", [])
            if not ups:
                self.status.setText("Every mod with a Nexus page already has an MO2 category.")
                return
            self.status.setText(f"Writing MO2 categories for {len(ups)} mod(s)...")
            QApplication.processEvents()
            done = apply_mo2_category_updates(ups, self._p._log)
            try:
                self._p._organizer.refresh(False)     # re-read the meta.ini files just written; never save over them
            except Exception:  # noqa: BLE001
                pass
            self.status.setText(f"MO2 categories written for {done} of {len(ups)} mod(s) from their Nexus category; MO2 refreshed.")
            self.compute()

        def apply(self):
            if not self._result:
                return
            self.b_apply.setEnabled(False)
            self.status.setText("Applying...")
            QApplication.processEvents()
            try:
                backup = self._p.apply(self._result)
                self.status.setText(f"Applied. Backups in {backup}. MO2 has been refreshed.")
            except Exception as exc:  # noqa: BLE001
                self._p._log(f"apply failed: {exc!r}")
                self.status.setText(f"Failed: {exc}")

    class MO2ModlistManager(mobase.IPluginTool):
        def __init__(self):
            super().__init__()
            self._organizer = None
            self._parent = None

        def init(self, organizer):
            self._organizer = organizer
            # ITS OWN BUTTON ON THE TOOLBAR (the owner, 2026-09-22: "its own button at the top with a unique icon,
            # using the same automatic refresh logic"). The same mechanism as the NoDelete button: poll until MO2's
            # toolbar exists, insert the action before Settings, then keep checking lightly - MO2 rebuilds parts of
            # the toolbar when executables or its style change, and the button is put back when that drops it.
            self._toolbar_action = None
            self._toolbar_timer = QTimer()
            self._toolbar_timer.setInterval(500)
            self._toolbar_timer.timeout.connect(self._keep_toolbar_button)
            self._toolbar_timer.start()
            return True

        def _keep_toolbar_button(self):
            try:
                app = QApplication.instance()
                if app is None:
                    return
                window = None
                for w in app.topLevelWidgets():
                    if w.metaObject().className() == "MainWindow" or w.objectName() == "MainWindow":
                        window = w
                        break
                if window is None:
                    for w in app.topLevelWidgets():
                        if w.findChild(QToolBar) is not None and w.isVisible():
                            window = w
                            break
                if window is None:
                    return
                toolbars = window.findChildren(QToolBar)
                if not toolbars:
                    return
                tb = toolbars[0]
                if self._toolbar_action is not None and self._toolbar_action in tb.actions():
                    self._toolbar_timer.setInterval(2000)      # in place: just keep an eye on it
                    return
                act = QAction(self.icon(), self.displayName(), window)
                act.setObjectName("MO2ModlistManagerAction")
                act.setToolTip(self.tooltip())
                act.triggered.connect(self.display)
                anchor = None
                for a in tb.actions():
                    text = (a.text() or "").replace("&", "").lower()
                    if "settings" in text or "settings" in (a.toolTip() or "").lower():
                        anchor = a
                        break
                if anchor is not None:
                    tb.insertAction(anchor, act)
                else:
                    tb.addAction(act)
                btn = tb.widgetForAction(act)
                if isinstance(btn, QToolButton):
                    btn.setObjectName("MO2ModlistManagerBtn")
                    btn.setAutoRaise(True)
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                    btn.setIconSize(tb.iconSize())
                self._toolbar_action = act
                self._log("toolbar button added")
            except Exception as exc:  # noqa: BLE001
                self._log(f"toolbar button: {exc!r}")

        def name(self):
            return "MO2 Modlist Manager"

        def author(self):
            return "ApocryphaRealm"

        def description(self):
            return ("Generates the left pane: separators named after each mod's Nexus category in load order, mods placed "
                    "under them, masters above dependents, the plugin list following the pane. Preview first, one Apply.")

        def version(self):
            return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.FINAL)

        def isActive(self):
            return True

        def settings(self):
            return []

        def displayName(self):
            return "MO2 Modlist Manager"

        def tooltip(self):
            return "Generate separators and place every mod in order"

        def icon(self):
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MO2ModlistManager.png")
            return QIcon(p) if os.path.isfile(p) else QIcon()

        def setParentWidget(self, widget):
            self._parent = widget

        def _cache_dir(self):
            return os.path.join(self._organizer.basePath(), "plugins", "data", "MO2ModlistManager")

        def _log(self, msg):
            try:
                os.makedirs(self._cache_dir(), exist_ok=True)
                with open(os.path.join(self._cache_dir(), "log.txt"), "a", encoding="utf-8") as fh:
                    fh.write(time.strftime("%H:%M:%S ") + msg + "\n")
            except OSError:
                pass

        def compute(self, progress=None, keep_winners=True, mode="index", min_run=8):
            org = self._organizer
            org.refresh(True)      # so modlist.txt on disk is what the pane shows
            domain = "skyrimspecialedition"
            try:
                domain = org.managedGame().gameNexusName() or domain
            except Exception:  # noqa: BLE001
                pass
            return run(org.basePath(), org.profileName(), self._cache_dir(), domain, progress, self._log, keep_winners, mode, min_run)

        def rules(self):
            return load_rules(os.path.join(self._organizer.basePath(), "profiles", self._organizer.profileName()))[0]

        def save_rules(self, ours):
            save_rules(os.path.join(self._organizer.basePath(), "profiles", self._organizer.profileName()), ours)

        def selected_mod(self):
            """The first mod selected in MO2's mod list, by reading the modList view's selection."""
            try:
                view = self._parent.findChild(QTreeView, "modList") if self._parent else None
                if view is None:
                    return ""
                names = set(self._organizer.modList().allMods())
                for idx in view.selectionModel().selectedRows():
                    val = idx.data()
                    if isinstance(val, str) and val in names:
                        return val
            except Exception:  # noqa: BLE001
                pass
            return ""

        def apply(self, result):
            org = self._organizer
            backup = apply(result, org.basePath(), org.profileName(), self._cache_dir(), self._log)
            # refresh WITHOUT saving: refresh(True) first writes MO2's in-memory lists to disk, and Bethesda Plugin
            # Manager's copy of the groups went down with them - 350 of 1,792 plugins were back in their old
            # groups after the 2026-09-22 Apply. With False the lists are re-read from the files just written.
            org.refresh(False)
            try:
                org.pluginList().setLoadOrder(result["plugins"])
            except Exception as exc:  # noqa: BLE001
                self._log(f"setLoadOrder skipped: {exc!r}")
            self._verify_groups_later(result)
            return backup

        def _verify_groups_later(self, result):
            """A few seconds after Apply, read plugingroups.txt back: if BPM has written older groups over it, put
            ours back and say so in the log, so a stale in-memory copy is visible rather than silent."""
            want = result.get("plugin_groups") or {}
            if not want or not bpm_installed(self._organizer.basePath()):
                return
            path = os.path.join(self._organizer.basePath(), "profiles", self._organizer.profileName(), "plugingroups.txt")
            order = list(result["plugins"])

            def check():
                try:
                    have = {}
                    for line in open(path, encoding="utf-8-sig"):
                        if "|" in line and not line.startswith("#"):
                            k, v = line.strip().split("|", 1)
                            have[k] = v
                    wrong = [k for k, v in want.items() if have.get(k) not in (None, v)]
                    if wrong:
                        write_plugin_groups(path, want, order)
                        self._log(f"plugin groups: BPM had written {len(wrong)} plugin(s) back into older groups; file rewritten "
                                  f"(first: {wrong[:3]}). If they revert again, restart MO2 so BPM re-reads the file.")
                    else:
                        self._log("plugin groups verified against plugingroups.txt")
                except Exception as exc:  # noqa: BLE001
                    self._log(f"plugin group check failed: {exc!r}")

            try:
                QTimer.singleShot(4000, check)
            except Exception:  # noqa: BLE001
                check()

        def display(self):
            try:
                RulerDialog(self, self._parent).exec()
            except Exception as exc:  # noqa: BLE001
                self._log(f"display failed: {exc!r}")

    def createPlugin():
        return MO2ModlistManager()


if __name__ == "__main__" and mobase is None:       # offline dry run: python MO2ModlistManager.py <instance> <profile> <cache dir>
    # (MO2 executes a plugin file with __name__ == "__main__" too - the mobase check keeps this block out of its way)
    import sys
    if len(sys.argv) < 4:
        raise SystemExit("usage: MO2ModlistManager.py <instance dir> <profile> <cache dir> [spine|blocks]")
    inst, prof, cache = sys.argv[1], sys.argv[2], sys.argv[3]
    mode = sys.argv[4] if len(sys.argv) > 4 else "index"
    res = run(inst, prof, cache, log=print, mode=mode)
    out = {"summary": res["nexus"], "moves": res["moves"], "facts": res["facts"], "plugins": res["plugins"],
           "plugin_groups": res["plugin_groups"],
           "rows": res["rows"], "placements": [(m.name, m.category, m.why) for m in res["mods"] if not is_sep(m.name)]}
    json.dump(out, open(os.path.join(cache, "dry-run.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    out["plugin_state"] = res["plugin_state"]
    json.dump(out, open(os.path.join(cache, "dry-run.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    ps = res["plugin_state"]
    print(res["nexus"]); print("moves", len(res["moves"]), "created", len(res["facts"]["created"]), "retired", len(res["facts"]["retired"]),
                               "fixes", len(res["facts"]["fixes"]), "plugins", len(res["plugins"]),
                               "| activate", len(ps["activate"]), "to optional", len(ps["to_optional"]), "from optional", len(ps["from_optional"]))


# --- fault handling (standing rule, 2026-09-23: every MO2 plugin of ours logs and arms faulthandler) ---------------
def _arm_faulthandler():
    """Arm Python's faulthandler once per process, into plugins\\data\\faults.log. When MO2 dies inside C++ with a
    Python slot on the stack, the minidump names only modules; faulthandler writes the Python frames of every
    thread first, so the log names the plugin and the line. Whichever of our plugins loads first arms it."""
    try:
        import faulthandler
        import os
        import time
        if faulthandler.is_enabled():
            return
        here = os.path.abspath(__file__)
        while os.path.basename(here).lower() != "plugins":
            parent = os.path.dirname(here)
            if parent == here:
                return
            here = parent
        path = os.path.join(here, "data", "faults.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fh = open(path, "a", encoding="utf-8")
        who = os.path.basename(os.path.dirname(__file__)) if os.path.basename(__file__) == "__init__.py" else os.path.basename(__file__)
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " faulthandler armed by " + who + chr(10))
        fh.flush()
        globals()["_FAULT_LOG_HANDLE"] = fh          # kept open for the life of the process
        faulthandler.enable(file=fh, all_threads=True)
    except Exception:  # noqa: BLE001
        pass


_arm_faulthandler()
