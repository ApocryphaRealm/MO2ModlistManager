# Changelog - MO2 Modlist Manager

Every version, beside the code it describes. Status is the version ledger's word for the build.

## 1.0.0 - 2026-09-23 - untested

First version. The evidence model: every signal a mod carries votes (files and their paths, the plugins' record
groups and the cells and worldspaces they reference, the mod's own words, its structure, a category the user set
himself), rules over the votes carry the owner's reasoning, and the heaviest category wins; the owner's taxonomy as
data (tiers, empty mains with sub-separators); the conflict resolver by evidence; plugin order and Bethesda Plugin
Manager groups following the pane; test builds under their official copy; a Review tab that writes nothing; copy
from every table. `expectations.json` scores each dry run against the owner's rulings (77 on 2026-09-23).

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

Sharing verdicts: a user's copy sends the verdicts it holds - mods whose MO2 category the user set and the evidence
would have placed elsewhere - behind a one-time disclosure and an explicit Send (a prefilled GitHub issue, or an https
drop box from the settings); the owner's copy (`role = owner`) fetches and pools them, and the pooled leaf is one more
vote weighted by how many users agree.
