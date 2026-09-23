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
import zlib
import time
import urllib.error
import urllib.parse
import urllib.request

# --- the taxonomy: group header -> the Nexus category names under it, in load order ----------------------------------
NODELETE_SEP = "[NoDelete]"            # kept as the last separator with its contents untouched (Wabbajack's convention)
TAG_NODELETE = re.compile(r"^\s*\[nodelete\]", re.I)
TAG_PATCH = re.compile(r"(^|\s)\[patch\](\s|$)", re.I)      # a prefix (older names) or a suffix (MO2 Keyword Tagger 1.0.2)
BASE_MASTERS = {"skyrim.esm", "update.esm", "dawnguard.esm", "hearthfires.esm", "dragonborn.esm", "_resourcepack.esl"}
PLUGIN_EXT = (".esp", ".esm", ".esl")
OUTPUT_TOOLS = re.compile(r"\b(dyndolod|texgen|xlodgen|occlusion|pgpatcher|parallaxgen|nemesis|pandora|synthesis|bodyslide)\b.*\boutput\b"
                          r"|\bsynthesis\.esp\b|\bbashed patch\b|\bsmashed patch\b", re.I)
# THE TAXONOMY (the owner, 2026-09-23). Tiers load top to bottom; a main with subs is an EMPTY separator followed by
# "Main - Sub" blocks. The distinctions Nexus lacks are his: new vs edited equipment, environment (textures IN the world,
# split by target) vs models and textures (inventory-scope items, clutter, furniture, interiors), engine fixes vs
# frameworks vs utilities, controls (action) vs interface (visual), camera, dialogue, physics, performance, lighting
# and effects, animation by subject, NPC / creature / player sub-blocks, alchemy / crafting / enchanting as headers.
TAXONOMY = [
    (0, "--- 0 BASE & ENGINE ---", [
        ("Base Game", None), ("Unofficial Patches", None), ("Essential Engine Fixes", None), ("Frameworks", None),
        ("Utilities", None), ("Bug Fixes", None), ("Performance Optimization", None), ("Uncategorised", None)]),
    (1, "--- 1 INTERFACE & INTERACTION ---", [
        ("User Interface", None), ("UI Overhaul", None), ("Improved Controls", None), ("Camera", None),
        ("Dialogue", None), ("Alternate Start", None), ("Save Games", None)]),
    (2, "--- 2 CHARACTERS & ANIMATION ---", [
        ("Physics", None), ("Body", None), ("Face", None), ("Hair", None), ("Races, Classes, and Birthsigns", None),
        ("Animation", ["General", "Player", "NPC", "Enemy", "Creature"])]),
    (3, "--- 3 WORLD, VISUALS & SYSTEMS ---", [
        ("Lighting", None), ("Visual Effects", None), ("Presets - ENB and ReShade", None),
        ("Environment", ["Landscape", "Grass", "Trees", "Plants", "Water", "Weather", "Seasons", "Architecture", "Roads"]),
        ("Models and Textures", ["General", "Items", "Clutter", "Furniture", "Interiors"]),
        ("PBR Textures", None), ("Audio", None),
        ("Gameplay", ["General", "Combat", "Stealth", "Economy"]), ("Immersion", None),
        ("Alchemy", ["Potions", "Ingredients"]), ("Crafting", ["General", "Armour", "Weapons"]),
        ("Enchanting", ["General", "Enchantments"]), ("Overhauls", None), ("Miscellaneous", None)]),
    (4, "--- 4 CONTENT ---", [
        ("Magic - Spells & Enchantments", None), ("Class, Perks, Powers and Blessings", None), ("Shouts", None),
        ("Clothing and Accessories", None), ("New Clothing", None), ("Armour", None), ("New Armour", None),
        ("Armour - Shields", None), ("Weapons", None), ("New Weapons", None), ("Weapons and Armour", None),
        ("New Weapons and Armour", None), ("Shape", None), ("Equipment Positioning", None),
        ("Items and Objects - World", None),
        ("Collectables, Treasure Hunts, and Puzzles", None),
        ("Creatures", ["Appearance", "Behaviour", "Mounts", "Animals", "New Creatures"]),
        ("NPC", ["Appearance", "AI and Behaviour", "Followers", "Other"]), ("Player", ["Appearance", "Other"]),
        ("Quests and Adventures", None), ("Player homes", None), ("Buildings", None),
        ("Location Overhauls", ["City", "Town", "Interior", "General"]), ("Dungeons", None), ("Locations - New", None),
        ("Guilds/Factions", None), ("Cheats and God items", None)]),
    (5, "--- 5 PATCHES ---", [("Patches", None)]),
    (6, "--- 6 TEST BUILDS ---", [("Test Builds", None)]),
    (7, "--- 7 GENERATED OUTPUTS ---", [("Generated Outputs", None)]),
]
LEAVES, MAIN_OF, TIERS, TIER_HEADERS, GROUPS = [], {}, {}, {}, []
for _t, _h, _mains in TAXONOMY:
    _names = []
    for _main, _subs in _mains:
        if _subs:
            for _sub in _subs:
                _leaf = f"{_main} - {_sub}"
                _names.append(_leaf)
                MAIN_OF[_leaf.lower()] = _main
        else:
            _names.append(_main)
    LEAVES.extend(_names)
    TIERS[_t] = tuple(_names)
    TIER_HEADERS[_t] = _h
    GROUPS.append((_h, list(_names)))
OTHER_GROUP_HEADER = "--- OTHER ---"           # an MO2 category of the user's that the tree does not know: tier 3, last
INDEX_TIER = {n.strip().lower(): t for t, names in TIERS.items() for n in names}
FIXED_BLOCKS = ("base game", "unofficial patches", "test builds", "generated outputs", "[nodelete]", "shape")
# a Nexus category's DEFAULT leaf; the signals below refine it (Body -> Face / Hair, Models and Textures -> a sub...)
NEXUS_TO_LEAF = {
    "utilities": "Utilities", "bug fixes": "Bug Fixes", "modders resources": "Utilities", "vr": "Utilities",
    "uncategorised": "Uncategorised", "user interface": "User Interface", "save games": "Save Games",
    "body, face, and hair": "Body", "animation": "Animation - General", "models and textures": "Models and Textures - General",
    "visuals and graphics": "Visual Effects", "environmental": "Environment - Landscape", "audio": "Audio",
    "overhauls": "Overhauls", "gameplay": "Gameplay - General", "immersion": "Immersion", "combat": "Gameplay - Combat",
    "stealth": "Gameplay - Stealth", "skills and leveling": "Class, Perks, Powers and Blessings",
    "magic - gameplay": "Magic - Spells & Enchantments", "alchemy": "Alchemy - Potions", "crafting": "Crafting - General",
    "items and objects - player": "Items and Objects - World", "npc": "NPC - Appearance",
    "followers & companions": "NPC - Followers", "followers & companions - creatures": "NPC - Followers",
    "creatures and mounts": "Creatures - New Creatures",
    "cities, towns, villages, and hamlets": "Location Overhauls - Town", "locations - vanilla": "Location Overhauls - General",
}
CAPITALS = {"Whiterun", "Riften", "Solitude", "Windhelm", "Markarth"}      # a city has a worldspace of its own; the rest are towns
LEAF_TO_NEXUS = {}
for _k, _v in NEXUS_TO_LEAF.items():
    LEAF_TO_NEXUS.setdefault(_v.lower(), _k)
# --- CONFLICT RESOLVER (the owner, 2026-09-23: "refine this plugin to the point that there's no need to have keep
# winners ... and it will still work properly"). Two mods sharing files are ordered by EVIDENCE about the two mods,
# never by where they happen to sit today. Read in this order, first hit decides:
#   1 name dependency  - one mod is named for the other ("Pelt Cloaks for Wet and Cold", "X - Y Patch"): it loads after
#   2 patch            - a [Patch]-tagged or "patch"-named mod loads after the mod it shares files with
#   3 PBR / parallax   - the mod shipping PBR or parallax companions of the shared textures loads after the plain one
#   4 specificity      - a small pack riding on a big one (most of its files are the big one's, the big one is 2x+
#                        larger) loads after it: the specific over the general
# Nothing decided = category order decides, and the pair is listed for review as "no evidence".
_NAME_NOISE = re.compile(r"\[[^\]]*\]|\((main|se|sse|ae)\)|\b(sse|se|ae|special edition|skyrim|for|the|a|an|of|and|v\d+(\.\d+)*)\b|[^a-z0-9]+", re.I)
_PATCH_WORD = re.compile(r"\bpatch(es)?\b|\bpatch collection\b|\bcompatibility\b", re.I)
_PBR_COMPANION = (("_rmaos.dds", "pbr"), ("_p.dds", "parallax"), ("_cnr.dds", "pbr"), ("_f.dds", "pbr"))


def _core_name(name):
    return _NAME_NOISE.sub("", name.lower())


def _is_patch_mod(m):
    """A patch is what the evidence DECIDED (structure: masters from other mods), not a word in the name. Until
    2026-09-23 the tag or the word was enough, and USSEP ('Unofficial ... Patch', Bug Fixes, a master to hundreds) was
    ordered after everything it shares a file with - 80 mods followed it into a 258-mod Patches block."""
    return norm(m.category or "") == norm("Patches")


def _pbr_kind(files, shared):
    """'pbr' or 'parallax' when this mod ships a companion map for a shared texture, else None."""
    fs = files if isinstance(files, set) else set(files)
    for f in shared:
        if not f.endswith(".dds"):
            continue
        stem = f[:-4]
        for suffix, kind in _PBR_COMPANION:
            if stem + suffix in fs:
                return kind
    if any(x.startswith("pbrnifpatcher/") or x.startswith("pbrtexturesets/") for x in fs):
        return "pbr"
    return None


def _is_local_build(m):
    return bool(m.twin) or m.name.lower().startswith(("unpublished ", "test "))


def resolve_conflict(a, b, shared, files_of):
    """(winner, loser, reason) from the evidence, or None. a and b are Mods; shared is the list of files both ship."""
    ca, cb = _core_name(a.name), _core_name(b.name)
    # 0. a local build (unpublished / test) of a mod wins over the third-party mod it forks - the one whose name is
    #    the same mod's ("unpublished Wait Your Turn Redux" over "Wait Your Turn Redux - Enemy Circling Behavior").
    #    Only when the names say they are the same mod: a reskin that merely shares a file with the local build
    #    (Norden UI over Dragon's Eye Minimap) is decided by the ordinary evidence below (2026-09-23)
    la, lb = _is_local_build(a), _is_local_build(b)
    if la != lb:
        local, other = (a, b) if la else (b, a)
        cl, co = (ca, cb) if la else (cb, ca)
        if len(cl) >= 6 and (cl in co or co in cl):
            return local, other, f"local build of the same mod wins over {other.name}"
    if len(cb) >= 6 and cb in ca and ca != cb and not (len(ca) >= 6 and ca in cb):
        return a, b, f"named for {b.name}"
    if len(ca) >= 6 and ca in cb and ca != cb and not (len(cb) >= 6 and cb in ca):
        return b, a, f"named for {a.name}"
    pa, pb = _is_patch_mod(a), _is_patch_mod(b)
    if pa != pb:
        return (a, b, f"a patch loads after {b.name}") if pa else (b, a, f"a patch loads after {a.name}")
    ka, kb = _pbr_kind(files_of[a.name], shared), _pbr_kind(files_of[b.name], shared)
    if ka and not kb:
        return a, b, f"ships {ka} companions of the shared textures; {b.name} does not"
    if kb and not ka:
        return b, a, f"ships {kb} companions of the shared textures; {a.name} does not"
    na, nb = len(files_of[a.name]), len(files_of[b.name])
    small, big = (a, b) if na <= nb else (b, a)
    ns, nbg = min(na, nb), max(na, nb)
    if ns and len(shared) >= 0.5 * ns and nbg >= 2 * ns:
        return small, big, f"specific over general: {len(shared)} of its {ns} files are also in {big.name} ({nbg} files)"
    return None


# SHAPE (the owner, 2026-09-23: "recognise mods that have only shape data or keywords like himbo, cbbe, unp, 3ba and
# other bodyslide related words to go in the shape separator which should override armor and clothes"). A BodySlide
# refit or conversion - shape data alone (CalienteTools\BodySlide), or a body's name in the mod's name - goes to the
# Shape block, which sits after Armour, Weapons and Clothing in tier 4 and loads after every equipment mod it shares
# a file with. The bodies themselves (Nexus: Body, Face, and Hair) stay bodies unless they are a refit by name.
SHAPE_CAT = "Shape"
SHAPE_WORDS = re.compile(r"\b(himbo|cbbe|unp|uunp|bhunp|3ba|3bbb|tbd|bodyslides?|body slides?|outfit studio|refits?|conversions?)\b", re.I)
SHAPE_REFIT_WORDS = re.compile(r"\b(bodyslides?|body slides?|outfit studio|refits?|conversions?)\b", re.I)
EQUIPMENT_CATS = {"armour", "armour - shields", "weapons", "weapons and armour", "clothing and accessories",
                  "new armour", "new weapons", "new weapons and armour", "new clothing"}


def shape_reason(m, nexus_cat):
    """Why this mod is a Shape mod, or None."""
    files = m.files or []
    shape_only = bool(files) and all(f.startswith("calientetools/") for f in files)
    if shape_only:
        return "ships shape data only (CalienteTools/BodySlide)"
    if SHAPE_WORDS.search(m.name):
        if norm(nexus_cat or "") == norm("Body, Face, and Hair") and not SHAPE_REFIT_WORDS.search(m.name):
            return None                       # the body itself, not a refit of something to it
        return f"a body's name in the mod's name ({SHAPE_WORDS.search(m.name).group(0)})"
    return None


def index_tier(category, mod=None):
    """The tier of a category; an unknown category is tier 3 (the middle) and says so in the report. (The replacer
    demotion that used to live here - a content label with only meshes/textures ranked as tier 3 while keeping its
    label - is now a category decision in the evidence model, rule R4, so a replacer IS Models and Textures.)"""
    k = re.sub(r"\s+", " ", category or "").strip().lower()
    if k == NODELETE_SEP.lower():
        return 8
    if k == SHAPE_CAT.lower():
        return 4                                  # a refit stays with the equipment it refits, plugin or not
    return INDEX_TIER.get(k, 3)


# --- COMMUNITY VERDICTS (the owner, 2026-09-23: a "send rules" feature - users share the verdicts they hold for mods we
# do not have, and the classifier's weighting learns from them; his own copy carries the receiving end). Rule 67: a
# verdict is scoring material, never an exception - it enters as ONE MORE VOTE SOURCE, weighted by how many users
# agree, and the Placement tab shows it beside the others. What leaves a user's machine is exactly DISCLOSURE below.
VERDICTS_REPO = "ApocryphaRealm/MO2ModlistManager"
VERDICTS_LABEL = "verdicts"
VERDICTS_ISSUES_API = f"https://api.github.com/repos/{VERDICTS_REPO}/issues"
VERDICTS_ISSUE_NEW = f"https://github.com/{VERDICTS_REPO}/issues/new"
VERDICTS_FILE = "community-verdicts.json"        # the pooled counts the owner's copy reads: {core name: {leaf: users}}
VERDICTS_INBOX = "community-inbox"               # a folder of dropped-in payload files, read by the fetch as well
W_COMMUNITY_EACH, W_COMMUNITY_CAP = 1.0, 3.0     # one user is a hint, three agreeing users weigh like a strong record vote
DISCLOSURE = ("Share verdicts sends this and nothing else: for each mod whose MO2 category you set yourself and the "
              "evidence alone would have placed elsewhere - the mod's name, its Nexus id, the category you chose, the "
              "category the evidence chose with its top votes, and a coarse summary of that evidence (how many plugins, "
              "whether it ships a DLL or animations, how many files, which record kinds). No file paths, no user names, "
              "no machine or account identity. It is off unless you turn it on, and you see every row before it goes. "
              "Without a drop-box address in the plugin settings it opens a GitHub issue in your browser, prefilled, "
              "for you to post yourself.")
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
    """The tier of a category (its place in TAXONOMY); an unknown one is tier 3."""
    k = norm(category)
    if k == NODELETE_SEP.lower():
        return len(GROUPS) + 1
    return INDEX_TIER.get(k, 3)


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


# WHAT A PLUGIN ADDS (the owner, 2026-09-23: "if it only has magic spells or only enchantments then it goes to magic
# spells and enchantments but if it has armor and weapons with enchantments then it goes to the right separator ...
# it alters some vanilla records and adds new weapons and enchantments so it goes in new weapons and armor"). The
# top-level record groups of a plugin say what it adds; a record whose form ID belongs to the plugin itself is new,
# one that belongs to a master is an override. Only these groups are read, the rest are skipped by their size.
RECORD_GROUPS = (b"ARMO", b"WEAP", b"AMMO", b"SPEL", b"ENCH", b"MGEF", b"SCRL",
                 # widened 2026-09-23 for the evidence model: what a plugin adds or alters says what the mod is about
                 b"NPC_", b"RACE", b"HDPT", b"QUST", b"DIAL", b"BOOK", b"MISC", b"INGR", b"ALCH", b"KEYM", b"SLGM", b"PERK",
                 b"AVIF", b"SHOU", b"WOOP", b"LSCR", b"STAT", b"ACTI", b"FURN", b"CONT", b"LVLI", b"LVLN", b"ARMA", b"TXST",
                 b"WTHR", b"CLMT", b"LGTM", b"IMGS", b"MUSC", b"SNDR", b"SOUN", b"GLOB", b"GMST", b"LCTN", b"FLST", b"MESG",
                 b"IDLE", b"REGN", b"TREE", b"FLOR", b"GRAS", b"LIGH", b"MSTT", b"DOOR", b"PROJ", b"EXPL", b"SPGD", b"HAZD")
FOOTPRINT_GROUPS = (b"CELL", b"WRLD")          # nested groups: only their byte size is read ("CELL~", "WRLD~")


def plugin_new_records(path, n_masters):
    """{type: count of NEW records} over RECORD_GROUPS; {} when unreadable."""
    out = {}
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
            if len(head) < 24 or head[:4] != b"TES4":
                return out
            fh.seek(24 + struct.unpack("<I", head[4:8])[0])
            while True:
                gh = fh.read(24)
                if len(gh) < 24 or gh[:4] != b"GRUP":
                    break
                gsize, label, gtype = struct.unpack("<I", gh[4:8])[0], gh[8:12], struct.unpack("<i", gh[12:16])[0]
                if gtype == 0 and label in FOOTPRINT_GROUPS:
                    k = label.decode("ascii", "replace") + "~"
                    out[k] = out.get(k, 0) + max(0, gsize - 24)
                    fh.seek(gsize - 24, 1)
                    continue
                if gtype != 0 or label not in RECORD_GROUPS:
                    fh.seek(gsize - 24, 1)
                    continue
                end = fh.tell() + gsize - 24
                while fh.tell() < end:
                    rh = fh.read(24)
                    if len(rh) < 24:
                        break
                    sig, dsize, form = rh[:4], struct.unpack("<I", rh[4:8])[0], struct.unpack("<I", rh[12:16])[0]
                    if sig == b"GRUP":                    # a nested group: skip whole
                        fh.seek(dsize - 24, 1)
                        continue
                    key = sig.decode("ascii", "replace") + ("" if (form >> 24) >= n_masters else "*")   # "ARMO" new, "ARMO*" override
                    out[key] = out.get(key, 0) + 1
                    fh.seek(dsize, 1)
                fh.seek(end)
    except (OSError, struct.error):
        return out
    return out


# (refine_by_records and its EQUIPMENT_FAMILY table were folded into the evidence model's _records_vote, 2026-09-23)


# --- THE EVIDENCE MODEL (the owner, 2026-09-23) ---------------------------------------------------------------------
# Every signal about a mod becomes a VOTE (source, category, weight, reason); the rules below adjust the votes; the
# category with the most weight wins and the dialog shows every vote. Sources: the Nexus category, an MO2 category the
# user set himself, the TES4 record groups the plugins add or alter, what the folder ships, the words the mod uses
# about itself (its name, plugin descriptions, readme, FOMOD info, the Nexus description MO2 cached), the [Patch] tag
# and the structure of its masters. Nothing here is a mode: a new signal is a new source of votes, a new placement is a
# rule over the votes.
W_NEXUS, W_MO2_USER, W_RECORDS_STRONG, W_RECORDS_WEAK, W_FILES, W_TAG = 3.0, 3.5, 3.5, 1.2, 1.5, 1.0
W_NAME_DEFINED = 6.0     # a leaf the owner defined by its name, hit in the mod's NAME: decisive over a label plus its files
NAME_DEFINED = {"camera", "dialogue", "improved controls", "physics", "performance optimization", "alternate start", "face", "hair",
                "pbr textures", "environment - seasons", "lighting", "unofficial patches", "ui overhaul",
                "essential engine fixes", "frameworks", "models and textures - interiors", "models and textures - clutter",
                "models and textures - furniture", "environment - architecture", "player homes", "gameplay - general", "utilities",
                "equipment positioning"}
TIER0 = {norm(c) for c in TIERS[0]}            # the leaves a mod's own documents may not vote for: a readme names its requirements
TARGET_IN_SUBJECT = {"equipment positioning"}  # a "for X" subject naming these is what the mod targets (an IED add-on), not what it is
TEXT_NAME_HIT, TEXT_DOC_HIT, TEXT_CAP = 1.0, 0.4, 2.5

# (pattern, leaf, weight multiplier) - the words a mod uses about itself. A multiplier of DEFINITIVE (3.6) means one hit
# in the NAME outweighs a Nexus label on its own: those are the words the owner named as decisive (camera, dialogue,
# physics, performance, controls, alternate start, lighting, seasons, pbr, snazzy...). Tune here.
DEFINITIVE = 3.6
TEXT_SIGNALS = [(re.compile(p, re.I), c, w) for p, c, w in (
    # tier 0
    # "skse" is not an engine fix (every DLL mod says it) and Skyrim Priority is a performance mod (the owner, 2026-09-23)
    (r"\b(address library|engine fixes|ssedisplaytweaks|display tweaks|crash logger|backported extended esl|bees|sse fixes|scrambled bugs|net script framework|preloader)\b", "Essential Engine Fixes", DEFINITIVE),
    (r"\b(mcm helper|skyui|papyrusutil|papyrus extender|powerofthree|po3|base object swapper|spell perk item distributor|spid|keyword item distributor|kid|open animation replacer|oar|dynamic animation replacer|dar|jcontainers|consoleutil|community shaders|dynamic string distributor|sound record distributor|payload interpreter|racemenu|nemesis|pandora|xpmsse|xp32|uiextensions|behavior data injector|scaleform translation|inventory injector|framework|distributor|injector|extender|loader|kiloader|runtime|sdk|api|hooks?)\b", "Frameworks", DEFINITIVE),
    (r"\b(texture set|assets? pack|tools?|utilit(y|ies)|generator|xedit|lodgen|texgen|dyndolod resources)\b", "Utilities", 1.0),
    (r"\b(resources?|modder'?s? resources?|library|tool ?kit|sdk)\b", "Utilities", 2.0),
    # a utility does nothing by itself; other mods use it (the owner, 2026-09-23: Animation Motion Revolution, dTry's Key Utils)
    (r"\b(animation motion revolution|amr|key ?utils?|utils?)\b", "Utilities", DEFINITIVE),
    (r"\b(fix(es|ed|er)?|bug ?fix(es|er)?|corrections?|navmesh|hotfix)\b", "Bug Fixes", 1.0),
    (r"\b(efps|optimi[sz](ation|ed|er)|performance|insignificant object remover|lightened skyrim|occlusion|fps|shadow boost|object remover|culling|skyrim priority|cpu)\b", "Performance Optimization", DEFINITIVE),
    # speed words: faster loading, lookups, copies, profiling (the owner, 2026-09-23: the Faster * mods and Load Time Profiler) - strong,
    # not decisive: "Faster HDT-SMP" is about SMP
    (r"\b(load ?times?|loadscreens?|loading (times?|screens?)|profilers?|cell lookups?|decompression|file copy|game start|ini file cacher)\b", "Performance Optimization", 2.0),
    (r"\b(unofficial .*patch|ussep|usmp)\b", "Unofficial Patches", DEFINITIVE),
    # tier 1
    (r"\b(ui|hud|menus?|interface|widgets?|fonts?|map markers?|compass|minimap|mcm|cursor|loading screens?|main menu|bestiary|character menu|follower stats|stats? menu|journal|inventory ?(menu|ui)|icons?|paper maps?|world map|fwmf|flat world map)\b", "User Interface", 1.0),
    (r"\b(ui overhaul|nordic ui|untarnished ui|norden ui|dear diary|edge ui|skyhud|interface overhaul|reskin|smooth ui|dragonbreaker|dwemer ui)\b", "UI Overhaul", DEFINITIVE),
    # "Mod Control Panel" is SKSE Menu Framework's menu name, not a controls word; keyboard and window handling is controls
    # (the owner, 2026-09-23: Kill Caps Lock, Better AltTab)
    (r"\b(read or take|better grabbing|btps|better third person selection|step up|quick ?loot|(?<!mod )controls?(?! panel)|controller|gamepad|hotkeys?|keybinds?|keybinding|grab|activate|activation|interaction|pick ?up|take all|jump|sprint|whistle|auto ?(equip|unequip|loot|sort)|unbind|bindings?|wheeler|wheel menu|back pocket|item explorer)\b", "Improved Controls", DEFINITIVE),
    (r"\b(caps ?lock|alt ?-?tab|keyboard|mouse)\b", "Improved Controls", 1.5),
    (r"\b(cam|camera|cameras|smoothcam|fov|field of view|headtracking|head tracking)\b", "Camera", DEFINITIVE),
    (r"\b(dialogue|dialog|persuasion|conversations?|talk|speech|voice ?lines?|subtitles?)\b", "Dialogue", DEFINITIVE),
    (r"\b(alternate start|alternate perspective|realm of lorkhan|live another life|skyrim unbound|new game start|character creation start)\b", "Alternate Start", DEFINITIVE),
    (r"\b(saves?|autosaves?|save ?games?|save system)\b", "Save Games", 1.0),
    # tier 2
    (r"\b(smp|hdt|cbpc|fsmp|physics|collision|jiggle|bounce|cloth physics)\b", "Physics", DEFINITIVE),
    (r"\b(bod(y|ies)|skins?|cbbe|himbo|unp|3ba|bhunp|tbd|muscle|nipple|feet|hands|complexion|bodypaint|tattoos?|texture ?set)\b", "Body", 1.0),
    # which body each actor gets - morphs and presets handed out (the owner, 2026-09-23: OBody is body)
    (r"\b(obody|autobody|body ?morphs?|body ?presets?|bodyslide presets?|body types?|body distribution)\b", "Body", DEFINITIVE),
    (r"\b(faces?|heads?|eyes?|brows?|eyebrows?|teeth|mouth|freckles?|scars?|warpaints?|makeup|blush(ing)?|tint|high poly head|expressions?|lips|complexions?|overlays?|tattoos?|bodypaints?|facegen|horns?)\b", "Face", DEFINITIVE),
    (r"\b(hairs?|hairdos?|hairstyles?|beards?|khisart[ai]n|stubble|ks hairdos|apachii|salt and wind|hairline)\b", "Hair", DEFINITIVE),
    (r"\b(races?|khajiit|argonians?|orcs?|orsimer|dunmer|altmer|bosmer|nords?|imperials?|bretons?|redguards?|birthsigns?|racial)\b", "Races, Classes, and Birthsigns", 1.0),
    (r"\b(animations?|animated|idles?|mco|bfco|skysa|adxp|locomotion|movement|dodge|tk dodge|true directional|tdm|diving|dive|swim|sprint animation|attack animations?|combos?)\b", "Animation - General", 1.0),
    (r"\b(player animations?|first person animations?|pca)\b", "Animation - Player", 2.0),
    (r"\b(npc animations?|idle animations?|gesture|conversation animations?|citizen animations?)\b", "Animation - NPC", 2.0),
    (r"\b(enemy animations?|bandit animations?|draugr animations?|boss animations?)\b", "Animation - Enemy", 2.0),
    (r"\b(creature animations?|animal animations?|horse animations?|dragon animations?|wolf animations?|bear animations?)\b", "Animation - Creature", 2.0),
    # tier 3
    (r"\b(lights?|lighting|lux|elfx|luminosity|window shadows|torch(es)?|lanterns?|candles?|illumination|shadows?|relighting|enb light)\b", "Lighting", DEFINITIVE),
    (r"\b(effects?|vfx|fx|particles?|blood|fire|smoke|spell effects?|impacts?|embers|lens|flares?|glow|magic effects?|mist|fog|explosions?|footprints|splash(es)?|sparks)\b", "Visual Effects", 1.5),
    (r"\b(enb|reshade)\b", "Presets - ENB and ReShade", 1.5),
    (r"\b(landscapes?|terrain|ground|rocks?|mountains?|cliffs?|dirt|complex parallax|parallax|tundra|mud|gravel|stones?)\b", "Environment - Landscape", 1.0),
    (r"\b(grass|grasses|folkvangr|veydosebrom|cathedral grass|landscape fixes for grass)\b", "Environment - Grass", 2.0),
    (r"\b(trees?|forests?|pines?|aspens?|birch(es)?|bark|happy little trees|nature of the wild lands|dead trees)\b", "Environment - Trees", 2.0),
    (r"\b(plants?|flora|flowers?|mushrooms?|shrubs?|bush(es)?|ferns?|ivy|moss|lichen|nirnroot|saplings?|blooms?|thickets?)\b", "Environment - Plants", 2.0),
    (r"\b(water|rivers?|waterfalls?|ocean|lakes?|realistic water|water for enb|shores?|foam|puddles)\b", "Environment - Water", 2.0),
    (r"\b(weathers?|sky|skies|clouds?|aurora|storms?|rain|climate|obsidian|cathedral weathers|azurite|nat|vivid weathers|wind)\b", "Environment - Weather", 2.0),
    (r"\b(seasons?|seasonal|turn of the seasons|winter|summer|autumn|spring|snowy)\b", "Environment - Seasons", DEFINITIVE),
    (r"\b(architecture|farmhouses?|chimneys?|exteriors?|rooftops|thatch|stonework|windmills?)\b", "Environment - Architecture", DEFINITIVE),
    (r"\b(roofs?|brick|city walls|fences?|docks|bridges?|wells?|signs?|signposts?|market stalls?)\b", "Environment - Architecture", 1.5),
    (r"\b(roads?|northern roads|pathways?|cobblestone|trails?|paths?)\b", "Environment - Roads", 2.0),
    (r"\b(re-?textures?|textures?|[1248]k|meshes?|hd|uhd|remesh|remodel|models?|retex)\b", "Models and Textures - General", 1.0),
    (r"\b(items?|potions? (models?|meshes|textures)|food|ingots?|gems?|soul ?gems?|scrolls? (models?|textures)|books? (models?|textures|covers?)|coins?|septims?|gold|weapon (models?|meshes)|armou?r (models?|meshes))\b", "Models and Textures - Items", 1.0),
    (r"\b(clutter|knapsacks?|sacks?|barrels?|crates?|baskets?|pottery|tankards?|junk|hay|firewood|buckets?|coins? of interesting nature)\b", "Models and Textures - Clutter", DEFINITIVE),
    (r"\b(bottles?|cups?|plates?|ropes?|jars?|bowls?|goblets?|candlesticks?|lamps?)\b", "Models and Textures - Clutter", 1.5),
    (r"\b(furniture|thrones?|chairs?|beds?|bench(es)?|shel(f|ves)|cabinets?|dressers?|wardrobes?|nightstands?|stools?)\b", "Models and Textures - Furniture", DEFINITIVE),
    (r"\b(tables?|desks?|counters?|bookcases?)\b", "Models and Textures - Furniture", 1.5),
    (r"\b(interiors?|snazzy|inn interiors?|tavern|shop|trader|store|rooms?|indoors?)\b", "Models and Textures - Interiors", DEFINITIVE),
    (r"\b(pbr|rmaos|parallax ?gen|pgpatcher|complex material)\b", "PBR Textures", DEFINITIVE),
    (r"\b(sounds?|audio|music|voices?|voiced|soundtrack|ambience|footsteps?|sfx)\b", "Audio", 1.0),
    # durability and degradation are a system over gear, not the gear (the owner, 2026-09-23: Simple Degradation)
    (r"\b(gameplay|mechanics?|balance|difficulty|encounters?|survival|needs|hunger|thirst|frostfall|camping|campfire|durability|degrad(e|es|ation))\b", "Gameplay - General", 1.0),
    # a rule about what the player may do (the owner, 2026-09-23: Item Equip Restrictor is gameplay)
    (r"\b(restrict(s|ion|ions|or|ors|ed)?)\b", "Gameplay - General", 2.0),
    (r"\bpress \w+ to\b", "Gameplay - General", DEFINITIVE),
    (r"\b(combat|parry|block(ing)?|stagger|killmoves?|poise|stamina ?regen|hit ?stop|melee|archery|damage|localized damage|localised damage|resistances?|weakness(es)?|armou?r rating|enemies|enemy)\b", "Gameplay - Combat", 1.5),
    (r"\b(stealth|sneak(ing)?|thie(f|ves)|pickpocket(ing)?|lockpick(ing)?|detection)\b", "Gameplay - Stealth", 1.5),
    (r"\b(economy|trade|trading|merchants?|prices?|barter|gold sink|taxes?)\b", "Gameplay - Economy", 1.5),
    (r"\b(immersive|immersion|realistic|wearable|bathing|sleep|eating|drinking|carry weight|carryweight|weight)\b", "Immersion", 1.0),
    (r"\b(alchemy|potions?|poisons?|apothecary|brewing)\b", "Alchemy - Potions", 1.5),
    (r"\b(ingredients?|reagents?|herbs?|harvest(ing)?)\b", "Alchemy - Ingredients", 1.5),
    (r"\b(craft(ing)?|smithing|forge|tanning|cooking|recipes?|tempering|workbench|blacksmith)\b", "Crafting - General", 1.5),
    (r"\b(enchant(ing|ments?|ed)?|disenchant|enchanter)\b", "Enchanting - Enchantments", 1.5),
    (r"\b(overhaul(s|ed)?|rework(ed)?|redone|remastered|revamp(ed)?)\b", "Overhauls", 0.5),
    # tier 4
    (r"\b(spells?|magic|magicka|scrolls?|wards?|destruction|conjuration|illusion|restoration|alteration|summon(s|ing)?|rituals?|tomes?|staff|staves|mysticism|apocalypse|odin|arcanum)\b", "Magic - Spells & Enchantments", 1.0),
    (r"\b(perks?|classes?|standing stones?|blessings?|powers?|shrine blessings?|ordinator|adamant|vokrii|apprentice|mannaz|aetherius|andromeda|paragon|custom skills?|skill trees?|skills?|level(l)?ing|experience|xp|attributes?)\b", "Class, Perks, Powers and Blessings", 1.5),
    (r"\b(shouts?|thu'?um|word walls?|dragon ?souls?)\b", "Shouts", 1.5),
    (r"\b(clothing|clothes|outfits?|dress(es)?|robes?|cloaks?|capes?|jewell?ery|amulets?|rings?|necklaces?|circlets?|earrings?|glasses|hoods?|scarf|scarves)\b", "Clothing and Accessories", 1.0),
    (r"\b(armou?rs?|cuirass|helmets?|boots|gauntlets|greaves|pauldrons|plate|mail)\b", "Armour", 1.0),
    (r"\b(shields?|bucklers?)\b", "Armour - Shields", 1.0),
    (r"\b(swords?|weapons?|weaponry|bows?|daggers?|axes?|maces?|greatswords?|warhammers?|blades?|arrows?|bolts?|crossbows?|spears?|katanas?|halberds?)\b", "Weapons", 1.0),
    (r"\b(shape data|bodyslide|outfit studio|refits?|conversions?)\b", SHAPE_CAT, 1.5),
    # where worn and carried gear sits on the body - sheaths, back shields, equipment displays (the owner, 2026-09-23:
    # Simple Dual Sheath and Immersive Equipment Displays go to an Equipment Positioning separator)
    (r"\b(dual sheathe?|equipment displays?|immersive equipment displays|ied|all geared up|equipment positioning|shields? on (the )?back|weapons? on (the )?back|back shields?|sheathe? positions?|holsters?)\b", "Equipment Positioning", DEFINITIVE),
    (r"\b(objects?|misc|containers?|chests?|displays?|book ?shel(f|ves)|lootable|placed items?)\b", "Items and Objects - World", 0.8),
    (r"\b(collectables?|collectibles?|treasure|treasure hunts?|puzzles?|collectables helper)\b", "Collectables, Treasure Hunts, and Puzzles", 1.5),
    (r"\b(creatures?|animals?|beasts?|mihail|spiders?|trolls?|giants?|draugr|falmer|dwarven automatons?|monsters?|wildlife|deer|elk|rabbits?|foxes|chickens?|hawks?|birds?|fish)\b", "Creatures - New Creatures", 1.0),
    # animals named (the owner, 2026-09-23: Dire Wolves is creatures) - plural or "dire"/"sabre" forms, so a "Wolf Armor"
    # is not an animal mod
    (r"\b(wolves|dire wol(f|ves)|bears|sabre ?cats?|saber ?cats?|mammoths?|horkers?|skeevers?|mudcrabs?|chaurus|boars?|wolf packs?|prehistoric|dinosaurs?|megafauna)\b", "Creatures - New Creatures", 2.0),
    (r"\b(creature (re)?textures?|animal (re)?textures?|dragon (re)?textures?|wolf (re)?textures?|bear (re)?textures?|hd creatures|bellyaches)\b", "Creatures - Appearance", 2.0),
    (r"\b(creature (ai|behaviou?r)|animal (ai|behaviou?r)|predators?|prey|animal aggression)\b", "Creatures - Behaviour", 2.0),
    (r"\b(horses?|mounts?|mounted|riding|steeds?|saddles?|convenient horses|horse power|immersive horses)\b", "Creatures - Mounts", 2.0),
    (r"\b(npcs?|citizens|villagers|guards|jarls?|children|overhauled npcs|character overhaul)\b", "NPC - Appearance", 1.0),
    (r"\b(bijin|pandorable|high poly npcs?|npc (overhaul|replacer|faces)|facegen|rs children|the ordinary women|males of skyrim|beards of power|npc hair)\b", "NPC - Appearance", 2.0),
    # "behaviour" in words is AI behaviour; animation behaviours are the .hkx files under behaviors/ (a path vote). How
    # attackers move in combat is NPC behaviour (the owner, 2026-09-23: Wait Your Turn)
    (r"\b(ai overhaul|ai|behaviou?rs?|behaviou?r edits?|routines?|schedules?|sandbox(ing)?|pathing|combat ai|smart npcs?|reactions?|immersive citizens|npc (ai|behaviou?r)|take cover|circl(e|ing)|attackers?|surround(ing)?|flank(ing)?|take turns|wait your turn)\b", "NPC - AI and Behaviour", 2.0),
    # a living world's AI named as such (the owner, 2026-09-23: Vivid Routines - Lightweight Living AI is NPC AI)
    (r"\b(living ai|npc routines?|daily routines?|vivid routines|lifelike npcs?|living world)\b", "NPC - AI and Behaviour", DEFINITIVE),
    (r"\b(followers?|companions?|hirelings?|inigo|lucien|serana|nether'?s follower|ufo|eff|aft|nff|follower framework)\b", "NPC - Followers", 2.0),
    # gathering the NPCs the player has chosen: marking, summoning, recalling friends is follower management (the owner,
    # 2026-09-23: Mark and Summon NPC Friends)
    (r"\b(npc friends|(summon|recall|teleport|gather) (your )?(friends|followers|allies|companions)|allies)\b", "NPC - Followers", DEFINITIVE),
    (r"\b(player (appearance|preset|character)|racemenu presets?|character presets?|my character)\b", "Player - Appearance", 2.0),
    (r"\b(quests?|questing|adventures?|questline|storyline|campaign|quest tracking|quest tracker)\b", "Quests and Adventures", 1.2),
    # a quest's own items: a mod about what the player may do with them is about the quest (the owner, 2026-09-23: Sell
    # Unusual Gems lets you sell a quest item)
    (r"\b(quest items?|unusual gems?|stones of barenziah|crown of barenziah)\b", "Quests and Adventures", 2.0),
    (r"\b(player ?homes?|homes?|houses?|manor|cabin|estate|abode|hideout|residence|cottage|lodge|sanctuary)\b", "Player homes", 1.5),
    (r"\b(vlindrel hall|breezehome|hjerim|honeyside|proudspire|lakeview|windstad|heljarchen|severin manor|myrwatch|tundra homestead|hendraheim|goldenhills)\b", "Player homes", DEFINITIVE),
    (r"\b(inns?|taverns?|temples?|shrines?|farms?|mills?|lighthouses?|forts?|castles?|palaces?|keeps?|stables?|jails?|prisons?|towers?|chapels?|halls?|guildhalls?)\b", "Buildings", 1.0),
    (r"\b(cit(y|ies)|whiterun|riften|solitude|windhelm|markarth|falkreath|dawnstar|morthal|winterhold|raven rock)\b", "Location Overhauls - City", 1.0),
    (r"\b(towns?|villages?|hamlets?|settlements?|riverwood|rorikstead|ivarstead|shor'?s stone|kynesgrove|dragon bridge|karthwasten|helgen|skaal|stonehills|darkwater|half-?moon mill|old hroldan|anga'?s mill|mixwater mill)\b", "Location Overhauls - Town", 1.0),
    (r"\b(dungeons?|caves?|ruins?|tombs?|barrows?|crypts?|mines?|nordic ruins?|dwemer ruins?|delves?)\b", "Dungeons", 1.0),
    (r"\b(worldspace|new lands?|island|province|beyond skyrim|bruma|wyrmstooth|falskaar|expansion)\b", "Locations - New", 1.2),
    (r"\b(vanilla locations?|location overhauls?|landmarks?|points? of interest|poi|environs|lost places)\b", "Location Overhauls - General", 1.0),
    (r"\b(guilds?|factions?|thieves guild|dark brotherhood|college of winterhold|bards? college|dawnguard|stormcloaks?|imperial legion|civil war|companions guild)\b", "Guilds/Factions", 1.0),
    (r"\b(cheats?|god ?(mode|items?)|infinite|unlimited|op)\b", "Cheats and God items", 1.0),
    (r"\b(patch(es|ed)?|compatibility|synergy|consistency)\b", "Patches", 1.0),
)]

# ASSET PATHS (the owner: "what the mod contains"). A path class votes for a leaf in proportion to its share of the
# mod's files: for a mod with no plugin that decides the sub-block (environment vs inventory scope, hair vs face vs
# body, creature appearance); a plugin mod's paths count half.
PATH_SIGNALS = [(re.compile(p), c) for p, c in (
    (r"(^|/)textures/pbr/|_rmaos\.dds$|_cnr\.dds$", "PBR Textures"),
    (r"(^|/)terrain/[^/]+/[a-z0-9_]+\.dds$", "User Interface"),
    (r"(^|/)(landscape|terrain)/(?!(grass|trees|plants))", "Environment - Landscape"),
    (r"(^|/)landscape/grass/|(^|/)grass/", "Environment - Grass"),
    (r"(^|/)landscape/trees/|(^|/)trees/|treepine|treeaspen|treereach|treesnow", "Environment - Trees"),
    (r"(^|/)landscape/plants/|(^|/)plants/|(^|/)flora/|mushroom|flower", "Environment - Plants"),
    (r"(^|/)water/|waterfall|/water[a-z]*\.(nif|dds)$", "Environment - Water"),
    (r"(^|/)sky/|(^|/)clouds?/|weather", "Environment - Weather"),
    (r"(^|/)architecture/", "Environment - Architecture"),
    (r"(^|/)roads?/|/road[a-z]*\.(nif|dds)$", "Environment - Roads"),
    (r"(^|/)clutter/", "Models and Textures - Clutter"),
    (r"(^|/)furniture/", "Models and Textures - Furniture"),
    (r"(^|/)(armor|weapons|clothes)/", "__equipment__"),
    (r"(^|/)hair/|(^|/)hairline|(^|/)beards?/|/hair[a-z0-9_]*\.(nif|dds|tri)$", "Hair"),
    (r"(^|/)(eyes|brows|eyebrows|teeth|mouth|facegendata|facetint|face|tintmasks|makeup|warpaint|overlays)/|/(eye|brow|teeth|mouth|face|head|tint)[a-z0-9_]*\.(nif|dds|tri)$", "Face"),
    (r"(^|/)actors/character/(female|male|character assets)/|(^|/)actors/character/.*(body|skin|hands|feet)", "Body"),
    (r"(^|/)actors/character/(eyes|brows|teeth|mouth|facegendata|facetint|face)", "Face"),
    (r"(^|/)actors/character/(animations|behaviors)/", "Animation - General"),
    (r"(^|/)actors/(?!character/)[^/]+/(animations|behaviors)/", "Animation - Creature"),
    (r"(^|/)actors/(?!character/)[^/]+/", "Creatures - Appearance"),
    (r"(^|/)(effects|fx|particles|magic)/", "Visual Effects"),
    (r"(^|/)lights?/|(^|/)lighting/", "Lighting"),
    (r"^interface/|(^|/)(fwmf|maps?)/|paper ?map|worldmap", "User Interface"),
    (r"^(sound|music)/", "Audio"),
    (r"^seq/", "Quests and Adventures"),
    (r"^calientetools/", SHAPE_CAT),
    (r"^(shadersfx|shaders)/", "Visual Effects"),
    (r"(^|/)dungeons/|(^|/)dwemer/|(^|/)imperial/interior", "Dungeons"),
)]

# which record groups a leaf's own label predicts; a plugin-bearing mod whose plugins hold NONE of them contradicts
# its label (Campfire: Nexus says NPC, its ESM has no NPC_ record at all)
LABEL_RECORDS = {
    "npc - appearance": ("NPC_",), "npc - ai and behaviour": ("NPC_", "PACK", "FLST"), "npc - followers": ("NPC_",),
    "creatures - new creatures": ("NPC_", "RACE"), "creatures - mounts": ("NPC_", "RACE"),
    "weapons": ("WEAP", "AMMO"), "new weapons": ("WEAP", "AMMO"), "armour": ("ARMO",), "new armour": ("ARMO",),
    "armour - shields": ("ARMO",), "clothing and accessories": ("ARMO",), "new clothing": ("ARMO",),
    "weapons and armour": ("ARMO", "WEAP", "AMMO"), "new weapons and armour": ("ARMO", "WEAP", "AMMO"),
    "magic - spells & enchantments": ("SPEL", "ENCH", "MGEF", "SCRL"), "shouts": ("SHOU", "WOOP"),
    "quests and adventures": ("QUST",), "races, classes, and birthsigns": ("RACE", "HDPT"),
    "class, perks, powers and blessings": ("PERK", "AVIF", "SPEL"),
}
ART_EXTS = {".nif", ".dds", ".tri", ".bsa", ".txt", ".ini", ".json", ".png", ".jpg", ".xml"}
CONTENT_TIER4 = {norm(c) for c in TIERS[4]} - {norm(SHAPE_CAT)}
NEW_OF = {"armour": "New Armour", "weapons": "New Weapons", "weapons and armour": "New Weapons and Armour",
          "clothing and accessories": "New Clothing"}
EDIT_OF = {v.lower(): k for k, v in NEW_OF.items()}
_CANON = {}


def canonical(cat):
    """The table's spelling of a category (Nexus writes 'Locations -  New' with two spaces)."""
    if not cat:
        return cat
    if not _CANON:
        for n in LEAVES:
            _CANON[norm(n)] = n
    return _CANON.get(norm(cat), re.sub(r"\s+", " ", cat).strip())


def leaf_for(cat):
    """A Nexus (or MO2) category name -> the leaf of the tree it defaults to."""
    k = norm(cat or "")
    if not k:
        return ""
    if k in NEXUS_TO_LEAF:
        return NEXUS_TO_LEAF[k]
    return canonical(cat)


def _records_vote(m):
    """(category, weight, reason) from what the plugins add or alter, or None. The equipment/magic thresholds are the
    owner's rules of 2026-09-23 (refine_by_records kept them); the other groups were added with the evidence model."""
    r = m.records
    if not r:
        return None
    new = lambda *ks: sum(r.get(k, 0) for k in ks)
    alt = lambda *ks: sum(r.get(k + "*", 0) for k in ks)
    armo_new, weap_new = new("ARMO"), new("WEAP", "AMMO")
    armo_alt, weap_alt = alt("ARMO"), alt("WEAP", "AMMO")
    alt_total = armo_alt + weap_alt
    alt_scale = min(1.0, 100.0 / alt_total) if alt_total else 0.0
    armo, weap = armo_new + int(armo_alt * alt_scale), weap_new + int(weap_alt * alt_scale)
    magic = new("SPEL", "ENCH", "MGEF", "SCRL")
    shouts = new("SHOU", "WOOP")
    npc, race, perk, qust = new("NPC_"), new("RACE"), new("PERK"), new("QUST")
    dial = new("DIAL")
    items = new("BOOK", "MISC", "INGR", "ALCH", "KEYM", "SLGM")
    weather = new("WTHR", "CLMT")
    world = r.get("CELL~", 0) + r.get("WRLD~", 0)
    parts = []
    if armo_new + weap_new > 500:
        return None                                  # an overhaul generating enchanted variants: its label stands
    cands = []
    if magic >= 50 and magic >= 5 * (armo + weap):
        cands.append(("Magic - Spells & Enchantments", magic, f"{magic} new spell/enchantment/effect records"))
    elif armo and weap:
        cands.append(("Weapons and Armour", armo + weap, f"{armo} armour and {weap} weapon/ammo records (new or altered)"))
    elif armo:
        cands.append(("Armour", armo, f"{armo} armour records (new or altered)"))
    elif weap:
        cands.append(("Weapons", weap, f"{weap} weapon/ammo records (new or altered)"))
    elif magic:
        cands.append(("Magic - Spells & Enchantments", magic, f"{magic} new spell/enchantment/effect records"))
    if shouts:
        cands.append(("Shouts", shouts * 3, f"{shouts} new shout/word records"))
    if npc >= 10:
        cands.append(("NPC - Appearance", npc, f"{npc} new NPC records"))
    elif npc >= 3:
        cands.append(("NPC - Other", 1, f"{npc} new NPC records (a handful: not the subject)"))
    if race and npc and not new("HDPT") and npc <= 20 * race:
        # a race with no head parts of its own, with a handful of actors of it: a creature race (the owner, 2026-09-23:
        # Dire Wolves). A hundred actors against two races is a population with some creatures in it (Wyrmstooth)
        cands.append(("Creatures - New Creatures", race * 3 + npc, f"{npc} NPC records of {race} new race(s) with no head parts: a creature race"))
    elif race:
        cands.append(("Races, Classes, and Birthsigns", race * 3, f"{race} new race records"))
    if perk >= 10:
        cands.append(("Class, Perks, Powers and Blessings", perk, f"{perk} new perk records"))
    if qust >= 3:
        cands.append(("Quests and Adventures", qust * 2, f"{qust} new quest records"))
    elif qust and dial >= 3:
        # a quest that speaks: its own dialogue topics make it quest content, however few (the owner, 2026-09-23: Sell
        # Unusual Gems - one quest, seven topics - is a quest mod)
        cands.append(("Quests and Adventures", qust * 2, f"{qust} new quest record(s) with {dial} dialogue topics"))
    if items >= 5 and not (armo or weap):
        cands.append(("Items and Objects - World", items, f"{items} new item records"))
    if weather:
        cands.append(("Environmental", weather * 2, f"{weather} new weather/climate records"))
    if world >= 200_000 and not cands:
        cands.append(("Locations - New", 1, f"{world // 1024} KB of cell/world records (edits or new: weak)"))
    if not cands:
        return None
    cat, n, why = max(cands, key=lambda c: c[1])
    raw = int(re.match(r"(\d+)", why).group(1)) if re.match(r"(\d+)", why) else n
    strong = raw >= 5 and n >= 5
    return cat, (W_RECORDS_STRONG if strong else W_RECORDS_WEAK), why + (" (strong)" if strong else " (few)")


def _text_votes(m):
    """Votes from the words the mod uses about itself: its name counts fully, its documents at a lower rate."""
    name, docs = m.name, (m.text or "")
    # "X from Y" / "X for Y": Y is the subject (Perks from Questing is about questing) - its words count triple
    subject, proper = "", name
    ms = re.search(r"\b(?:from|for)\s+(.+)$", TAG_PATCH.sub(" ", name), re.I)
    if ms:
        subject = ms.group(1)
        proper = TAG_PATCH.sub(" ", name)[:ms.start()]
    scores, reasons, definitive = {}, {}, set()
    has_art = any(f.lower().endswith((".dds", ".nif")) for f in (m.files or ()))
    # R23 a mod that ships only distribution files (SPID / KID / SkyPatcher-style INIs) hands out what its name proper
    # names; a "for Y" subject is who receives it (the owner, 2026-09-23: Wolf Armor for The Companions - SPID is armour)
    shipped = [f.lower() for f in (m.files or ()) if not f.lower().endswith(("meta.ini", ".txt", ".md"))]
    distribution_only = bool(shipped) and all(f.endswith(("_distr.ini", "_kid.ini", "_swap.ini", "_flm.ini")) for f in shipped)
    recipients = distribution_only and bool(subject)
    for rx, cat, mult in TEXT_SIGNALS:
        hits_n = {h.lower() for h in (x if isinstance(x, str) else x[0] for x in rx.findall(proper if recipients else name))}
        hits_s = {h.lower() for h in (x if isinstance(x, str) else x[0] for x in rx.findall(subject))} if subject and not recipients else set()
        hits_d = {h.lower() for h in (x if isinstance(x, str) else x[0] for x in rx.findall(docs))} if docs else set()
        # R17 a mod's documents name what it REQUIRES ("Address Library", "SKSE Menu Framework") and a "for X" subject names
        # what it targets ("Fix Note icon for SkyUI"): neither says the mod is one - tier-0 leaves count from the name proper
        # only (the owner, 2026-09-23: Item Equip Restrictor, Sure of Stealing, Wait Your Turn, Custom Difficulty UI)
        if norm(cat) in TIER0:
            hits_d, hits_s = set(), set()
            if subject:
                hits_n = {h.lower() for h in (x if isinstance(x, str) else x[0] for x in rx.findall(proper))}
        if norm(cat) in TARGET_IN_SUBJECT and subject:
            hits_s = set()
            hits_n = {h.lower() for h in (x if isinstance(x, str) else x[0] for x in rx.findall(proper))}
        # R18 a mod that ships no meshes or textures is not art, whatever its readme mentions ("sitting on a bench")
        if not has_art and cat.startswith(("Models and Textures", "Environment", "PBR")):
            hits_d = set()
        w = (TEXT_NAME_HIT * mult if hits_n else 0.0) + (TEXT_DOC_HIT * mult * min(3, len(hits_d)) if hits_d else 0.0)
        if hits_s:
            w += 2.0 * TEXT_NAME_HIT * mult
        if w:
            scores[cat] = scores.get(cat, 0.0) + w
            reasons.setdefault(cat, []).extend(sorted(hits_n)[:2] + (sorted(hits_d - hits_n)[:1]))
            if hits_n and mult >= DEFINITIVE:
                definitive.add(cat)
    out = []
    for cat, w in scores.items():
        if cat in definitive and norm(cat) in NAME_DEFINED:
            w = max(w, W_NAME_DEFINED)            # the owner defined this leaf by its name: the name decides
            cap = 99.0
        elif cat in definitive:
            cap = 4.5
        elif subject and any(rx.search(subject) for rx, c, _m in TEXT_SIGNALS if c == cat):
            cap = 4.0                             # the subject of an "X from Y" name
        else:
            cap = TEXT_CAP
        out.append(("text", cat, min(cap, w), "says " + ", ".join(f"'{x}'" for x in reasons[cat][:3])))
    return out


def _path_votes(m):
    """Votes from what the folder ships: the file kinds (a DLL, interface files, animations, sound) and the asset paths,
    each path class in proportion to its share of the mod's files. Returns (votes, art_only, best_path_leaf)."""
    files = m.files or []
    votes = []
    if not files:
        return votes, False, None
    exts = {os.path.splitext(f)[1].lower() for f in files}
    art_only = not m.plugins and exts <= ART_EXTS and bool(exts & {".dds", ".nif"})
    if ".dll" in exts:
        votes.append(("files", "Utilities", 0.5, "ships a DLL (SKSE plugin) - weak: a named feature is not a utility"))
    if ".hkx" in exts and not art_only:
        votes.append(("files", "Animation - General", W_FILES, "ships animations / behaviours"))
    if exts & {".wav", ".xwm", ".fuz"} and not exts & {".dds", ".nif"}:
        votes.append(("files", "Audio", W_FILES, "ships sound files"))
    counts = {}
    n_art = 0
    own = {p[0].lower() for p in (m.plugins or [])}
    for f in files:
        fl = f.lower()
        # FaceGen data under the mod's own plugin is its NPCs' generated faces, not a face mod (CFTO's drivers)
        fg = re.search(r"facegendata/face(geom|tint)/([^/]+)/", fl)
        if fg and fg.group(2) in own:
            continue
        if not fl.endswith((".dds", ".nif", ".tri", ".hkx", ".swf", ".seq", ".osp", ".xml")):
            continue
        n_art += 1
        for rx, leaf in PATH_SIGNALS:
            if rx.search(fl):
                counts[leaf] = counts.get(leaf, 0) + 1
                break
    best = None
    if n_art:
        scale = 3.0 if art_only else 1.5
        for leaf, n in sorted(counts.items(), key=lambda kv: -kv[1])[:3]:
            share = n / n_art
            if share < 0.15:
                continue
            if leaf == "__equipment__":
                leaf_name = "Armour" if any("/armor/" in f.lower() or "/clothes/" in f.lower() for f in files) else "Weapons"
                if any("/weapons/" in f.lower() for f in files) and any("/armor/" in f.lower() for f in files):
                    leaf_name = "Weapons and Armour"
            elif leaf == "__hairface__":
                leaf_name = "Hair" if any("/hair/" in f.lower() for f in files) else "Face"
            else:
                leaf_name = leaf
            votes.append(("paths", leaf_name, round(scale * share, 2), f"{n} of {n_art} asset files under {leaf_name.lower()} paths"))
            if best is None:
                best = leaf_name
    if not counts and art_only:
        votes.append(("files", "Models and Textures - General", W_FILES, "ships only meshes/textures, no plugin"))
        best = "Models and Textures - General"
    return votes, art_only, best


def gather_votes(m, nexus_cat, mo2_names, structural_patch, nexus_names=frozenset()):
    """Every signal as a vote; nothing decided yet. NO Nexus category and no MO2 category that mirrors one (the owner,
    2026-09-23: they get in the way) - only a category the user created himself in MO2 that names one of the tree's
    own leaves counts, as his statement."""
    votes = []
    for c in m.mo2_cats or ():
        name = mo2_names.get(c) if mo2_names else None
        if not name or norm(name) in ("unpublished",):
            continue
        if norm(name) == "test":
            # decisive: a name word the owner defined (IED Key Override says 'ied') never takes a test build out
            votes.append(("mo2", "Test Builds", 99.0, "MO2 category 'test' (decisive)"))
            break
        if norm(name) in NEXUS_TO_LEAF or norm(name) in nexus_names:
            continue                                  # a Nexus category name (whoever wrote it): not his statement
        if norm(name) in {norm(x) for x in LEAVES}:
            votes.append(("mo2", canonical(name), W_MO2_USER, f"MO2 category '{name}' you created"))
            break
    rv = _records_vote(m)
    if rv:
        votes.append(("records", rv[0], rv[1], rv[2]))
    pv, art_only, best_path = _path_votes(m)
    votes.extend(pv)
    if art_only:
        votes.append(("files", "__art_only__", 0.0, best_path or "Models and Textures - General"))
    votes.extend(_scope_votes(m))
    votes.extend(_text_votes(m))
    if TAG_PATCH.search(m.name):
        votes.append(("tag", "Patches", W_TAG, "[Patch] tag"))
    if structural_patch:
        votes.append(("structure", "Patches", 2.5, structural_patch))
    return votes


ANIMAL_NOUNS = re.compile(r"\b(crows?|ravens?|birds?|hawks?|eagles?|owls?|seagulls?|deer|elk|stags?|wol(f|ves)|dogs?|bears?|"
                          r"sabre ?cats?|saber ?cats?|foxes|fox|rabbits?|hares?|goats?|cows?|mammoths?|horkers?|skeevers?|"
                          r"mudcrabs?|fish|salmon|slaughterfish|chickens?|boars?|squirrels?|butterfl(y|ies)|moths?|"
                          r"dragonfl(y|ies)|critters?|wildlife|fauna|predators?|prey)\b", re.I)


def decide(m, votes, nexus_cat=""):
    """The rules over the votes, then the winner. Returns (category, why, adjusted votes). No rule reads a label."""
    votes = [list(v) for v in votes]
    notes = []
    for marker_name in ("__framework__", "__art_only__", "__everywhere__"):
        pass
    framework = next((v for v in votes if v[1] == "__framework__"), None)
    if framework is not None:
        votes.remove(framework)
        notes.append(framework[3])
    art_marker = next((v for v in votes if v[1] == "__art_only__"), None)
    art_target = None
    if art_marker is not None:
        votes.remove(art_marker)
        art_target = art_marker[3]
    everywhere = next((v for v in votes if v[1] == "__everywhere__"), None)
    if everywhere is not None:
        votes.remove(everywhere)
        notes.append(everywhere[3])
    files = m.files or []
    rec = m.records or {}
    n_pex = sum(1 for f in files if f.endswith(".pex"))
    has_dll = any(f.endswith(".dll") for f in files)
    has_hkx = any(f.endswith(".hkx") for f in files)
    rec_new = sum(v for k, v in rec.items() if not k.endswith("*") and not k.endswith("~"))
    rec_alt = sum(v for k, v in rec.items() if k.endswith("*"))
    magic_new = sum(rec.get(k, 0) for k in ("SPEL", "ENCH", "MGEF", "SCRL"))
    plain = TAG_PATCH.sub(" ", m.name)
    says_fix = bool(re.search(r"\b(fix(es|ed|er)?|bug ?fix(es|er)?|hotfix)\b", plain, re.I))
    # a leaf the owner defined BY NAME, hit in this mod's name, takes precedence over what the files and paths say
    named = any(v[0] == "text" and norm(v[1]) in NAME_DEFINED and v[2] >= W_NAME_DEFINED for v in votes)
    if named:
        for v in votes:
            if v[0] in ("files", "paths", "scope"):
                v[2] *= 0.5
        notes.append("named for a leaf the owner defined: files, paths and scope count half")
    # R10 mechanism records: spells and effects shipped with animations, a DLL or scripts are a vehicle (TK Dodge,
    # Press H to Horse, Perks from Questing) - they count 0.4 unless it is a spell pack
    # an MCM or a SkyPatcher config beside the scripts is a system too (Vivid Routines: 2 scripts, an MCM, 8 spells)
    has_cfg = any(f.lower().startswith(("mcm/", "skse/plugins/skypatcher/")) for f in files)
    if (has_hkx or has_dll or n_pex >= 5 or (n_pex and has_cfg)) and magic_new and magic_new < 50:
        for v in votes:
            if v[0] == "records" and v[1] == "Magic - Spells & Enchantments":
                v[2] *= 0.4
                notes.append("spells as a mechanism (animations, a DLL or scripts ship with them)")
    # R13 a name that says fix is a fix: its records are the fix's means, not new content (a utility does nothing on
    # its own; USSEP alters thousands of records)
    if says_fix and (m.plugins or has_dll):          # a DLL that says fix is a fix too (Fix Note icon for SkyUI)
        for v in votes:
            if v[0] == "records":
                v[2] *= 0.3
        votes.append(["rule", "Bug Fixes", 3.0, "named a fix"])
    # R7 alters far more than it adds: the mod is about existing things - new-content records count half, and scope
    # (which places) decides ahead of what it adds
    elif rec and rec_alt >= 3 * max(1, rec_new) and rec_alt >= 20:
        for v in votes:
            if v[0] == "records":
                v[2] *= 0.5
        notes.append(f"alters {rec_alt} records, adds {rec_new}: about existing content")
    if has_hkx:
        for v in votes:
            if v[0] == "text" and v[1] == "NPC - AI and Behaviour":
                v[2] *= 0.3
                notes.append("behaviour files ship: 'behaviour' means the animation graph")
    # R14 mostly animation files (60%+ under animation paths, with .hkx) is an animation mod (TDM, SDS)
    anim_share = max((v[2] for v in votes if v[0] == "paths" and v[1].startswith("Animation")), default=0.0)
    if has_hkx and anim_share >= 0.9 and not named:
        votes.append(["rule", "Animation - General", 2.0, "mostly animation files"])
    # R15 abilities given to actors: perks/spells added while actors are altered, none added, is a combat system
    # (Know Your Enemy), not creatures or NPCs
    distributes = any(f.lower().endswith(("_distr.ini", "_kid.ini")) for f in files)      # SPID / KID: records handed to actors
    if rec and not rec.get("NPC_", 0) and (rec.get("PERK", 0) + rec.get("SPEL", 0)) >= 10 \
            and ((rec.get("NPC_*", 0) + rec.get("RACE*", 0)) >= 10 or distributes):
        votes.append(["rule", "Gameplay - Combat", 3.0, "abilities given to actors" + (" through a distribution file" if distributes else "") + ": a combat system"])
    # R19 "X Menu" / "X UI": the menu is the means, X is the subject - a content leaf named beside a UI word gets the
    # vote (the owner, 2026-09-23: Custom Difficulty UI is gameplay, Add Spell Menu is spells)
    mv = re.search(r"\b(\w+(?: \w+)?) (menu|ui|hud|widget|overlay|panel)\b", plain, re.I)
    if mv:
        before = mv.group(1)
        content = [c for rx, c, _w in TEXT_SIGNALS if rx.search(before) and INDEX_TIER.get(norm(c), 0) >= 3
                   and norm(c) not in ("patches", "overhauls")]
        if content:
            totals0 = {}
            for v in votes:
                totals0[norm(v[1])] = totals0.get(norm(v[1]), 0.0) + v[2]
            subj = max(content, key=lambda c: totals0.get(norm(c), 0.0))
            votes.append(["rule", subj, 2.0, f"the menu is the means; the subject is {subj.lower()}"])
            # R20 the item records of a spell mod are its tomes: delivery, not the subject
            if norm(subj) == "magic - spells & enchantments":
                for v in votes:
                    if v[0] == "records" and v[1] == "Items and Objects - World":
                        v[2] *= 0.4
                        notes.append("item records are spell tomes: delivery, not the subject")
    # R25 the NPCs a place mod adds are its inhabitants: with a location vote of 3.0 or more, new-NPC records count half
    # (the owner, 2026-09-23: Carriage and Ferry Travel Overhaul, Wyrmstooth; Holds The City Overhaul's 1293 citizens)
    if any(v[0] == "scope" and (v[1].startswith("Location Overhauls") or v[1] == "Locations - New") and v[2] >= 3.0 for v in votes):
        for v in votes:
            if v[0] == "records" and v[1] == "NPC - Appearance":
                v[2] *= 0.5
                notes.append("its NPCs are the place's inhabitants")
    # R22 quests that only hold scripts: quest records with no dialogue of their own, scripts beside them, no meshes and no
    # menu art - they are how a system runs (start-up and MCM quests), not a quest; the system is gameplay, and its few
    # spells and effects are its means (the owner, 2026-09-23: Acquisitive Soul Gems is a system for soul gem filling
    # logic, Simple Degradation is a gameplay system)
    # the system must act on the game - globals, settings, effects, spells, perks or form lists beside its quests; a
    # quest, messages and scripts alone is a tool (MCM Recorder)
    rule_recs = sum(rec.get(k, 0) + rec.get(k + "*", 0) for k in ("GLOB", "GMST", "MGEF", "SPEL", "PERK", "FLST"))
    if rec.get("QUST", 0) and not rec.get("DIAL", 0) and not rec.get("NPC_", 0) and n_pex >= 3 and rule_recs \
            and not any(f.endswith((".nif", ".swf")) for f in files):
        for v in votes:
            if v[0] == "records" and v[1] == "Quests and Adventures":
                v[2] *= 0.3
            if v[0] == "records" and v[1] == "Magic - Spells & Enchantments" and magic_new < 50:
                v[2] *= 0.4
        votes.append(["rule", "Gameplay - General", 2.0, f"a scripted system: {rec.get('QUST', 0)} quest(s) holding scripts, no dialogue"])
    # R21 a leveled-list injector is the patch layer: it integrates other mods' items into the lists (the owner,
    # 2026-09-23: Dynamic Leveled Lists goes in Patches)
    if has_dll and re.search(r"\bleveled lists?\b", plain, re.I):
        votes.append(["rule", "Patches", 2.5, "a leveled-list injector: the patch layer between other mods' items and the lists"])
    # R16 a framework master is a system other mods build on (Campfire)
    if framework is not None:
        votes.append(["rule", "Gameplay - General", 2.0, "a system other mods build on"])
    # R2 clothes are ARMO records: armour records with clothing words in the name are clothing
    if any(v[0] == "records" and v[1] == "Armour" for v in votes) and re.search(r"\b(clothing|clothes|outfits?|dress(es)?|robes?|cloaks?|capes?|jewell?ery|amulets?|rings?|necklaces?|circlets?)\b", plain, re.I) \
            and not rec.get("WEAP", 0):
        for v in votes:
            if v[0] == "records" and v[1] == "Armour":
                v[1] = "Clothing and Accessories"
                notes.append("armour records with clothing in the name are clothing")
    # R4 a replacer: no plugin, only meshes/textures - it is art; its paths say which (equipment meshes stay in the
    # EDITED equipment block)
    if art_target:
        eq_word = next((v[1] for v in votes if v[0] == "text" and v[1] in ("Weapons", "Armour", "Armour - Shields", "Clothing and Accessories")), None)
        if art_target == "Models and Textures - General" and eq_word:
            art_target = eq_word                       # custom mesh paths say nothing; the name says what it replaces
        elif art_target == "Models and Textures - General" and any(v[0] == "text" and v[1] == "Creatures - New Creatures" and v[2] >= 1.0 for v in votes):
            art_target = "Creatures - Appearance"       # a creature replacer: art for an animal the game already has
        votes.append(["rule", art_target, 2.0, f"a replacer: only meshes/textures; {'its name says' if eq_word and art_target == eq_word else 'its paths say'} {art_target}"])
    # R24 a mod that calls itself a replacer or retexture of a creature it names is that creature's appearance, plugin
    # or not (the owner, 2026-09-23: Felidae - A Sabrecat Replacer)
    if re.search(r"\b(replacers?|retextures?|remodels?|re-?textures?)\b", plain, re.I):
        for v in votes:
            if v[0] == "text" and v[1] == "Creatures - New Creatures":
                v[1] = "Creatures - Appearance"
                notes.append("a replacer of a creature it names: creature appearance")
    # R26 a mod that ships only distribution files and hands out gear that already exists (no armour, no plugin) is
    # about what the NPCs wear, not the gear (the owner, 2026-09-23: Wolf Armor for The Companions - SPID "has no armor
    # files, it just makes npcs wear specific armor that's already there")
    shipped = [f.lower() for f in files if not f.lower().endswith(("meta.ini", ".txt", ".md"))]
    if shipped and not m.plugins and all(f.endswith(("_distr.ini", "_kid.ini", "_swap.ini", "_flm.ini")) for f in shipped):
        for v in votes:
            if v[1] in ("Armour", "Weapons", "Weapons and Armour", "Armour - Shields", "Clothing and Accessories"):
                v[1] = "NPC - Appearance"
                notes.append("hands out gear that already exists: what NPCs wear")
    # R8 PBR supersedes other textures (the owner: "if it says pbr it goes in the pbr textures section")
    if re.search(r"\bpbr\b", m.name, re.I) or any(v[0] == "paths" and v[1] == "PBR Textures" and v[2] >= 1.0 for v in votes):
        if not m.plugins or art_target:
            votes.append(["rule", "PBR Textures", 4.0, "says PBR: supersedes the other texture blocks"])
    # R5 a patch is a patch by structure; the word or tag alone counts little
    if not any(v[0] == "structure" for v in votes):
        for v in votes:
            if v[0] in ("tag", "text") and v[1] == "Patches":
                v[2] *= 0.3
    # R6 scripts-and-systems: many scripts or a DLL is a system; the equipable items it adds (Campfire's tents) are
    # props - equipment records count half - and with no content of its own it leans Gameplay
    scripted = framework is not None or (m.plugins and files and (n_pex >= 20 or has_dll))
    if scripted:
        for v in votes:
            if v[0] == "scope" and not (v[1] == "Location Overhauls - General" and ("exterior" in v[3] or v[3].startswith("location overhaul"))) \
                    and v[1] != "Locations - New":
                v[2] *= 0.5                        # a system's cells are utility cells, not a place it overhauls
                # (its exterior edits stay whole: what it adds to a worldspace is what needs patches - the owner,
                # 2026-09-23, Carriage and Ferry Travel Overhaul)
    if scripted and rec:
        for v in votes:
            if v[0] == "records" and v[1] in ("Armour", "Weapons", "Weapons and Armour", "Clothing and Accessories") and (rec.get("ARMO", 0) + rec.get("WEAP", 0)) < 100:
                v[2] *= 0.5
                notes.append("a scripted system: its equipment records count half")
        if not any(rec.get(k, 0) for k in ("NPC_", "QUST", "RACE")) and not (rec.get("CELL~", 0) + rec.get("WRLD~", 0) > 200_000) \
                and (rec.get("ARMO", 0) + rec.get("WEAP", 0)) < 100:
            votes.append(["rule", "Gameplay - General", 0.9, "a scripted system: scripts or a DLL, no content of its own"])
    # content-type fallback: a plugin with scripts and nothing decisive is a system; a plugin that only alters is an
    # edit of existing things; scripts alone are a utility
    if not any(v[2] >= 1.0 for v in votes):
        if m.plugins and n_pex:
            votes.append(["files", "Gameplay - General", 0.8, "a scripted plugin, nothing more specific"])
        elif m.plugins and rec_alt and not rec_new:
            votes.append(["files", "Overhauls", 0.6, "a plugin that only alters existing records"])
        elif n_pex and not m.plugins:
            votes.append(["files", "Utilities", 0.8, "scripts and nothing visual"])
    totals, best_reason = {}, {}
    for src, cat, w, why in votes:
        k = norm(cat)
        totals[k] = totals.get(k, 0.0) + w
        best_reason.setdefault(k, cat)
    if not totals:
        return None, "", votes
    prio = {"mo2": 0, "community": 1, "structure": 1, "scope": 2, "records": 3, "rule": 4, "paths": 5, "files": 6, "text": 7, "tag": 8}
    def first_src(k):
        return min((prio.get(v[0], 9) for v in votes if norm(v[1]) == k), default=9)
    win = max(totals, key=lambda k: (round(totals[k], 3), -first_src(k)))
    cat = canonical(best_reason[win])
    # R9 new vs edited equipment: a plugin that ADDS armour/weapon records is new content; a replacer or an edit is not
    fam = EDIT_OF.get(cat.lower(), cat.lower())
    if fam in NEW_OF:
        new_eq = rec.get("ARMO", 0) + rec.get("WEAP", 0) + rec.get("AMMO", 0)
        cat = NEW_OF[fam] if (m.plugins and new_eq >= 3) else canonical(fam)
        notes.append(f"{'new' if cat.startswith('New') else 'edited'} equipment: {new_eq} new armour/weapon records")
    # R27 a new creature that is an animal - wildlife by its own noun - goes to Animals; monsters stay New Creatures
    # (the owner, 2026-09-23: Crows go to Animals). The series tag "Monsters and Animals" is not an animal noun.
    if cat == "Creatures - New Creatures":
        own = re.sub(r"(?i)\bmonsters and animals\b", " ", plain)
        if ANIMAL_NOUNS.search(own) or (re.search(r"(?i)\banimals\b", own) and not re.search(r"(?i)\bmonsters?\b", own)):
            cat = "Creatures - Animals"
            notes.append("an animal: wildlife")
    shown = sorted(votes, key=lambda v: -v[2])[:4]
    why = f"{cat} ({totals[win]:.1f}): " + "; ".join(f"{v[0]} {v[1]} {v[2]:.1f} - {v[3]}" for v in shown)
    if notes:
        why += " | " + "; ".join(notes)
    return cat, why, votes


def structural_patch_reason(m, owner_of, framework_masters=frozenset(), owner_tier=None):
    """A plugin whose masters belong to two or more other CONTENT mods is a patch by construction; one such master plus
    the word 'patch' in the name proper is too. Not patch evidence: a framework master (ten or more dependents:
    Campfire, the magic overhauls, USSEP) and a master owned by a tier-0/1 mod (SkyUI, MCM Helper, a fix) - those are
    dependencies. The [Patch] tag alone is not the word: the Keyword Tagger writes it from plugin descriptions too."""
    own = {f.lower() for f, _, _ in m.plugins + m.optional}
    foreign = set()
    for _f, masters, _esm in m.plugins:
        for mast in masters:
            k = mast.lower()
            if k in BASE_MASTERS or k in own or k in framework_masters:
                continue
            o = owner_of.get(k)
            if o is None or o is m:
                continue
            if owner_tier is not None and owner_tier(o) <= 1:
                continue
            foreign.add(o.name)
    if len(foreign) >= 2:
        return f"its plugins take masters from {len(foreign)} other mods ({', '.join(sorted(foreign)[:3])})"
    plain = TAG_PATCH.sub(" ", m.name)
    if len(foreign) == 1 and _PATCH_WORD.search(plain):
        return f"named a patch and takes its master from {next(iter(foreign))}"
    return ""


# WHAT A PLUGIN REFERENCES (the owner, 2026-09-23: "specific names of things it references, like Whiterun in the name
# or the Whiterun worldspace, as a discriminator"). The CELL and WRLD groups are walked (nested blocks and all) for the
# EDIDs of the cells and worldspaces a plugin adds or alters; exterior cells are counted per worldspace.
_REF_LIMIT = 6000


def plugin_refs(path, n_masters):
    """{"cells_new": [edid], "cells_alt": [edid], "worlds_new": [edid], "worlds_alt": [edid], "ext": {world: count},
        "refs": {place key: references placed or altered there}} - a place key is an interior cell's EDID or
        "<world>/<cell edid or form id>" for an exterior cell."""
    out = {"cells_new": [], "cells_alt": [], "worlds_new": [], "worlds_alt": [], "ext": {}, "refs": {}}
    seen = 0                                                 # reset per top-level group below
    world_names = {}
    cur = {"key": None}

    def edid_of(fh, rh):
        dsize, flags = struct.unpack("<I", rh[4:8])[0], struct.unpack("<I", rh[8:12])[0]
        data = fh.read(dsize)
        if flags & 0x00040000:
            try:
                data = zlib.decompress(data[4:])
            except zlib.error:
                return None
        p = 0
        while p + 6 <= len(data):
            sig, ln = data[p:p + 4], struct.unpack("<H", data[p + 4:p + 6])[0]
            p += 6
            if sig == b"EDID":
                return data[p:p + ln].split(b"\x00", 1)[0].decode("cp1252", "replace")
            p += ln
        return None

    def group(fh, end, world):
        nonlocal seen
        while fh.tell() < end and seen < _REF_LIMIT:
            rh = fh.read(24)
            if len(rh) < 24:
                return
            if rh[:4] == b"GRUP":
                gsize, gtype = struct.unpack("<I", rh[4:8])[0], struct.unpack("<i", rh[12:16])[0]
                gend = fh.tell() + gsize - 24
                if gtype == 1:                                   # a worldspace's children: the label is the WRLD form id
                    wid = struct.unpack("<I", rh[8:12])[0]
                    group(fh, gend, world_names.get(wid, f"WRLD{wid:08X}"))
                elif gtype in (2, 3, 4, 5, 6, 8, 9):             # interior blocks, exterior blocks, cell children
                    group(fh, gend, world)
                fh.seek(gend)
                continue
            sig, dsize, form = rh[:4], struct.unpack("<I", rh[4:8])[0], struct.unpack("<I", rh[12:16])[0]
            new = (form >> 24) >= n_masters
            seen += 1
            if sig == b"WRLD":
                ed = edid_of(fh, rh) or f"WRLD{form:08X}"
                world_names[form] = ed
                (out["worlds_new"] if new else out["worlds_alt"]).append(ed)
            elif sig == b"CELL":
                ed = edid_of(fh, rh)
                if world is None:                                # an interior cell: its EDID is the name
                    if ed:
                        (out["cells_new"] if new else out["cells_alt"]).append(ed)
                    cur["key"] = ed or f"CELL{form:08X}"
                else:                                            # an exterior cell: counted under its worldspace
                    out["ext"][world] = out["ext"].get(world, 0) + 1
                    cur["key"] = f"{world}/{ed or f'{form:08X}'}"
            elif sig in (b"REFR", b"ACHR", b"PGRE", b"PHZD", b"PMIS", b"PARW", b"PBEA", b"PFLA", b"PCON", b"PBAR"):
                fh.seek(dsize, 1)                                # a placed reference: counted at the current cell
                k = cur["key"] or "?"
                out["refs"][k] = out["refs"].get(k, 0) + 1
            else:
                fh.seek(dsize, 1)                                # LAND, NAVM and the rest
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
            if len(head) < 24 or head[:4] != b"TES4":
                return out
            fh.seek(24 + struct.unpack("<I", head[4:8])[0])
            while True:
                gh = fh.read(24)
                if len(gh) < 24 or gh[:4] != b"GRUP":
                    break
                gsize, label, gtype = struct.unpack("<I", gh[4:8])[0], gh[8:12], struct.unpack("<i", gh[12:16])[0]
                gend = fh.tell() + gsize - 24
                if gtype == 0 and label in (b"CELL", b"WRLD"):
                    seen = 0                                 # CELL and WRLD each get the budget: a big interior group
                    group(fh, gend, None)                    # must not hide a new worldspace (Wyrmstooth, 2026-09-23)
                fh.seek(gend)
    except (OSError, struct.error):
        pass
    return out


# named places, as they appear in names and in EDIDs (CamelCase, no spaces): word -> the place
PLACES = {p.replace(" ", "").lower(): p for p in (
    "Whiterun", "Riften", "Solitude", "Windhelm", "Markarth", "Falkreath", "Dawnstar", "Morthal", "Winterhold",
    "Riverwood", "Rorikstead", "Ivarstead", "Shors Stone", "Kynesgrove", "Dragon Bridge", "Karthwasten", "Helgen",
    "Raven Rock", "Skaal", "Stonehills", "Darkwater Crossing", "Half-Moon Mill", "Old Hroldan", "Angas Mill",
    "Mixwater Mill", "Sarethi Farm", "Heljarchen", "Dragon Bridge", "Nightgate", "Tel Mithryn", "Soljund", "Kolskeggr",
    "Left Hand Mine", "Salvius Farm", "Katla", "Pelagia", "Battle-Born", "Loreius", "Merryfair", "Goldenglow",
    "Whistling Mine", "Fort Dawnguard", "High Hrothgar", "Sky Haven", "Castle Volkihar", "Bthardamz", "Blackreach")}
HOME_WORDS = re.compile(r"playerhouse|playerhome|breezehome|hjerim|honeyside|proudspire|vlindrel|lakeview|windstad|heljarchenhall|severinmanor|myrwatch|tundrahomestead|hendraheim|goldenhills|bloodchill|shadowfoot|nchuanthumz|elysium", re.I)
DUNGEON_WORDS = re.compile(r"cave|ruins?|barrow|crypt|mine(?!r)|tomb|grotto|hideout|lair|redoubt|sanctum|depths|nordic|dwemer|dwarven|catacomb|labyrinth|vault|den\b|camp\b|tower", re.I)
FACTION_WORDS = re.compile(r"college|guild|brotherhood|jorrvaskr|companions|thalmor|dawnguard|bards|greybeard|highhrothgar|penitus|stormcloak|legion|castlevolkihar|nightingale|sanctuary", re.I)
LANDMARK_WORDS = re.compile(r"shrine|standingstone|waystone|altar|statue|bridge|lighthouse|farm|mill|watchtower|ruin|fort\b", re.I)


def _scope_votes(m):
    """Votes from what the plugins reference: a new worldspace, a home's cells, dungeon cells, a town's cells, interiors
    only, exteriors everywhere."""
    r = m.refs
    votes = []
    if not r:
        return votes
    cells = r["cells_new"] + r["cells_alt"]
    ext_total = sum(r["ext"].values())
    # HOW THE REFERENCES DISTRIBUTE (the owner, 2026-09-23): a location overhaul concentrates many placed references
    # in one worldspace or cell - a city's own worldspace (WhiterunWorld), a town's cells, an interior, or some other
    # place; clutter puts a few changes on the same objects across many cells and spaces
    refs = r.get("refs", {})
    total = sum(refs.values())
    n_places = len(refs)
    if total:
        by_world = {}
        for k, n in refs.items():
            w = k.split("/", 1)[0] if "/" in k else "interior"
            by_world[w] = by_world.get(w, 0) + n
        top_world, top_world_n = max(by_world.items(), key=lambda kv: kv[1])
        top_cell, top_cell_n = max(refs.items(), key=lambda kv: kv[1])
        interior_n = by_world.get("interior", 0)
        rec = m.records or {}
        base_edits = sum(rec.get(k + "*", 0) for k in ("STAT", "MSTT", "FURN", "ACTI", "CONT", "MISC", "DOOR", "LIGH", "FLOR", "TREE"))
        own_new = set(r["cells_new"]) | set(r["worlds_new"])
        new_n = sum(n for k, n in refs.items() if k.split("/", 1)[0] in own_new)
        if n_places >= 20 and total / n_places <= 3 and base_edits <= 30:
            votes.append(("scope", "Models and Textures - Clutter", 3.0, f"clutter: {total} references over {n_places} cells, {total / n_places:.1f} each"))
        elif r["worlds_new"] and total >= 60 and new_n >= 0.5 * total:
            # its references sit in the worldspace and cells it adds: a new land (the owner, 2026-09-23: Wyrmstooth)
            votes.append(("scope", "Locations - New", 3.5, f"{new_n} of {total} references in the worldspace and cells it adds"))
        elif total >= 60:
            def place_of(key):
                kl = key.lower()
                for w, place in PLACES.items():
                    if w in kl:
                        return place
                return None
            ext_n = total - interior_n
            place = place_of(top_world) or place_of(top_cell)
            ext_worlds = {w: n for w, n in by_world.items() if w != "interior"}
            top_ext_world = max(ext_worlds, key=ext_worlds.get) if ext_worlds else ""
            ext_place = place_of(top_ext_world) if top_ext_world else None
            conc = max(top_world_n, top_cell_n) / total
            # a city's or town's exterior outranks its own interiors: a city worldspace or a placed town holding a
            # fifth of the references is the overhaul's subject even when the interiors carry more
            if ext_place and ext_n >= 0.2 * total and (top_ext_world.lower().endswith("world") or conc >= 0.3):
                kind = "City" if ext_place in CAPITALS else "Town"
                votes.append(("scope", f"Location Overhauls - {kind}", 3.5, f"{kind.lower()} overhaul: {ext_worlds[top_ext_world]} exterior and {interior_n} interior references in {ext_place}"))
            elif interior_n >= 0.7 * total:
                pl = place_of(top_cell)
                votes.append(("scope", "Location Overhauls - Interior", 3.5, f"interior overhaul: {interior_n} references in {len([k for k in refs if '/' not in k])} interiors" + (f" ({pl})" if pl else "")))
            elif place and conc >= 0.5:
                kind = "City" if place in CAPITALS else "Town"
                votes.append(("scope", f"Location Overhauls - {kind}", 3.5, f"{kind.lower()} overhaul: {max(top_world_n, top_cell_n)} of {total} references in {place}"))
            elif conc >= 0.5 and not (top_world.lower() == "tamriel" and top_cell_n < 0.3 * total):
                votes.append(("scope", "Location Overhauls - General", 3.0, f"location overhaul: {max(top_world_n, top_cell_n)} of {total} references at {top_cell.split('/')[-1][:30]}"))
    everywhere = len(r["cells_alt"]) + ext_total > 200 and not r["cells_new"] and not r["worlds_new"]
    scale = 0.3 if everywhere else 1.0             # a mod that touches hundreds of cells is a systemic edit, not a place
    if everywhere:
        votes.append(("scope", "__everywhere__", 0.0, f"touches {len(r['cells_alt'])} interiors and {ext_total} exterior cells: a systemic edit"))
    if r["worlds_new"]:
        votes.append(("scope", "Locations - New", 3.5, f"adds worldspace {', '.join(r['worlds_new'][:2])}"))
    home = [c for c in cells if HOME_WORDS.search(c)]
    if home:
        votes.append(("scope", "Player homes", min(3.5, 1.5 + len(home)) * scale, f"references home cells {', '.join(home[:2])}"))
    dung = [c for c in cells if DUNGEON_WORDS.search(c) and not HOME_WORDS.search(c)]
    if cells and len(dung) >= max(1, len(cells) * 0.5):
        votes.append(("scope", "Dungeons", min(3.0, 1.0 + len(dung) * 0.5) * scale, f"references dungeon cells {', '.join(dung[:2])}"))
    place_hits = {}
    for c in cells + list(r["ext"].keys()) + r["worlds_alt"]:
        cl = c.lower()
        for w, place in PLACES.items():
            if w in cl:
                place_hits[place] = place_hits.get(place, 0) + 1
    fac = [c for c in cells if FACTION_WORDS.search(c)]
    if cells and len(fac) >= max(2, len(cells) * 0.5):
        votes.append(("scope", "Guilds/Factions", min(3.5, 1.5 + len(fac) * 0.3) * scale, f"references faction cells {', '.join(fac[:2])}"))
        place_hits = {}
    if place_hits:
        top = sorted(place_hits.items(), key=lambda kv: -kv[1])
        n_place = sum(place_hits.values())
        names = ", ".join(f"{p} ({n})" for p, n in top[:3])
        interiors_only = not r["ext"] and not r["worlds_new"]
        if interiors_only and len(cells) <= 3 and not home and total >= 20:
            votes.append(("scope", "Location Overhauls - Interior", 2.0 * scale, f"one or two interiors in {names}"))
        elif not (dung and len(dung) >= len(cells) * 0.5):
            kind = "City" if top[0][0] in CAPITALS else "Town"
            votes.append(("scope", f"Location Overhauls - {kind}", min(3.0, 1.0 + n_place * 0.5) * scale, f"references {names}"))
    elif ext_total and not r["worlds_new"] and not everywhere:
        land = [c for c in cells if LANDMARK_WORDS.search(c)]
        votes.append(("scope", "Location Overhauls - General", min(3.0, 1.0 + ext_total * 0.2) * scale, f"edits {ext_total} exterior cells" + (f" and {', '.join(land[:2])}" if land else "")))
    elif cells and not r["ext"] and not home and not dung and total >= 20:
        votes.append(("scope", "Location Overhauls - Interior", min(2.5, 1.0 + len(cells) * 0.3) * scale, f"interiors only: {', '.join(cells[:2])}"))
    return votes


def read_meta(mod_dir):
    """(nexus mod id or 0, MO2 category ids, the mod's own text from meta.ini: nexus description, notes, comments)."""
    p = os.path.join(mod_dir, "meta.ini")
    cp = configparser.RawConfigParser(strict=False)
    try:
        cp.read(p, encoding="utf-8")
        modid = int(str(cp.get("General", "modid", fallback="0")).strip('" ') or 0)
        cats = [c for c in str(cp.get("General", "category", fallback="")).strip('" ').split(",") if c and c not in ("0", "-1")]
        text = " ".join(str(cp.get("General", k, fallback="")).strip('" ') for k in ("nexusDescription", "notes", "comments"))
        text = re.sub(r"<[^>]+>", " ", text)[:4000]
    except (configparser.Error, ValueError):
        modid, cats, text = 0, [], ""
    return modid, cats, text


_README_RE = re.compile(r"(?i)^(read ?me|description|info|about|instructions?)\b.*\.(txt|md)$")


def read_self_text(mod_dir):
    """What the folder says about itself: a readme at the top level and the FOMOD info.xml (name + description)."""
    out = []
    try:
        for f in os.listdir(mod_dir):
            if _README_RE.match(f):
                try:
                    out.append(open(os.path.join(mod_dir, f), encoding="utf-8", errors="ignore").read(4000))
                except OSError:
                    pass
        info = os.path.join(mod_dir, "fomod", "info.xml")
        if os.path.isfile(info):
            t = open(info, encoding="utf-8", errors="ignore").read(8000)
            for tag in ("Name", "Description", "Groups"):
                mm = re.search(rf"<{tag}>(.*?)</{tag}>", t, re.S | re.I)
                if mm:
                    out.append(re.sub(r"<[^>]+>", " ", mm.group(1)))
    except OSError:
        pass
    return " ".join(out)


ASSET_EXTS = (".dds", ".nif", ".hkx", ".dll", ".esl", ".esp", ".esm", ".bsa", ".pex", ".seq", ".ini", ".json", ".swf",
              ".wav", ".xwm", ".fuz", ".tri", ".txt")
IGNORED_FILES = {"meta.ini", "readme.txt", "read me.txt", "changelog.txt", "changes.txt", "license.txt", "licence.txt",
                 "credits.txt", "desktop.ini", "thumbs.db"}


class Mod:
    __slots__ = ("name", "enabled", "index", "nexus_id", "mo2_cats", "plugins", "optional", "category", "why", "group", "flags", "files", "twin", "records",
                 "votes", "text", "decided", "refs", "raw_votes")

    def __init__(self, name, enabled, index):
        self.name, self.enabled, self.index = name, enabled, index
        self.nexus_id, self.mo2_cats, self.plugins = 0, [], []      # plugins: [(file, [masters], is_esm)]
        self.optional = []                                          # the same, for the mod's optional folder (MO2's Optional ESPs)
        self.category, self.why, self.group, self.flags, self.files = None, "", None, set(), []
        self.twin = None                                            # a test build: the name of the copy it supersedes
        self.records = {}                                           # {record type: new records its plugins add} for the types below
        self.votes = []                                             # the evidence model: [(source, category, weight, reason)]
        self.raw_votes = []                                         # the same before decide()'s rules, for the verdict comparison
        self.decided = None                                         # the category the evidence decided, before any displacement or merge
        self.refs = None                                            # what the plugins reference: cells, worldspaces (plugin_refs)
        self.text = ""                                              # what the mod says about itself (plugin descriptions, readme, FOMOD, Nexus description)

    @property
    def tier(self):
        return tier_of(self.category) if self.category else None


TEST_BUILD = re.compile(r"^test\s+(.+?)(?:\s+\d+(?:\.\d+)*)?$", re.I)


def pair_test_builds(mods):
    """(the owner, 2026-09-23: "the test versions should be right next to their official versions with the official
    version being superseded by the test version"). A 'test <Name> [<ver>]' mod whose official copy is in the list -
    '<Name>' (the Nexus download) or 'unpublished <Name>' (a local build) - is paired with it: both are enabled, the
    test build takes the official copy's category and is placed directly under it, so its files win. A test build
    with no counterpart still goes to Test Builds. Returns [(test, official, redundant)] - redundant when the two
    carry the same version, so the test copy adds nothing."""
    by = {m.name: m for m in mods}
    pairs = []
    for m in mods:
        mt = TEST_BUILD.match(m.name)
        if not mt or is_sep(m.name):
            continue
        base = mt.group(1).strip()
        official = by.get(base) or by.get("unpublished " + base)
        if official is None or is_sep(official.name):
            continue
        m.twin = official.name
        m.enabled = official.enabled = True
        vt = re.search(r"\s(\d+(?:\.\d+)*)$", m.name)
        pairs.append((m.name, official.name, vt.group(1) if vt else ""))
    return pairs


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
        m.nexus_id, m.mo2_cats, meta_text = read_meta(d)
        texts = [meta_text, read_self_text(d)]
        try:
            for f in os.listdir(d):
                if f.lower().endswith(PLUGIN_EXT) and os.path.isfile(os.path.join(d, f)):
                    masters, _desc, esm = read_header(os.path.join(d, f))
                    if _desc:
                        texts.append(_desc)
                    # a .esl-EXTENSION file loads in the master block whatever its header says, as does a .esm
                    m.plugins.append((f, masters, esm or f.lower().endswith((".esm", ".esl"))))
                    for k, v in plugin_new_records(os.path.join(d, f), len(masters)).items():
                        m.records[k] = m.records.get(k, 0) + v
                    if m.records.get("CELL~", 0) or m.records.get("WRLD~", 0):
                        rr = plugin_refs(os.path.join(d, f), len(masters))
                        if m.refs is None:
                            m.refs = rr
                        else:
                            for key_ in ("cells_new", "cells_alt", "worlds_new", "worlds_alt"):
                                m.refs[key_].extend(rr[key_])
                            for w, n in rr["ext"].items():
                                m.refs["ext"][w] = m.refs["ext"].get(w, 0) + n
                            for k2, n in rr.get("refs", {}).items():
                                m.refs["refs"][k2] = m.refs["refs"].get(k2, 0) + n
            opt = os.path.join(d, "optional")
            if os.path.isdir(opt):
                for f in os.listdir(opt):
                    if f.lower().endswith(PLUGIN_EXT) and os.path.isfile(os.path.join(opt, f)):
                        masters, _desc, esm = read_header(os.path.join(opt, f))
                        m.optional.append((f, masters, esm or f.lower().endswith((".esm", ".esl"))))
            m.files = scan_files(d)              # every mod, enabled or not: the files are classification evidence too
        except OSError:
            pass
        m.text = " ".join(t for t in texts if t)[:12000]
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
def place(mods, categories, mo2_category_names=None, under_nodelete=(), pins=None, community=None):
    """Set .category / .why on every mod. Returns nothing; every decision is a fact the dialog can show.
    community: {core name: {leaf: users}} pooled from other users' verdicts (fetch_community_verdicts) - one more vote."""
    order, _headers = category_order()
    pins = pins or {}
    owner_of = {}                      # plugin file -> the mod MO2 takes it from (the lowest enabled one that ships it)
    dependents = {}
    for m in mods:
        if is_sep(m.name) or "missing" in m.flags:
            continue
        for f, masters, _esm in m.plugins:
            k = f.lower()
            if m.enabled or k not in owner_of:
                owner_of[k] = m
            for mast in masters:
                dependents.setdefault(mast.lower(), set()).add(m.name)
    framework_masters = frozenset(k for k, ds in dependents.items() if len(ds) >= 10)
    nexus_names = frozenset(norm(c) for c in categories.values() if c)      # every category name Nexus uses: never a vote

    def owner_tier(o):
        if o.category:                                   # decided already (the list is walked top-down, masters first)
            return index_tier(o.category)
        c = categories.get(str(o.nexus_id), "") if o.nexus_id else ""
        return index_tier(c) if c else 3
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
            if m.twin:
                m.category, m.why = None, ""       # filled from the twin in the post-pass below
                continue
            m.category, m.why = "Test Builds", "name starts with 'test '"
            continue
        if m.plugins and all(f.lower() in BASE_MASTERS or f.lower().startswith("cc") for f, _, _ in m.plugins) and not m.nexus_id:
            m.category, m.why = "Base Game", "every plugin is a base-game or Creation Club file"
            continue
        if not m.nexus_id and OUTPUT_TOOLS.search(n):
            m.category, m.why = "Generated Outputs", "no Nexus page and a tool's output name"
            continue
        cat = categories.get(str(m.nexus_id), "") if m.nexus_id else ""
        why_shape = shape_reason(m, cat)
        if why_shape:
            m.category, m.why = SHAPE_CAT, "Shape: " + why_shape
            continue
        # THE EVIDENCE MODEL: every signal votes, the rules adjust, the heaviest category wins (the owner, 2026-09-23)
        m.votes = gather_votes(m, cat, mo2_category_names, structural_patch_reason(m, owner_of, framework_masters, owner_tier), nexus_names)
        m.raw_votes = [tuple(v) for v in m.votes]
        cv = (community or {}).get(_core_name(m.name))
        if cv:
            leaf, users = max(cv.items(), key=lambda kv: kv[1])
            if norm(leaf) in {norm(x) for x in LEAVES}:
                m.votes = list(m.votes) + [("community", canonical(leaf), min(W_COMMUNITY_CAP, W_COMMUNITY_EACH * users),
                                            f"{users} user(s) filed this leaf")]
        if any(f.lower() in framework_masters for f, _, _ in m.plugins):
            n_dep = max(len(dependents.get(f.lower(), ())) for f, _, _ in m.plugins)
            m.votes = list(m.votes) + [("structure", "__framework__", 0.0, f"a framework: {n_dep} mods depend on its plugin")]
        decided, why, m.votes = decide(m, m.votes, cat)
        if decided:
            m.category, m.why = decided, why
            continue
        m.category, m.why = "Uncategorised", ("no Nexus page" if not m.nexus_id else f"Nexus has no category for mod {m.nexus_id}")
    by_name_ = {m.name: m for m in mods}
    # ADDONS (second pass): a mod named for another - "Northern Concept - Northern Roads", "Utenlands Nordic Tents -
    # Campfire Addon" - sits with that mod, so it takes the parent's category as a strong vote and is decided again.
    # A patch by structure stays a patch; the hard gates above are untouched.
    decided_names = {m.name: m for m in mods if m.category and not is_sep(m.name)}
    cores = {}
    for m in decided_names.values():
        c = _core_name(m.name)
        if len(c) >= 6:
            cores.setdefault(c, []).append(m)
    for m in mods:
        if is_sep(m.name) or not m.votes or norm(m.category or "") in (norm("Patches"), norm(SHAPE_CAT), norm("Test Builds"), norm("Base Game"), norm("Generated Outputs"), NODELETE_SEP.lower()):
            continue
        if m.why.startswith(("pinned", "carries the [NoDelete]", "name starts", "every plugin", "no Nexus page and", "Shape:")):
            continue
        mine = _core_name(m.name)
        parent = None
        for c, ms in cores.items():
            if c != mine and mine.startswith(c) and (parent is None or len(c) > len(_core_name(parent.name))):
                cand = min(ms, key=lambda x: len(x.name))
                if cand is not m and norm(cand.category or "") not in (norm("Patches"), norm("Test Builds"), NODELETE_SEP.lower()):
                    parent = cand
        if parent is None:
            continue
        cat = categories.get(str(m.nexus_id), "") if m.nexus_id else ""
        votes = [tuple(v) for v in m.votes] + [("addon", parent.category, 3.0, f"named for {parent.name}, which is {parent.category}")]
        decided, why, m.votes = decide(m, votes, cat)
        if decided:
            m.category, m.why = decided, why
    for m in mods:
        if m.twin and by_name_.get(m.twin) is not None and by_name_[m.twin].category:
            t = by_name_[m.twin]
            m.category, m.why = t.category, f"test build of {t.name}: sits directly under it and supersedes it"
        elif m.twin:
            m.category, m.why = "Test Builds", "test build; its official copy has no category yet"
    for m in mods:
        if m.category:
            m.group = tier_of(m.category)
            m.decided = m.category


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
    # 2026-09-23: the DECIDED category (every signal weighed), not the bare Nexus one; a mod whose MO2 category the user
    # set himself is left alone, one the updater wrote earlier from Nexus is corrected when the decision differs
    names = read_mo2_categories(instance_dir)
    for m in mods:
        if is_sep(m.name) or "missing" in m.flags or not m.category:
            continue
        if norm(m.category) in (norm(SHAPE_CAT), norm("Test Builds"), norm("Base Game"), norm("Generated Outputs"), NODELETE_SEP.lower(), norm("Uncategorised")):
            continue
        if m.category.startswith("displaced") or " block; " in (m.why or ""):
            continue
        mo2_id = catmap.get(norm(m.category))
        if not mo2_id:
            continue
        current = [names.get(c, "") for c in (m.mo2_cats or [])]
        if any(norm(c) == norm(m.category) for c in current):
            continue
        nexus_cat = categories.get(str(m.nexus_id), "") if m.nexus_id else ""
        user_set = any(c and norm(c) not in (norm(nexus_cat), "unpublished", "test") for c in current)
        if user_set:
            continue
        out.append((m.name, os.path.join(mods_dir, m.name, "meta.ini"), mo2_id, m.category))
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


def build(mods, rules=None, min_run=2):
    """The new pane: [(name, enabled)] top-first, plus the facts.

    ONE WAY TO ORDER (2026-09-23, the owner: "clean up the plugin from previous versions' logic so it is not biased"):
    every mod ranks by (tier, its category's place in the tier, today's position); a topological sort (Kahn, with a
    heap) then keeps every FACTUAL edge - a master above its dependent, a generated output last, a settings loader
    below its target, a shape refit below what it refits, the resolver's evidence about a shared file, and the user's
    own before/after/first/last rules. A mod an edge holds below its block is DISPLACED and relabelled to the block it
    lands in, with the reason. Nothing else moves a mod: no kept winners, no learned category order, no rules written
    by a previous run."""
    import heapq
    rules = [r for r in (rules or []) if "review" not in str(r.get("comment", ""))]
    real = [m for m in mods if not is_sep(m.name) and "missing" not in m.flags]
    by_name = {m.name: m for m in real}

    def rank(m):
        k = norm(m.category)
        if k == NODELETE_SEP.lower():
            return (index_tier(NODELETE_SEP), 0, m.index)
        if True:
            # tier, then the category's place in that tier's own list, then today's position. Until 2026-09-23 the
            # order inside a tier was today's position alone, and the blocks were labels stamped over runs of it -
            # 496 of 2,191 mods sat in a block of another category (the owner: "many mods seem out of place").
            # Now every category is one block; the tested same-tier override winners are kept by the keep-winners
            # edges below, which pull a winner down under its loser and relabel it there (the 'displaced' list).
            if m.twin and m.twin in by_name and by_name[m.twin] is not m:
                base = rank(by_name[m.twin])
                return (base[0], base[1], base[2] + 0.5)      # directly behind the copy it supersedes
            t = index_tier(m.category)
            names = TIERS.get(t, ())
            k = norm(m.category)
            ci = next((i for i, n in enumerate(names) if norm(n) == k), len(names))
            return (t, ci, m.index)

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
    for m in real:
        if m.twin and m.twin in by_name:
            edge(by_name[m.twin], m, f"test build supersedes {m.twin}")
    fixes = []
    for m in real:
        # which of this mod's plugins need each other mod: the mod follows that mod in the pane only when ALL its
        # plugins do - a bundled compatibility plugin (VividRoutines - Wyrmstooth.esp) or a patch hub's patches follow
        # their masters in the plugin order alone, and the mod keeps its own block (the owner, 2026-09-23)
        needs = {}
        for f, masters, _esm in m.plugins:
            for mast in masters:
                o = owner.get(mast.lower())
                if o and o is not m:
                    needs.setdefault(o.name, (o, f, mast, set()))[3].add(f.lower())
        for _on, (o, f, mast, fs) in needs.items():
            if len(fs) < len(m.plugins):
                continue
            edge(o, m, f"{f} needs its master {mast}")
            if o.index > m.index:
                fixes.append((m.name, o.name))
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
        cands = [m for m in real if m.enabled and m is not a_mod and not name_re.search(m.name) and not TAG_PATCH.search(m.name)
                 and (norm(m.name) == norm(base) or m.name.lower().startswith(base.lower() + " (") or m.name.lower().startswith(base.lower() + " - "))]
        target = min(cands, key=lambda m: len(m.name)) if cands else None
        if target is not None and target.name not in shared:
            edge(target, a_mod, f"settings loader for {target.name} (by name)")
            shared[target.name] = 0
        loader_pairs.update((a_mod.name, b) for b in shared)
        if shared:
            loaders += 1
    rule_moves = []
    rules_ignored = []

    def apply_rules(which):
        for r in which:
            a, b, kind = by_name.get(r.get("mod", "")), by_name.get(r.get("target", "")), r.get("type", "")
            if a is None or not r.get("enabled", True):
                continue
            # a rule that would close a loop against what is already known is skipped and reported, never obeyed:
            # 527 review rules written under an old order pinned settings loaders ABOVE their targets and mods after
            # generated outputs, and every one became a cycle that froze the pane (2026-09-23)
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
    # the user's own rules outrank the resolver's heuristics (never a master, output or loader edge)
    apply_rules(rules)
    # a Shape mod (a refit) must win the files it shares with the armour, weapon and clothing mods it refits
    shape_pairs = set()
    for a_mod in real:
        if a_mod.category != SHAPE_CAT or not a_mod.enabled:
            continue
        seen_ = {}
        for f in a_mod.files:
            for b_mod in owners.get(f, []):
                if b_mod is not a_mod and b_mod.enabled and b_mod.category != SHAPE_CAT and norm(b_mod.category) not in (norm("Generated Outputs"), norm("Test Builds"), NODELETE_SEP.lower()):
                    seen_[b_mod.name] = seen_.get(b_mod.name, 0) + 1
        for b_name, n in seen_.items():
            if not would_cycle(a_mod.name, b_name):
                edge(by_name[b_name], a_mod, f"shape refit: must win {n} file(s) of {b_name}")
                shape_pairs.add((a_mod.name, b_name))
    pairs = {}
    for f, ms in owners.items():
        if len(ms) < 2 or len(ms) > 40:
            continue
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                a, b = ms[i], ms[j]
                k = (a.name, b.name) if a.name < b.name else (b.name, a.name)
                pairs.setdefault(k, []).append(f)
    files_of = {m.name: set(m.files) for m in real if m.enabled}
    winners = {}
    winners_yielded = []
    resolved, undecided = [], []
    for (a, b), shared in pairs.items():
        n = len(shared)
        loser, winner = (a, b) if by_name[a].index < by_name[b].index else (b, a)
        winners[(loser, winner)] = n
        if (loser, winner) in loader_pairs or (winner, loser) in loader_pairs or (loser, winner) in shape_pairs or (winner, loser) in shape_pairs:
            continue                  # a settings loader's or a shape refit's pair is settled above
        ma, mb = by_name[a], by_name[b]
        same_tier_pair = index_tier(ma.category) == index_tier(mb.category)
        same_cat_pair = norm(ma.category) == norm(mb.category)
        verdict = resolve_conflict(ma, mb, shared, files_of)
        # name dependency and patch evidence hold across tiers (a "for X" mod belongs under X whatever their
        # categories); PBR and specificity only between mods of the SAME category, where nothing else orders them -
        # across categories the category order is the stronger evidence (2026-09-23: More Accurate Collision, an
        # Immersion mod of 4,192 files, had pulled 36 texture packs under Immersion by size alone)
        if verdict is not None and not same_cat_pair and not (verdict[2].startswith("named for") or verdict[2].startswith("a patch")):
            verdict = None
        if verdict is not None:
            w, l, why = verdict
            if would_cycle(l.name, w.name):
                winners_yielded.append((w.name, l.name, n, "resolver: " + why + " - but a master or loader edge says the opposite"))
                continue
            edge(l, w, "resolver: " + why)
            resolved.append((w.name, l.name, n, why, "as today" if w.name == winner else "flips today's order"))
            continue
        if not same_tier_pair:
            continue                  # the hierarchy decides a cross-tier pair
        undecided.append((winner, loser, n, "no evidence either way - category order decides"))
    firsts = {r.get("mod") for r in rules if r.get("type") == "first" and r.get("enabled", True)}
    lasts = {r.get("mod") for r in rules if r.get("type") == "last" and r.get("enabled", True)}

    # --- Kahn with a heap on the rank ---------------------------------------------------------------------------------
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

    # --- displaced mods take the category they land in --------------------------------------------------------------
    absorbed = []
    displaced = []                     # displacement first, so the run merging below sees every mod's final category
    cur = None
    for m in ordered:
        if m.category == NODELETE_SEP or norm(m.category) in FIXED_BLOCKS:
            continue
        gi = rank(m)[0]
        if cur is None:
            cur = m
            continue
        if rank(m)[:2] < rank(cur)[:2] and norm(m.category) != norm(cur.category):
            # held here by an edge (a lower tier, or an earlier category of the same tier): name the latest
            # predecessor that holds it. Until 2026-09-23 only a tier change counted, so a texture pack held under
            # Northern Roads was listed as a nameless minority of the Audio block instead of a displacement with its reason
            holders = [x for x in above.get(m.name, ()) if x in by_name]
            why = ""
            if holders:
                h = max(holders, key=lambda x: ordered.index(by_name[x]))
                why = reason.get((h, m.name), "")
            displaced.append((m.name, m.category, cur.category, why))
            m.category, m.why = cur.category, f"displaced under '{cur.category}': {why} ({m.why})"
        else:
            cur = m

    if True:
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
        # ONE BLOCK PER CATEGORY NAME (the owner, 2026-09-23: "no separator should have duplicate named separators
        # like name then name(1)"). The category's largest run keeps the separator; every other run of it, whatever
        # its size, is absorbed into a neighbouring block and its mods are listed as minorities there. A category too
        # small for a block of its own (fewer than min_run mods in the list) is absorbed entirely.
        cat_total = {}
        for r in runs:
            cat_total[norm(r[0])] = cat_total.get(norm(r[0]), 0) + len(r[1])
        largest = {}                       # category -> its biggest run: the one block it gets
        for r in runs:
            key_ = norm(r[0])
            if key_ not in largest or len(r[1]) > len(largest[key_][1]):
                largest[key_] = r
        for r in runs:
            key_ = norm(r[0])
            if key_ in FIXED_BLOCKS:
                continue
            if largest[key_] is r:
                if len(r) == 2 and cat_total.get(key_, 0) >= min_run and len(r[1]) < min_run:
                    r.append("keep")
            elif len(r) == 2:
                r.append("absorb")

        def same_tier(a, b):
            if a is None or b is None:
                return True
            if norm(a[0]) in FIXED_BLOCKS or norm(b[0]) in FIXED_BLOCKS:
                return False
            return run_tier(a) == run_tier(b)
        while len(runs) > 1:
            def pick_key(j):
                r = runs[j]
                if norm(r[0]) in FIXED_BLOCKS or (len(r) > 2 and r[2] == "keep"):
                    return (10**6, j)
                if len(r) > 2 and r[2] == "absorb":
                    return (len(r[1]), j)             # a second run of a category: absorbed whatever its size
                return (len(r[1]) if len(r[1]) < min_run else 10**6, j)
            i = min(range(len(runs)), key=pick_key)
            if pick_key(i)[0] >= 10**6:
                break
            left = runs[i - 1] if i > 0 and same_tier(runs[i - 1], runs[i]) else None
            right = runs[i + 1] if i + 1 < len(runs) and same_tier(runs[i], runs[i + 1]) else None
            if left is None and right is None:
                # a short run alone in its tier keeps its own separator; mark it so the loop moves on
                if len(runs[i]) > 2:
                    runs[i][2] = "keep"
                else:
                    runs[i].append("keep")
                continue
            into = left if (right is None or (left is not None and len(left[1]) >= len(right[1]))) else right
            if into is left:
                left[1].extend(runs[i][1])
            else:
                right[1][0:0] = runs[i][1]
            del runs[i]
            # merging can make two same-category runs adjacent: join them (the joined run keeps a 'keep' if either had it)
            j = 0
            while j + 1 < len(runs):
                if norm(runs[j][0]) == norm(runs[j + 1][0]):
                    keep_ = (len(runs[j]) > 2 and runs[j][2] == "keep") or (len(runs[j + 1]) > 2 and runs[j + 1][2] == "keep")
                    runs[j][1].extend(runs[j + 1][1])
                    del runs[j + 1]
                    runs[j][2:] = ["keep"] if keep_ else []
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
    # --- separators: one tier header per tier, one block per category ------------------------------------------------
    rows = []
    cur_header, cur_cat = None, None
    written_headers = set()
    written_mains = set()
    block_uses = {}
    for m in ordered:
        k = norm(m.category)
        if k == NODELETE_SEP.lower():
            header = None
        else:
            header = TIER_HEADERS[m.group if m.group in TIER_HEADERS else index_tier(m.category)]
        if header != cur_header and header is not None:
            if header not in written_headers:           # a displaced mod can bring a tier back: one header each
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
                if norm(m.category) in block_uses:
                    pass                    # never a second separator of the same name: the mods continue under the last block
                else:
                    block_uses[norm(m.category)] = 1
                    main = MAIN_OF.get(norm(m.category))
                    if main and main not in written_mains:      # the empty main separator heads its sub-blocks
                        written_mains.add(main)
                        rows.append((sep_name(main), False))
                    rows.append((sep_name(m.category), False))
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
            tw, tl = index_tier(by_name[w].category), index_tier(by_name[l].category)
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
        if index_tier(ml.category) == index_tier(mw.category) and len(mw.files) > len(ml.files) and mw.files and ml.files:
            advice.append((w, l, n, f"the larger mod ({len(mw.files)} files) wins over the smaller ({len(ml.files)}) - check it is meant to"))
    advice.sort(key=lambda x: -x[2])
    new_seps = {nm for nm, _ in rows if is_sep(nm)}
    old_seps = {m.name for m in mods if is_sep(m.name)}
    return rows, {"fixes": fixes, "rule_moves": rule_moves, "flips": flips, "conflict_pairs": len(pairs),
                  "displaced": displaced, "absorbed": absorbed, "advice": advice, "cycles": [m.name for m in cycles], "cycle_edges": cycle_edges, "rules_ignored": rules_ignored, "winners_yielded": winners_yielded, "resolved": resolved, "undecided": undecided,
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
    # rules an earlier build's Review tab wrote ("kept today's winner") are retired to a file beside the live one and
    # never applied again: the order stands on evidence (the owner, 2026-09-23). Nothing is deleted.
    review = [r for r in ours["rules"] if "review" in str(r.get("comment", ""))]
    if review:
        try:
            rp = os.path.join(profile_dir, RULES_FILE.replace(".json", ".review-retired.json"))
            old = []
            if os.path.isfile(rp):
                try:
                    old = json.load(open(rp, encoding="utf-8"))
                except (OSError, ValueError):
                    old = []
            json.dump(old + review, open(rp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            ours["rules"] = [r for r in ours["rules"] if "review" not in str(r.get("comment", ""))]
            json.dump(ours, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        except OSError:
            pass
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


EXPECTATIONS_FILE = "expectations.json"


def check_expectations(mods):
    """[(mod, expected, got, ok)] against expectations.json beside this file: the owner's rulings as a test set."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXPECTATIONS_FILE)
    try:
        exp = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    by = {m.name: m for m in mods if not is_sep(m.name)}
    out = []
    for name, want in exp.items():
        if name.startswith("_"):
            continue
        m = by.get(name) or next((mm for k, mm in by.items() if name.endswith("*") and k.startswith(name[:-1])), None)
        if m is None:
            continue
        got = m.decided or m.category or ""
        placed = m.category or ""
        wants = want if isinstance(want, list) else [want]
        ok = False
        for w in wants:
            if w.startswith("!"):
                ok = norm(got) != norm(w[1:])
            elif norm(got) == norm(w):
                ok = True
            if ok:
                break
        shown = got if norm(placed) == norm(got) else f"{got} (placed under {placed}: {(m.why or '').split(':', 1)[0]})"
        out.append((name, " | ".join(wants), shown, ok))
    return out


def collect_verdicts(mods, mo2_names):
    """The user's verdicts: every mod whose MO2 category HE set (one of the tree's leaves, not a Nexus name - the same
    test gather_votes applies) and which the evidence alone - every vote but his - would have placed elsewhere. Each row
    is exactly what DISCLOSURE says and nothing more."""
    out = []
    for m in mods:
        if is_sep(m.name) or not m.raw_votes:
            continue
        user = next((v for v in m.raw_votes if v[0] == "mo2" and norm(v[1]) != norm("Test Builds")), None)
        if user is None:
            continue
        evidence = [v for v in m.raw_votes if v[0] not in ("mo2", "community")]
        cat, why, adjusted = decide(m, evidence)
        if not cat or norm(cat) == norm(user[1]):
            continue
        rec = m.records or {}
        top = sorted(adjusted, key=lambda v: -v[2])[:4]
        out.append({
            "mod": m.name, "nexus_id": m.nexus_id or 0, "user_leaf": canonical(user[1]), "evidence_leaf": cat,
            "evidence": [f"{v[0]} {v[1]} {v[2]:.1f} - {v[3]}" for v in top],
            "summary": {"plugins": len(m.plugins), "dll": any(f.endswith(".dll") for f in m.files or ()),
                        "hkx": any(f.endswith(".hkx") for f in m.files or ()), "files": len(m.files or ()),
                        "records": dict(sorted(rec.items(), key=lambda kv: -kv[1])[:6])},
        })
    return out


def verdicts_payload(rows):
    return {"plugin": "MO2 Modlist Manager", "version": __version__, "taxonomy": len(LEAVES),
            "sent": time.strftime("%Y-%m-%d"), "verdicts": rows}


def _issue_url(payload, limit=2500):
    """A prefilled GitHub issue for the browser: as many rows as fit the URL, the rest in the saved file."""
    rows = payload["verdicts"]
    keep = []
    for r in rows:
        trial = dict(payload, verdicts=keep + [r])
        if len(json.dumps(trial, ensure_ascii=False, separators=(",", ":"))) > limit:
            break
        keep.append(r)
    body = (f"Verdicts from MO2 Modlist Manager {__version__}: {len(keep)} of {len(rows)} mod(s)"
            + ("" if len(keep) == len(rows) else " - the rest are in the saved file the plugin named; drag it into this issue")
            + "\n\n```json\n" + json.dumps(dict(payload, verdicts=keep), ensure_ascii=False, separators=(",", ":")) + "\n```")
    q = urllib.parse.urlencode({"labels": VERDICTS_LABEL, "title": f"Verdicts: {len(rows)} mod(s)", "body": body})
    return VERDICTS_ISSUE_NEW + "?" + q, len(keep)


def send_verdicts(rows, cache_dir, endpoint="", log=None):
    """Save the payload beside the cache, then either POST it to the drop box (an https address the user set) or
    build the GitHub issue URL for the browser. Returns (mode, message, url): mode is 'posted', 'browser' or 'failed'."""
    payload = verdicts_payload(rows)
    folder = os.path.join(cache_dir, "verdicts-sent")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime("verdicts-%Y%m%d-%H%M%S.json"))
    json.dump(payload, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if endpoint and endpoint.lower().startswith("https://"):
        try:
            req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "User-Agent": "MO2ModlistManager/" + __version__})
            with urllib.request.urlopen(req, timeout=20) as fh:
                code = fh.status
            if log:
                log(f"verdicts: {len(rows)} row(s) posted to the drop box (HTTP {code}); copy at {path}")
            return "posted", f"{len(rows)} verdict(s) sent (HTTP {code}). A copy is at {path}.", ""
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if log:
                log(f"verdicts: post failed ({exc!r}); copy at {path}")
            return "failed", f"Sending failed: {exc}. The file is at {path} - post it as a GitHub issue instead.", ""
    url, kept = _issue_url(payload)
    if log:
        log(f"verdicts: {len(rows)} row(s) saved to {path}; GitHub issue prepared with {kept} of them")
    note = "" if kept == len(rows) else f" Only {kept} of {len(rows)} fit the prefilled issue - drag the saved file into it."
    return "browser", f"A GitHub issue opens in your browser with the verdicts prefilled; post it to send.{note} Saved: {path}", url


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_ATTACHMENT = re.compile(r"https://github\.com/user-attachments/files/[^\s)\]]+\.json", re.I)


def _get_json(url, log=None):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MO2ModlistManager/" + __version__, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as fh:
            return json.loads(fh.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        if log:
            log(f"verdicts: fetch {url[:80]} failed ({exc!r})")
        return None


def _payload_rows(obj):
    """Rows from a payload, a bare list of rows, or a drop box's {"payloads": [...]} / [...]."""
    if isinstance(obj, dict):
        if isinstance(obj.get("verdicts"), list):
            return [r for r in obj["verdicts"] if isinstance(r, dict) and r.get("mod") and r.get("user_leaf")]
        if isinstance(obj.get("payloads"), list):
            return [r for pl in obj["payloads"] for r in _payload_rows(pl)]
    if isinstance(obj, list):
        rows = []
        for x in obj:
            if isinstance(x, dict) and x.get("mod") and x.get("user_leaf"):
                rows.append(x)
            else:
                rows.extend(_payload_rows(x))
        return rows
    return []


def fetch_community_verdicts(cache_dir, endpoint="", log=None):
    """The receiving end (the owner's copy): read every 'verdicts' issue on the repo, the drop box if one is set, and
    any payload file dropped into the inbox folder; pool them as {core name: {leaf: distinct submitters}} and write
    VERDICTS_FILE. Submitters are counted, never stored. Returns a summary line."""
    pooled = {}          # core -> leaf -> set(submitter key)
    n_items = 0

    def add(rows, who):
        nonlocal n_items
        for r in rows:
            leaf = canonical(str(r.get("user_leaf", "")))
            if norm(leaf) not in {norm(x) for x in LEAVES}:
                continue
            core = _core_name(str(r.get("mod", "")))
            if len(core) < 4:
                continue
            pooled.setdefault(core, {}).setdefault(leaf, set()).add(who)
            n_items += 1
    issues = _get_json(f"{VERDICTS_ISSUES_API}?labels={VERDICTS_LABEL}&state=all&per_page=100", log) or []
    n_issues = 0
    for it in issues if isinstance(issues, list) else []:
        body = it.get("body") or ""
        who = f"issue:{it.get('number')}"
        rows = []
        for blk in _JSON_BLOCK.findall(body):
            try:
                rows.extend(_payload_rows(json.loads(blk)))
            except ValueError:
                continue
        for url in _ATTACHMENT.findall(body):
            rows.extend(_payload_rows(_get_json(url, log) or {}))
        if rows:
            n_issues += 1
            add(rows, who)
    n_box = 0
    if endpoint and endpoint.lower().startswith("https://"):
        got = _get_json(endpoint, log)
        if got is not None:
            items = got.get("payloads") if isinstance(got, dict) and isinstance(got.get("payloads"), list) else (got if isinstance(got, list) else [got])
            for i, pl in enumerate(items):
                rows = _payload_rows(pl)
                if rows:
                    n_box += 1
                    add(rows, f"box:{i}")
    n_files = 0
    inbox = os.path.join(cache_dir, VERDICTS_INBOX)
    if os.path.isdir(inbox):
        for f in sorted(os.listdir(inbox)):
            if f.lower().endswith(".json"):
                try:
                    rows = _payload_rows(json.load(open(os.path.join(inbox, f), encoding="utf-8")))
                except (OSError, ValueError):
                    continue
                if rows:
                    n_files += 1
                    add(rows, f"file:{f}")
    out = {core: {leaf: len(who) for leaf, who in leaves.items()} for core, leaves in pooled.items()}
    os.makedirs(cache_dir, exist_ok=True)
    json.dump(out, open(os.path.join(cache_dir, VERDICTS_FILE), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    msg = (f"Community verdicts: {len(out)} mod(s) from {n_issues} issue(s), {n_box} drop-box payload(s), {n_files} inbox file(s) "
           f"- {n_items} row(s) pooled into {VERDICTS_FILE}")
    if log:
        log(msg)
    return msg


def load_community(cache_dir):
    try:
        d = json.load(open(os.path.join(cache_dir, VERDICTS_FILE), encoding="utf-8"))
        return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def run(instance_dir, profile, cache_dir, domain="skyrimspecialedition", progress=None, log=None, min_run=2):
    """Everything up to (not including) writing. Returns a dict the dialog and the offline runner both use."""
    mods_dir = os.path.join(instance_dir, "mods")
    ml = os.path.join(instance_dir, "profiles", profile, "modlist.txt")
    rows, header = read_modlist(ml)
    mods = scan(mods_dir, rows, progress)
    test_pairs = pair_test_builds(mods)
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
    community = load_community(cache_dir)
    mo2_names = read_mo2_categories(instance_dir)
    place(mods, cats, mo2_names, under, ours.get("pins"), community)
    new_rows, facts = build(mods, ours.get("rules"), min_run)
    facts["expectations"] = check_expectations(mods)
    facts["community"] = len(community)
    facts["verdicts"] = collect_verdicts(mods, mo2_names)
    by_name = {m.name: m for m in mods}
    plugins = plugin_order(new_rows, by_name, theirs)
    return {"mods": mods, "rows": new_rows, "header": header, "facts": facts, "moves": diff(mods, new_rows),
            "category_updates": plan_mo2_category_updates(mods, cats, instance_dir),
            "plugin_groups": plugin_groups(new_rows, by_name), "bpm": bpm_installed(instance_dir),
            "plugin_state": plugin_state, "test_pairs": test_pairs,
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
        from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
        from PyQt6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QShortcut
        from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView,
                                     QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
                                     QToolButton, QTreeView, QVBoxLayout, QWidget)
    except ImportError:
        from PyQt5.QtCore import QSize, Qt, QTimer, QUrl
        from PyQt5.QtGui import QDesktopServices, QIcon, QKeySequence
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView,
                                     QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
                                     QToolButton, QTreeView, QVBoxLayout, QWidget)
        from PyQt5.QtWidgets import QAction

    class VerdictsDialog(QDialog):
        """Share verdicts: the disclosure, every row that would leave, one Send. Nothing is sent from anywhere else."""
        def __init__(self, plugin, rows, parent=None):
            super().__init__(parent)
            self._p, self._rows = plugin, rows
            self.setWindowTitle("Share verdicts")
            self.resize(900, 560)
            v = QVBoxLayout(self)
            note = QLabel(DISCLOSURE)
            note.setWordWrap(True)
            v.addWidget(note)
            self.t = QTableWidget(0, 3)
            self.t.setHorizontalHeaderLabels(["Mod", "Your category", "The evidence said"])
            self.t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.t.setRowCount(len(rows))
            for i, r in enumerate(rows):
                for j, val in enumerate((r["mod"], r["user_leaf"], r["evidence_leaf"])):
                    self.t.setItem(i, j, QTableWidgetItem(str(val)))
            v.addWidget(self.t, 1)
            self.cb_auto = QCheckBox("Share automatically after each Apply")
            self.cb_auto.setChecked(bool(self._p.setting("share_after_apply", False)))
            v.addWidget(self.cb_auto)
            self.status = QLabel("" if rows else "No verdicts: every category you set yourself agrees with the evidence, or none is set.")
            self.status.setWordWrap(True)
            v.addWidget(self.status)
            b = QHBoxLayout()
            b.addStretch(1)
            self.b_copy = QPushButton("Copy JSON")
            self.b_copy.setToolTip("Copy the full payload to the clipboard, to paste into an issue yourself")
            self.b_send = QPushButton("Send")
            self.b_cancel = QPushButton("Close")
            for x in (self.b_copy, self.b_send, self.b_cancel):
                b.addWidget(x)
            v.addLayout(b)
            self.b_copy.clicked.connect(self.copy_json)
            self.b_send.clicked.connect(self.send)
            self.b_cancel.clicked.connect(self.close)
            self.cb_auto.toggled.connect(lambda on: self._p.set_setting("share_after_apply", bool(on)))
            self.b_send.setEnabled(bool(rows))
            self.b_copy.setEnabled(bool(rows))

        def copy_json(self):
            try:
                QApplication.clipboard().setText(json.dumps(verdicts_payload(self._rows), ensure_ascii=False, indent=1))
                self.status.setText(f"{len(self._rows)} verdict(s) copied as JSON.")
            except Exception as exc:  # noqa: BLE001
                self.status.setText(f"Copy failed: {exc}")

        def send(self):
            self.b_send.setEnabled(False)
            self.status.setText("Sending...")
            QApplication.processEvents()
            mode, msg, url = self._p.send_verdicts(self._rows)
            self.status.setText(msg)
            if mode == "browser" and url:
                QDesktopServices.openUrl(QUrl(url))
            self.b_send.setEnabled(mode == "failed")

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
            self.t_conf = self._table(["Wins", "Over", "Shared files", "Why"])
            self.t_conf.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.t_conf.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.t_place = self._table(["Mod", "Tier", "Separator", "Why"])
            self.tabs.addTab(self.t_moves, "Moves")
            self.tabs.addTab(self.t_seps, "Separators")
            self.tabs.addTab(self.t_disp, "Minorities / displaced")
            conf_page = QWidget()
            cl = QVBoxLayout(conf_page)
            cl.addWidget(QLabel("Every file conflict the resolver could not decide from evidence (top), then the ones it "
                                "flipped against today's order. Information only: nothing here writes a rule. A pair the "
                                "category order gets wrong is a missing piece of evidence - add it to the model, or write "
                                "a rule of your own on the Rules tab."))
            cl.addWidget(self.t_conf, 1)
            self.tabs.addTab(conf_page, "Review")
            self.tabs.addTab(self.t_place, "Every placement")
            self.t_plug = self._table(["Plugin", "Mod", "Action", "Why"])
            self.tabs.addTab(self.t_plug, "Plugins")
            self.tabs.addTab(self._rules_tab(), "Rules")
            opts = QHBoxLayout()
            opts.addWidget(QLabel("Order: tier by evidence, general before specific; masters, outputs, loaders, refits and your rules enforced."), 3)
            opts.addWidget(QLabel("Smallest block:"))
            self.sp_run = QSpinBox()
            self.sp_run.setRange(1, 60)
            self.sp_run.setValue(2)
            opts.addWidget(self.sp_run)
            root.insertLayout(1, opts)
            self.sp_run.valueChanged.connect(lambda _v: self.compute())
            self.status = QLabel()
            self.status.setWordWrap(True)
            root.addWidget(self.status)
            buttons = QHBoxLayout()
            buttons.addStretch(1)
            self.b_cats = QPushButton("Write decided categories to MO2")
            self.b_cats.setToolTip("Write each mod's DECIDED category (every signal weighed: Nexus, records, files, its own words) into its meta.ini as its MO2 category. A category you set yourself is left alone.")
            self.b_cats.clicked.connect(self.update_categories)
            buttons.addWidget(self.b_cats)
            self.b_verdicts = QPushButton("Fetch community verdicts" if self._p.is_owner() else "Share verdicts...")
            self.b_verdicts.setToolTip("Read the verdicts other users have shared and add them to the evidence as a vote" if self._p.is_owner()
                                       else DISCLOSURE)
            self.b_verdicts.clicked.connect(self.verdicts)
            buttons.addWidget(self.b_verdicts)
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
            # copy and paste (the owner, 2026-09-23): whole rows select; Ctrl+C copies the selected rows as tab-separated
            # text; the right-click menu offers the rows, the mod names alone, or the whole table
            if t.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection:
                t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            t.customContextMenuRequested.connect(lambda pos, tt=t: self._table_menu(tt, pos))
            sc = QShortcut(QKeySequence.StandardKey.Copy, t)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(lambda tt=t: self._copy_table(tt, "rows"))
            return t

        def _copy_table(self, t, what):
            """what: 'rows' (selected, with the header when several), 'names' (first column of the selection), 'all'."""
            cols = t.columnCount()
            header = [t.horizontalHeaderItem(j).text() if t.horizontalHeaderItem(j) else "" for j in range(cols)]
            rows = sorted({i.row() for i in t.selectedIndexes()}) if what != "all" else list(range(t.rowCount()))
            if not rows and what != "all":
                rows = list(range(t.rowCount()))

            def cell(i, j):
                it = t.item(i, j)
                return (it.text() if it else "").replace("\t", " ").replace("\r", " ").replace("\n", " ")
            if what == "names":
                lines = [cell(i, 0) for i in rows]
            else:
                lines = ["\t".join(cell(i, j) for j in range(cols)) for i in rows]
                if len(rows) > 1 or what == "all":
                    lines.insert(0, "\t".join(header))
            QApplication.clipboard().setText("\n".join(lines))
            self.status.setText(f"Copied {len(rows)} row(s)" + (" (mod names only)" if what == "names" else "") + " to the clipboard.")

        def _table_menu(self, t, pos):
            menu = QMenu(t)
            n = len({i.row() for i in t.selectedIndexes()})
            menu.addAction(f"Copy selected row{'s' if n != 1 else ''} ({n})\tCtrl+C").triggered.connect(lambda _=False: self._copy_table(t, "rows"))
            menu.addAction(f"Copy mod name{'s' if n != 1 else ''} only").triggered.connect(lambda _=False: self._copy_table(t, "names"))
            menu.addAction(f"Copy all {t.rowCount()} rows with header").triggered.connect(lambda _=False: self._copy_table(t, "all"))
            menu.exec(t.viewport().mapToGlobal(pos))

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
                self._result = self._p.compute(progress, self.sp_run.value())
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
                f"{len(r['facts']['absorbed'])} in a block of another category, {len(r['facts']['displaced'])} displaced by a master, loader, refit or rule - "
                f"{len(r['facts'].get('resolved', []))} file conflicts decided by evidence, {len(r['facts'].get('undecided', []))} left to category order, "
                f"{len(r['facts'].get('rules_ignored', []))} rule(s) ignored as contradictory - {len(r['plugins'])} plugins ordered"
                f" ({len(r.get('plugin_state', {}).get('activate', []))} to activate, {len(r.get('plugin_state', {}).get('to_optional', []))} to Optional ESPs, "
                f"{len(r.get('plugin_state', {}).get('from_optional', []))} back from Optional ESPs)"
                + (f" into {len(set(r.get('plugin_groups', {}).values()))} BPM groups" if r.get("bpm") else " (no Bethesda Plugin Manager: no groups)")
                + (f" - {r['facts'].get('community', 0)} mod(s) carry community verdicts" if r['facts'].get('community') else "")
                + (f" - {len(r['facts'].get('verdicts', []))} verdict(s) of yours the evidence disagrees with" if r['facts'].get('verdicts') else ""))
            self._fill(self.t_moves, [(n, (o or "")[:-len("_separator")] if o else "", (w or "")[:-len("_separator")] if w else "", a, b) for n, o, w, a, b in r["moves"]])
            self._fill(self.t_seps, [(s[:-len("_separator")], "created") for s in r["facts"]["created"]] + [(s[:-len("_separator")], "retired (folder moved to the backup)") for s in r["facts"]["retired"]])
            self._fill(self.t_disp, [(a, b, c, "") for a, b, c in r["facts"]["absorbed"]] + r["facts"]["displaced"])
            f = r["facts"]
            self._fill(self.t_conf, f.get("undecided", []) + [(w, l, n, "resolver flipped today's order: " + why) for w, l, n, why, tag in f.get("resolved", []) if tag != "as today"])
            self._fill(self.t_place, [(m.name, f"{index_tier(m.category)} " + TIER_HEADERS.get(index_tier(m.category), "NoDelete").strip("- ").title(), m.category, m.why) for m in mods])
            self._fill(self.t_rules, self._rules_rows())
            ps = r.get("plugin_state", {})
            self._fill(self.t_plug, [(f, m, "activate", w) for f, m, w in ps.get("activate", [])]
                       + [(f, m, "move to Optional ESPs", w) for f, m, w in ps.get("to_optional", [])]
                       + [(f, m, "back from Optional ESPs, activate", w) for f, m, w in ps.get("from_optional", [])])
            n_plug = sum(len(ps.get(k, [])) for k in ("activate", "to_optional", "from_optional"))
            self.tabs.setTabText(self.tabs.indexOf(self.t_plug), f"Plugins ({n_plug})" if n_plug else "Plugins")
            self.b_apply.setEnabled(bool(r["moves"] or r["facts"]["created"] or r["facts"]["retired"] or n_plug))
            self.status.setText("Nothing is written until Apply. Apply backs up modlist.txt, plugins.txt, loadorder.txt and the retired separators first.")

        def verdicts(self):
            if not self._result:
                return
            if self._p.is_owner():
                self.status.setText("Fetching community verdicts...")
                QApplication.processEvents()
                try:
                    msg = fetch_community_verdicts(self._p._cache_dir(), self._p.setting("verdicts_endpoint", ""), self._p._log)
                except Exception as exc:  # noqa: BLE001
                    self._p._log(f"fetch verdicts failed: {exc!r}")
                    self.status.setText(f"Fetch failed: {exc}")
                    return
                self.status.setText(msg + " - computing again with them as a vote.")
                QApplication.processEvents()
                self.compute()
                return
            rows = self._result["facts"].get("verdicts", [])
            VerdictsDialog(self._p, rows, self).exec()

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
                return
            rows = self._result["facts"].get("verdicts", [])
            if rows and not self._p.is_owner() and self._p.setting("share_after_apply", False):
                mode, msg, url = self._p.send_verdicts(rows)
                self.status.setText(self.status.text() + " " + msg)
                if mode == "browser" and url:
                    QDesktopServices.openUrl(QUrl(url))

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
            return [
                mobase.PluginSetting("role", "user (share your verdicts) or owner (the receiving end: fetch and pool them)", "user"),
                mobase.PluginSetting("share_after_apply", "Share verdicts automatically after each Apply (off: only from the button)", False),
                mobase.PluginSetting("verdicts_endpoint", "https address of a drop box to POST verdicts to / to fetch pooled payloads from; "
                                     "empty: a prefilled GitHub issue opens in your browser instead", ""),
                mobase.PluginSetting("disclosed", "The sharing disclosure has been shown once at startup", False),
            ]

        def setting(self, key, default):
            try:
                v = self._organizer.pluginSetting(self.name(), key)
                return default if v is None else v
            except Exception:  # noqa: BLE001
                return default

        def set_setting(self, key, value):
            try:
                self._organizer.setPluginSetting(self.name(), key, value)
            except Exception as exc:  # noqa: BLE001
                self._log(f"setting {key}: {exc!r}")

        def is_owner(self):
            return str(self.setting("role", "user")).strip().lower() == "owner"

        def send_verdicts(self, rows):
            try:
                return send_verdicts(rows, self._cache_dir(), str(self.setting("verdicts_endpoint", "") or ""), self._log)
            except Exception as exc:  # noqa: BLE001
                self._log(f"send verdicts failed: {exc!r}")
                return "failed", f"Sending failed: {exc}", ""

        def disclose_once(self):
            """The privacy note, once, before the first dialog on a user's copy: sharing is off until turned on."""
            if self.is_owner() or self.setting("disclosed", False):
                return
            try:
                QMessageBox.information(self._parent, "MO2 Modlist Manager - sharing verdicts",
                                        DISCLOSURE + "\n\nYou will find it under 'Share verdicts...' in the dialog. Nothing is shared until you press Send there.")
            except Exception as exc:  # noqa: BLE001
                self._log(f"disclosure: {exc!r}")
            self.set_setting("disclosed", True)

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

        def compute(self, progress=None, min_run=2):
            org = self._organizer
            org.refresh(True)      # so modlist.txt on disk is what the pane shows
            domain = "skyrimspecialedition"
            try:
                domain = org.managedGame().gameNexusName() or domain
            except Exception:  # noqa: BLE001
                pass
            return run(org.basePath(), org.profileName(), self._cache_dir(), domain, progress, self._log, min_run)

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
                self.disclose_once()
                RulerDialog(self, self._parent).exec()
            except Exception as exc:  # noqa: BLE001
                self._log(f"display failed: {exc!r}")

    def createPlugin():
        return MO2ModlistManager()


if __name__ == "__main__" and mobase is None:       # offline dry run: python MO2ModlistManager.py <instance> <profile> <cache dir>
    # (MO2 executes a plugin file with __name__ == "__main__" too - the mobase check keeps this block out of its way)
    import sys
    if len(sys.argv) < 4:
        raise SystemExit("usage: MO2ModlistManager.py <instance dir> <profile> <cache dir>")
    inst, prof, cache = sys.argv[1], sys.argv[2], sys.argv[3]
    res = run(inst, prof, cache, log=print)
    out = {"summary": res["nexus"], "moves": res["moves"], "facts": res["facts"], "plugins": res["plugins"],
           "plugin_groups": res["plugin_groups"],
           "rows": res["rows"], "placements": [(m.name, m.category, m.why) for m in res["mods"] if not is_sep(m.name)],
           "votes": {m.name: m.votes for m in res["mods"] if not is_sep(m.name) and m.votes}}
    json.dump(out, open(os.path.join(cache, "dry-run.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    out["plugin_state"] = res["plugin_state"]
    out["test_pairs"] = res.get("test_pairs", [])
    json.dump(out, open(os.path.join(cache, "dry-run.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    ps = res["plugin_state"]
    ex = res["facts"].get("expectations", [])
    if ex:
        ok = sum(1 for e in ex if e[3])
        print(f"expectations: {ok} of {len(ex)} rulings met")
        for name, want, got, good in ex:
            if not good:
                print(f"   MISS  {name[:48]:48s} wanted {want[:44]:44s} got {got[:60]}")
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
