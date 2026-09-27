MO2 Modlist Manager
===================
Version 1.0.0

A Mod Organizer 2 plugin that sorts the whole left pane for you: it generates the separators, places every mod under
the category its own evidence decides, puts masters above the mods that need them, and makes the plugin list follow
the pane. Nothing is written until you press Apply, and Apply backs up the profile's lists first.

THIS IS NOT A MOD. Do not install it with the mod manager.

HOW A MOD IS PLACED
-------------------
Every signal a mod carries becomes a vote, and the heaviest category wins:
  - what the folder ships: a DLL, animations, sound, meshes and textures, and which asset paths they sit under;
  - what its plugins add or alter: the record groups, and the cells and worldspaces they add or edit;
  - what the mod says about itself: its name, its plugins' descriptions, its readme and FOMOD info;
  - its structure: plugins built on other mods (a patch), a master many mods depend on (a framework), a name that
    says it is an addon of another mod in the list;
  - a category you set yourself in MO2, if it names one of the manager's categories - your word, and decisive.
Nexus categories are not used and Nexus is never contacted. The "Every placement" tab shows every vote for every mod,
so each placement explains itself.

THE ORDER
---------
Tiers from what everything stands on to what finishes the list: base game and engine, interface, characters and
animation, the world and gameplay systems, content, patches, test builds, generated outputs, optional addons. Inside
them, rules read off a hand-built published list (Apostasy) and measured on it:
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
    master, a generated output or a settings loader.
Apply writes the plan: modlist.txt, plugins.txt and loadorder.txt, new separators (in your separators' colour),
retired separators moved to the backup, and Bethesda Plugin Manager groups when that plugin is installed. Every
Apply keeps a backup of the lists under plugins\data\MO2ModlistManager\backups\<date-time>\.
"Write decided categories to MO2" stores each mod's decided category in its meta.ini as its MO2 category; a category
you set yourself is left alone.

SHARING VERDICTS (optional, off unless you use it)
--------------------------------------------------
"Share verdicts..." lists the mods whose MO2 category you set yourself where the evidence alone would have placed
them elsewhere, and exactly what would be sent: the mod's name, its Nexus id, your category, the evidence's category
and a coarse summary of the evidence. No file paths, user names or machine details. Every row is on screen before
Send, and without a drop-box address in the plugin settings Send opens a prefilled GitHub issue for you to post.

DEBUGGING
---------
Every decision is logged to plugins\data\MO2ModlistManager\log.txt. If MO2 crashes with this plugin on the stack,
Python's fault handler writes the Python frames to plugins\data\faults.log, naming the line. Send both with a report.

LICENCE
-------
GPL-3.0-or-later. Copyright (C) 2026 ApocryphaRealm. See LICENSE, NOTICE.md and THIRD_PARTY_NOTICES.md.
Source: https://github.com/ApocryphaRealm/MO2ModlistManager
