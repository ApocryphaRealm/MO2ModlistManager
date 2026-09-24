# Changelog - MO2 Modlist Manager

Every version, beside the code it describes. Status is the version ledger's word for the build.

## 1.0.0 - 2026-09-23 - untested

First version. The evidence model: every signal a mod carries votes (files and their paths, the plugins' record
groups and the cells and worldspaces they reference, the mod's own words, its structure, a category the user set
himself), rules over the votes carry the owner's reasoning, and the heaviest category wins; the owner's taxonomy as
data (tiers, empty mains with sub-separators); the conflict resolver by evidence; plugin order and Bethesda Plugin
Manager groups following the pane; test builds under their official copy; a Review tab that writes nothing; copy
from every table. `expectations.json` scores each dry run against the owner's rulings (109 on 2026-09-23).

Third batch of rulings, as weights: an Equipment Positioning separator after Shape (where gear sits on the body -
Simple Dual Sheath, Immersive Equipment Displays and its presets; an IED word in a "for X" subject is the target, not
the mod); a quest's own items and a quest that carries dialogue topics vote Quests (Sell Unusual Gems); quests that
only hold scripts, beside records that act on the game, are a gameplay system (R22: Acquisitive Soul Gems, Simple
Degradation); durability and degradation are gameplay words; the MO2 'test' category is decisive.

Fourth batch: body-morph and body-preset words (OBody) define Body; a new race with no head parts and a handful of
actors per race is a creature race, and named animals vote Creatures (Dire Wolves); a creature replacer is creature
appearance; FaceGen data under the mod's own plugin is its NPCs' generated faces, not face art; a scripted system's
concentrated exterior edits keep their full weight - what it adds to a worldspace needs patches (Carriage and Ferry
Travel Overhaul is a location overhaul).

Fifth batch: the reference walker gives the CELL and WRLD groups a budget each (a big interior group hid
Wyrmstooth's new worldspace); references concentrated in the worldspace and cells a mod adds are a new land; the NPCs
a place mod adds are its inhabitants (R25); a distribution-only mod (SPID/KID INIs) hands out what its name proper
names - "for Y" is the recipients (R23); follower-gathering words (NPC friends, summon your followers) define
Followers; "living AI" / routines define NPC AI and spells beside scripts and an MCM are its means; a replacer of a
creature it names is creature appearance (R24).

Sixth batch: a mod follows another mod in the pane only when ALL its plugins need that mod as a master - a
bundled compatibility plugin or a patch hub's patches follow their masters in the plugin order alone, and the mod
keeps its own block; a Creatures - Animals sub-separator for wildlife (R27); a distribution-only mod handing out gear
that already exists is NPC - Appearance (R26). A Creatures - Monster Appearance sub-separator (R29), and a BSA loader - a plugin with no
records beside a BSA - is judged as art (R28). A perk overhaul (100+ perks, new or altered, and at least a quarter as many perks as
spells and effects) is Class, Perks, Powers and Blessings (R30); a collection of two or more plugins, each built on
another content mod, votes the categories of the mods it tweaks (tweak-collection pass).

Seventh batch: a Maps separator at the end of the content tier for every map-related mod; Overhauls split into
General and Faction Overhauls (R33: several kinds of change around one faction); new equipment placed in an existing
place with a quest is a quest mod, with a new location a new-location mod (R31); a new place of interiors (R36); a
story beat for an existing character (R32) and a small adventure to find (R34) are quests; activators with message
boxes are UI (R35); quest-expansion and questline names; voiced dialogue; name-only rows for maps, crafting stations,
huts and followers; alchemy ingredients, auto draw, iHUD, Raven Rock, one-world overhauls, fixes shipped as animations.

Sharing verdicts: a user's copy sends the verdicts it holds - mods whose MO2 category the user set and the evidence
would have placed elsewhere - behind a one-time disclosure and an explicit Send (a prefilled GitHub issue, or an https
drop box from the settings); the owner's copy (`role = owner`) fetches and pools them, and the pooled leaf is one more
vote weighted by how many users agree.
