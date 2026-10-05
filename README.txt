MO2 Modlist Manager
===================
Version 1.1.3

A Mod Organizer 2 plugin that sorts the whole left pane for you: it generates the separators, places every mod under
the category its own evidence decides, puts masters above the mods that need them, and makes the plugin list follow
the pane. Nothing is written until you press Apply, Apply backs up the profile's lists first, and any backup can
be restored.

THIS IS NOT A MOD. Do not install it with the mod manager.

HOW A MOD IS PLACED
-------------------
A mod is placed by what it contains and changes, not by its Nexus category or where it sits today:
  - what the folder ships: a DLL, animations, sound, meshes and textures, and which asset paths they sit under;
  - what its plugins add or alter: the record groups, and the cells and worldspaces they add or edit;
  - what the mod says about itself: its name, its plugins' descriptions, its readme and FOMOD info;
  - its structure: plugins built on other mods (a patch), a master many mods depend on (a framework), a name that
    says it is an addon of another mod in the list;
  - a category you set yourself in MO2, if it names one of the manager's categories - your word, and decisive (the
    categories the manager's own category button wrote are not counted as yours).
Nexus categories are not used and Nexus is never contacted. The "Every placement" tab shows every mod's block and
what it was placed by.

THE ORDER
---------
Tiers from what everything stands on to what finishes the list: base game and engine, interface, characters, the
world, gameplay systems and animation, content, patches, test builds, generated outputs, optional addons. Inside
them:
  - every block is specific: no block is "general", "other" or "miscellaneous". Whole-game baseline
    packs (a static mesh improvement, a vanilla texture cleanup) load first in the world tier so everything after
    them wins; every other art mod goes with the thing it is art for - furniture, clutter, a town, an interior, a
    weapon, a face. Gameplay splits into difficulty and progression, survival and camping, travel, inventory and
    equipment, combat, stealth, economy and optional tweaks; location overhauls into towns, cities, interiors,
    strongholds and castles, and the wilderness;
  - a mod whose content is all inside BSA archives is read from the archives' file lists, so it is placed by what it
    holds; "Uncategorised" is left only for a mod with nothing at all to read;
  - cubemap packs load after every equipment block, so they apply to the armour and weapons;
  - the world runs broad to specific - weather, landscape, water, architecture, towns and cities, roads, trees,
    grass, plants - and lighting loads after the meshes it re-authors;
  - fixes are filed by what they overwrite (plugin, script, SKSE or mesh fixes); an SKSE-only tweak of the world or
    items has a block of its own, an SKSE-only gameplay or combat system keeps its subject;
  - a big location or quest mod with ten or more mods named for it gets a separator of its own;
  - patches naming several mods load after all of them; a patch whose targets share one block stays in it;
  - physics after hair and body; icon packs after the UI overhaul (never a font mod - the overhaul's fontconfig wins);
  - [Addon], [Optional] and [Ultrawide] variants after the generated outputs, so switching one on always wins;
  - inside a block: a mod's addons and patches after it, a family together with its patch collection last, the
    smaller or more specific mod after the bigger one, a complex-material or parallax version after the plain one,
    and alphabetical where nothing else decides. Today's position is never used, so the result does not depend on
    the order your list starts in.

REQUIREMENTS
------------
Mod Organizer 2 2.5.x (tested on 2.5.2), for Skyrim Special Edition.

INSTALLATION
------------
Copy plugins\MO2ModlistManager.py and plugins\MO2ModlistManager.png into your MO2 folder's "plugins" folder, next to
the other .py plugins, and restart MO2. The button appears on the toolbar ("Generate separators and place every mod
in order"). To remove it, delete the two files and the plugins\data\MO2ModlistManager folder.

USE
---
Press the toolbar button. The manager reads the list and shows its plan; nothing has changed yet.
  - Separators: every separator it would create and retire.
  - Moves: every mod that changes separator or line, and why.
  - Minorities / displaced: mods held in another block by a master or a patch, with the reason.
  - Every placement: every mod's category and all of its votes.
  - Plugins: the plugin order it would write, and plugins it would move into or out of Optional ESPs.
  - Review: conflicting pairs the evidence could not decide - write a rule for the ones you care about.
  - Rules: your own before / after / first / last rules and pins; they rank above the evidence, never above a
    master, a generated output or a settings loader. The pins learned from mods you moved are listed here too, as
    "pin (learned)" (see MOVING A MOD BY HAND).
  - Settings: switches for what Apply does on its own, each saved as soon as it changes -
      Move plugins that cannot load to Optional ESPs (off: they stay in the right pane, unticked),
      Bring optional plugins back when their masters arrive,
      Write Bethesda Plugin Manager groups,
      Write the verdicts file after each Apply,
      Learn a rule from each mod you move to another separator.
    All on by default. The same switches are on MO2's Settings > Plugins page.
Apply writes the plan: modlist.txt, plugins.txt and loadorder.txt, new separators (in your separators' colour),
retired separators moved to the backup, and Bethesda Plugin Manager groups when that plugin is installed. Every
Apply keeps a backup of the lists under plugins\data\MO2ModlistManager\backups\<date-time>\.
"Write decided categories to MO2" stores each mod's decided category in its meta.ini as its MO2 category; a category
you set yourself is left alone.

MO2 CATEGORIES
--------------
"Write decided categories to MO2" gives every mod that has no MO2 category the block the manager placed it by, as its
MO2 category - created in MO2 when it is new. A category you set yourself is never touched; the ones this button wrote
follow the manager's decision when it changes, and are never mistaken for yours.

MOVING A MOD BY HAND
--------------------
Drag a mod to another category's separator after an Apply, and it stays there: the next time the manager reads the
list it turns the move into a pin rule, so you do not have to write one per mod. It is listed in the Rules tab as
"pin (learned)", with the separator the manager had given it, and the log says
"learned '<mod>' -> <category> (moved there by hand; the manager had it in <category>)".
  - Move the mod back under the separator the manager gave it, and the rule is forgotten.
  - Only separators named for one of the manager's categories teach. Moving a mod under a separator you named
    yourself, a tier header or the NoDelete separator makes no rule.
  - A pin you typed yourself always wins over a learned one.
  - "Forget learned rules" in the Rules tab removes them all (Remove selected removes one). The next Apply places
    those mods by their evidence again. If a mod was the only one under its old separator, that separator is gone
    after the Apply, so this is the way back for it.
  - Learning starts after your first Apply with this version: that Apply records where it put every mod, and later
    moves are compared with it.
  - Settings > "Learn a rule from each mod you move to another separator" switches it off. Rules already learned
    stay until you forget them.

RESTORE BACKUP
--------------
"Restore backup..." beside Apply lists every backup newest first, with the profile it came from. The one you choose
puts the profile back as it was before that Apply: the mod list, plugin list, load order and plugin groups, the
separators the Apply retired (and the ones it created set aside), and the plugins it moved to or from Optional ESPs.
Your own rules stay; the pins learned from moves go back to what they were with that backup. The state it replaces
is backed up first, so a restore can itself be restored.

VERDICTS
--------
After every Apply, the mods whose MO2 category you set yourself where the manager would have placed them elsewhere
are written to plugins\data\MO2ModlistManager\verdicts\verdicts-<profile>-<date>.json: each mod's name, its Nexus
id, your category, the manager's category and a coarse summary of the mod - no file paths, user names or machine
details. Nothing is sent from the plugin. If you want future versions to place those mods your way, send us the file.

DEBUGGING
---------
Every decision is logged to plugins\data\MO2ModlistManager\log.txt. If MO2 crashes with this plugin on the stack,
Python's fault handler writes the Python frames to plugins\data\faults.log, naming the line. Send both with a report.
The verdicts from your last Apply are in plugins\data\MO2ModlistManager\verdicts - send them too if a mod was placed
somewhere you did not expect.

LICENCE
-------
GPL-3.0-or-later. Copyright (C) 2026 ApocryphaRealm. See LICENSE, NOTICE.md and THIRD_PARTY_NOTICES.md.
Source: https://github.com/ApocryphaRealm/MO2ModlistManager
