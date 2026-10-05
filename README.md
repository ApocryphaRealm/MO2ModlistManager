# MO2 Modlist Manager

A Mod Organizer 2 plugin (Python, MO2 2.5.x) that generates the left pane: one separator per category in a fixed
load-order taxonomy, every mod placed under the category the evidence decides, masters above dependents, the plugin
list following the pane. Nothing is written until Apply, and Apply backs up the profile's lists first.

Version 1.1.3 (this build's own numbering; no upstream).

## How a mod is placed

Every signal a mod carries becomes a vote - (source, category, weight, reason) - and the heaviest category wins. The
Placement tab shows every vote for every mod, so a placement is always explainable. The sources:

* **what the folder ships** - a DLL, animations, sound, meshes and textures, and which asset paths they sit under
  (architecture, clutter, furniture, hair, face, effects, the world map, ...), each path class in proportion to its
  share of the files;
* **what the plugins add or alter** - the TES4 record groups (armour, weapons, spells, perks, NPCs, quests, races,
  weather, ...) read from the plugin files, plus the cells and worldspaces a plugin adds or edits and what they are
  named (a city, a home, a dungeon, a faction hall, a new worldspace);
* **what the mod says about itself** - its name, its plugins' descriptions, its readme and FOMOD info; some words the
  owner named as decisive (camera, dialogue, physics, controls, lighting, seasons, PBR, ...);
* **its structure** - a `[Patch]` tag, plugins whose masters belong to other content mods, a master ten or more mods
  depend on, a name that says it is an addon of another mod in the list;
* **a category you set yourself in MO2** that names one of the tree's leaves - your statement, and decisive;
* **community verdicts** - what other users filed for the same mod (below), weighted by how many agree.

No Nexus category is used and nothing is asked of Nexus: they got in the way. Rules over the votes encode the owner's
reasoning - a name that says fix is a fix, a mod that alters far more than it adds is about existing things, spells
shipped with a DLL or animations are a mechanism, a readme names what a mod requires and not what it is, "X Menu" is
about X, a leveled-list injector is the patch layer, and so on - each written beside its case in the source.

The ORDER follows ten rules: the world broad to
specific with lighting after what it re-authors; core blocks by mechanism (plugin, script, SKSE and mesh fixes; SKSE
tweaks of the world and items); performance swaps after the patches; a big location or quest mod in a block of its own;
asset patches that name two mods in Patches; physics after hair and body; icon packs after the UI overhaul; optional
addons after the outputs; and inside a block, families together with their patches last, then alphabetical - never
today's position, so the result does not depend on the order the list starts in.

`expectations.json` holds the owner's rulings as a scorecard. The offline dry run
(`python MO2ModlistManager.py <instance dir> <profile> <cache dir>`) reports how many are met; a ruling is folded
into the weights and rules, never handled as a one-off exception (the project's rule 67).

## Mods moved by hand become rules (1.1.3)

The owner, 2026-10-05: *"any mods that the user shifts to a different separator becomes a new rule automatically so they
don't have to make them one by one manually."* Every Apply records the separator it put each mod under
(`auto_placement` in the profile's `modlist_order_rules.json`). A later run compares the pane with that record:

- **Learn.** A mod now under a different category separator (one named for a taxonomy leaf) becomes a learned pin
  (`learned_pins`). It is honoured like a typed pin and listed in the Rules tab as `pin (learned)`. The log line is
  `learned '<mod>' -> <category> (moved there by hand; the manager had it in <category>)`.
- **Forget.** Moved back under the separator the manager gave it, the learned pin is forgotten. **Forget learned rules**
  (or Remove selected) forgets on demand, and records the mod's current separator so the move is not learned again.
- **What never teaches:** a separator the user named, a tier header, an empty main separator, NoDelete. A typed pin
  always wins.
- **Restore backup** puts `auto_placement` and `learned_pins` back with the other automatic facts.
- **Off switch:** `learn_from_moves` in the settings, default on.

The trigger is the comparison, not MO2's `onModMoved`. MO2 2.5.2 emits that signal only from the multi-index
`changeModPriority`, not from the single-index one or for an edit made outside MO2 (MO2-REFERENCE.md).

These are the player's rules for their own list. A ruling by the owner about where a mod belongs still goes into the
evidence model and `expectations.json` (rule 67). `tools/test_learned_pins.py` covers the cycle on a scratch instance:
Apply, move, learn, Apply, move back, forget, the user's own separator, a typed pin, Forget, the switch, and Restore.

## Sharing verdicts

The classifier learns from other lists. In the dialog, **Share verdicts...** shows every mod whose MO2 category you
set yourself and the evidence alone would have placed elsewhere, with what would leave your machine:

> the mod's name, its Nexus id, the category you chose, the category the evidence chose with its top votes, and a
> coarse summary of that evidence (how many plugins, whether it ships a DLL or animations, how many files, which
> record kinds). No file paths, no user names, no machine or account identity.

It is off unless you turn it on, and every row is on screen before Send. With no drop-box address in the plugin
settings, Send opens a prefilled GitHub issue in your browser for you to post; **Copy JSON** puts the full payload on
the clipboard. `share_after_apply` in the plugin settings repeats the send after each Apply. The disclosure is shown
once, at the first opening.

The receiving end is the same plugin with `role` set to `owner`: **Fetch community verdicts** reads every `verdicts`
issue on this repository, the drop box if one is set, and any payload dropped into `plugins/data/MO2ModlistManager/
community-inbox/`, pools them by mod as `{leaf: distinct submitters}`, and the pooled leaf becomes one more vote (one
user 1.0, capped at 3.0). Submitters are counted, never stored.

## Settings (MO2 > Settings > Plugins > MO2 Modlist Manager)

| Setting | Meaning |
|---|---|
| `role` | `user` (share) or `owner` (receive and pool) |
| `share_after_apply` | send the verdicts after each Apply |
| `verdicts_endpoint` | an https address to POST to / fetch from; empty means the GitHub issue route |
| `disclosed` | the disclosure has been shown once |
| `learn_from_moves` | a mod moved by hand to another category separator becomes a pin (default on, 1.1.3) |

## Debugging

Every decision is logged to `plugins/data/MO2ModlistManager/log.txt`; a crash inside MO2 with this plugin on the
stack is written by Python's faulthandler to `plugins/data/faults.log`, naming the line. Send both with a report.

## Licence

GPL-3.0-or-later. Copyright (C) 2026 ApocryphaRealm. See LICENSE and NOTICE.md.
