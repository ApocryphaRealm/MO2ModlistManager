# Changelog - MO2 Modlist Manager

Every version, beside the code it describes. Status is the version ledger's word for the build.

## 1.0.8 - 2026-09-27 - untested

- **Restore backup...** is a new button beside Apply. The owner: "lets add a restore backup button". It works like
  MO2's own restore (mainwindow.cpp at v2.5.2):
  1. Every backup is listed newest first by its time, with the profile it came from.
  2. You choose one and confirm.
  3. The profile's mod list, plugin list, load order and plugin groups are copied back, and MO2 refreshes without
     saving.
- A restore also undoes what the Apply did outside those files. The separators it retired come back, and the empty
  separators it created are set aside. Plugins it moved to or from Optional ESPs are moved back. From the rules file
  only the automatic facts are restored; your own rules stay.
- The state a restore replaces is backed up first, in the same shape, so a restore can be undone by restoring that
  backup.
- Apply now records its profile and the separators it created and retired (applied.json in the backup). For older
  backups the profile is a guess, from which profile's mod list the backup matches best, and the guess is marked in
  the list.
- **Game-version aware.** The owner: "make the plugin game version aware by checking stock game". The manager reads
  the game executable in the instance's game folder (gamePath, a Wabbajack list's Stock Game, else Stock Game or Game
  Root). It reads the FileVersion string, because Bethesda's fixed version block says 1.0.0.0; the owner's
  instances read 1.5.97, 1.6.1170 and 1.7.104.
  - A mod's name says which game version it is for ("for Skyrim 1.5", "1.5.97", "AE", "1.6.1170", "1.7.104"). A name
    that says both (SE-AE, "SSE and AE") fits either, and a mod's own version number (Dragon's Eye 1.7.3) is not a game
    version.
  - Two mods shipping one SKSE DLL: the build for this game wins. This replaces the old rule that anything saying "1.5"
    wins, which was wrong on AE.
  - Two copies from one Nexus page: the copy for this game wins over a newer one for another version.
  - A copy for this game is never switched off as an old copy.
  - Nothing is ever switched off for being made for another version.
- **Verdicts are no longer sent from the plugin.** The owner: "remove the send verdicts button and make the verdicts
  folder populated after an apply". The Share verdicts button, its send window, the GitHub-issue sending and the
  one-time sharing notice are gone. Every Apply, headless included, writes the verdicts to
  plugins\data\MO2ModlistManager\verdicts\verdicts-<profile>-<stamp>.json for the user to send by hand. The owner's
  copy keeps "Fetch community verdicts", which pools the files dropped in its inbox.

## 1.0.7 - 2026-09-27 - untested

- **No "Other" blocks and no Miscellaneous.** The owner: "yes break them up".
  - NPC is now Appearance, AI and Behaviour, Followers, New NPCs, and Names and Titles (Old Holds - Clan Names and
    Titles).
  - Player is Appearance only.
  - A handful of new NPC records votes New NPCs. A plugin that only alters NPC records goes to AI and Behaviour.
- **Uncategorised is a last resort, not a place to stop.** When nothing else decides a mod, the manager reads the file
  list inside its BSAs, directory only, and decides again. It also reads signals no other rule looked at:
  - Nemesis behaviour patches go to Animation.
  - Community Shaders features go to Lighting or Visual Effects.
  - Head-part whitelists and RaceMenu sliders go to Face.
  - Upscalers go to Performance.
  - Sound records go to Audio.
  - Ingredient records go to Alchemy, or to Items when the mod ships the models.
  - Overlay names go to Face or Body (make-up, eyebags, marks, tattoos, sliders, pubic hair).
  - Dragons go to Monster Appearance.

  Thirteen mods that had no evidence at all are placed now, including GoT dragons, Ribbit Remix, Skylighting, Unclench,
  DLSS-NR and the RaceMenu overlays.
- **Self-check:** it fails any "- General" or "- Other" leaf, and any mod of ours left Uncategorised. Folders starting
  with "_" are storage, not mods.

## 1.0.6 - 2026-09-27 - untested

- **No separator with a "General" suffix.** The owner: "nothing is ever actually general, it should be tied to
  something". The old general blocks are replaced by specific ones:
  - **Gameplay:** Difficulty and Progression, Survival and Camping (Campfire and its tents, wetness, woodcutting),
    Travel (No Fast Travel, Press H to Horse), and Inventory and Equipment (Weightless, outfits, durability, loot,
    soul gems). Combat, Stealth, Economy and Optional Tweaks stay.
  - **Location Overhauls:** Strongholds and Castles (Orc strongholds, Imperial Castles, Castle Volkihar, Fort
    Dawnguard) and Wilderness (barrows, occult sites, shrines, camps, standing stones, dragon mounds, Soul Cairn,
    Cold Welcome). Town, City and Interior stay.
  - **Crafting:** Smithing (Ars Metallica) and Stations (the Atronach Forge offering box).
  - **Enchanting:** Mechanics.
- **Filing order.** A mod the evidence still votes "general" is filed by:
  1. its name's subject;
  2. a place it names (a city unless the name means its hold or wilds, or a town);
  3. the mod it belongs to (for a place, only if that mod is itself a place);
  4. what its records mostly are (sounds go to Audio, a dialogue-heavy mod to Quests).

  A mod with no evidence fails the self-check, and so does a general leaf in the taxonomy.
- **Placements:**
  - Sound mods (Volkihar Soundscape, Standing Sound Stones, Haunted Shipwrecks) go to Audio.
  - Bridges and carriage and ferry travel go to Roads.
  - Tales of Skyrim - Berserkyr goes to Quests.
  - Reindeer Herds goes to Animals.
  - Producers of Skyrim goes to Economy.
  - Better Dynamic Snow goes to Landscape.
- **A series whose base is "<name> - Master Plugin" gets its own separator** once ten mods are named for it. The
  Environs mods (15) now form one block.
- **A small separator folds only into a neighbour of its own kind** (Crafting - Stations into Crafting - Smithing).
  It is never folded into an unrelated one: the Atronach Forge offering box had become an Alchemy mod. Otherwise it
  keeps its own separator.
- **Named mods:** Mannequins Behave goes to Bug Fixes. VioLens and killmove mods go to Gameplay - Combat; "disable
  killmoves" goes to Optional Tweaks. A difficulty mod is gameplay, whatever menu it uses.

## 1.0.5 - 2026-09-27 - untested

- **No general models and textures block.** Only whole-game baseline packs stay in the new **Mesh Improvements**
  block, which is the first of the world tier: SMIM and its addons, High Poly Project and its fixes, and Cleaned Skyrim
  SE Textures. Every other mod goes somewhere specific, checked in this order:
  1. A decisive name.
  2. The mod it is art for, found by name or initials (HD Textures for Solitude and Temple Frescoes goes with the
     Frescoes, NVFH LOD Files with Northern Vanilla Farmhouses).
  3. The object its name says.
  4. What most of its files are.

  A mod left with no evidence fails the self-check. Resource packs go to Architecture. Security Overhaul's locks go to
  Clutter.
- **No general Overhauls block.** A plugin that only alters existing records is filed by what it alters: weather,
  plants, enchantments, quests, NPCs or creatures. Anything else goes to the new **Gameplay - Optional Tweaks** block
  (Disable Cinematic Kills).
- **Cubemaps** is a new block after every equipment block. Dynamic Cubemaps overwrites all the equipment mods.
- **No Collectables, Treasure Hunts, and Puzzles block.** Collectibles Helper goes to Quests. A scripts-only fix
  (High Gate Ruins Puzzle Reset Fix) goes to Bug Fixes.
- **Dialogue:**
  - Every Lines Expansion mod (Civil War, Bandit, Forsworn and Thalmor, Vampire, Falmer Servant, Brawl).
  - Smart Talk and Predictable Persuasion.
  - PlayerPayCrimeGold.
- **Enchantments:**
  - An existing item's enchantment, changed: Chillrend, Better Rueful Axe, A Better Gauldur Amulet.
  - Better Oghma Infinium.
- **New equipment:**
  - Nordic Wanderer Equipment, and any name ending in "Equipment".
  - Sword of the First Ember: a lone quest that hands gear over is delivery. Gear that comes with new people or several
    quests stays a quest mod (Ice Blade of the Monarch, Dwemer Exoskeleton).
  - Silverguard: a unique piece of gear is new even as a single record.
- **User Interface:** SkyALERT and Detection Meter are HUD elements, and "prompt" mods (Survival Mode Prompt Removed)
  go here.
- **Improved Controls:** Simpler Knock and Simply Order Summons, and Dragon Claws Auto-Unlock, which joins BTPS.
- **Other placements:**
  - Photo Mode goes to Camera.
  - Magic Sneak Attacks goes to Magic.
  - Skyrim Save System Overhaul goes to Save Games.
  - Mixwater Mill goes to Town.
  - Model Swapper goes to Utilities.
  - Clan Names and Titles goes to NPC.
  - Skyrim Snow Dogs goes to Animals.
  - Vanilla Script Optimizations goes to Script Fixes.
  - Gathering Be Gone goes to Plants.
  - Backpack Repositioner goes to Equipment Positioning.
  - Always Snowing goes to Weather.
  - Smart NPC Potions and Conditional Tavern Cheering go to NPC behaviour.
  - Read the Room goes to Gameplay.
  - Grindstone, forge and anvil model swaps go to Furniture.
- **Rule changes:**
  - A mod named "... Base Object Swapper" is art, not the Base Object Swapper framework.
  - The Environs mods leave Gameplay.
  - A name that says fix outweighs a gameplay word (Zero Bounty Hostility Fix).
  - Faction cells alone do not make a faction mod: Ars Metallica goes to Crafting, and Statue of Sithis to Interiors
    as decoration.
- **Earlier the same day:**
  - The Animation blocks move after gameplay.
  - Collision is its own block, and Debugging (with Collision Sentinel off by default) follows Bug Fixes.
  - Animation splits into Character, Combat, Player, NPC, Enemy and Creature.
  - Animation engines go to Utilities.
  - Mods sort by name inside a block, with families together.
  - Interiors, player homes, animals, quests, followers and new weapons take the mods the owner named.
  - A fixed block is no longer split by one of its mods sitting mid-run.

## 1.0.4 - 2026-09-27 - untested

- SkyUI, RaceMenu, MCM Helper and UIExtensions, and mods named for them, go to User Interface, not Frameworks. A "for
  SkyUI" at the end of a name names the target, so "Fix Note icon for SkyUI" stays a fix.
- The animation engines (Nemesis, Pandora, FNIS, Open Animation Replacer, Dynamic Animation Replacer, Behavior Data
  Injector, BFCO) and the mods named for them go to Animation.
- Security Overhaul and its lock mods go to Models and Textures. Weightless and carry-weight mods go to Gameplay.
  SkyPatcher is a framework.
- These name words count from the mod's name only. A readme saying "requires SkyUI" or "carry weight" does not make
  a mod a UI or gameplay mod.
- A "resources" pack that ships meshes and textures is a model and texture pack, not a utility. When mods in an
  earlier block build on its plugin, it goes to the world tier's architecture block, before them.
- A mod that is only an SKSE plugin, and whose name and documents say nothing, is read from its own config: keys are
  split into words, and it counts when one theme repeats at least four times. Intellightent's config says "light"
  seven times, so it is a lighting mod. A lighting DLL now stays in Lighting instead of going to SKSE Plugin Tweaks.
- SKSE Plugin Tweaks, reassessed: a mod that is only an SKSE plugin is filed by its subject whenever its name or
  documents give one. Examples: an audio output switch goes to Audio, a grass cache helper to Grass, a follower leash to
  Followers, and paralysis spells to Magic. SKSE Plugin Tweaks keeps only engine tweaks that name no subject.
- New name words, all counted from the name only:
  - Revoiced and voice mods go to Audio.
  - Bethesda logo removers go to Essential Engine Fixes.
  - "Scripting" goes to Script Fixes, and stays there whatever the mod ships.
  - Camera-collision mods go to Camera.
  - Strongboxes go to Furniture.
  - "NPCs Learn to Aim" goes to NPC AI.
  - "One click" goes to Improved Controls.
  - Texture downscalers go to Performance.
  - Crime and bounty mods go to Gameplay.
  - Knotwork and Item Explorer go to User Interface.
- A mod that calls itself "animations" and ships animation files is an animation mod, even when its name also says
  "sprint" or "jump".
- A preset that names a mod belongs to that mod: Whistle SmoothCam Preset goes to Camera, beside SmoothCam.
- Character-creation options go to Face, beside the other head parts, rather than to Races. That covers names like
  "character creation", "fins" and "Argonian crests" (Kabu's Argonian Fins, Argonian Crests, KCCE).
- Races, Classes, and Birthsigns takes mods named for classes ("class overhaul", "classes"), race overhauls, and the
  standing stones, which are Skyrim's birthsigns ("integrated standing stones", "standing stones overhaul",
  "birthsigns"). This covers Apprentice, Heritage and Freyr, which had gone to Magic on their spell records.
- Inverse kinematics goes to Animation. A loading-screen mod goes to User Interface, except a "Faster Loadscreens"
  kind of mod, which stays in Performance.
- Animation blocks: Animation - General is now Animation - Character, and Animation - Combat is new. The Player,
  NPC, Enemy and Creature blocks stay.
  - An animation mod whose name says it animates fighting goes to Combat. That covers attacks, movesets, combos,
    MCO, BFCO, stances, blocking, dodge, and weapons such as bows and spears. "Non combat" stays in Character.
  - An animation mod whose animation files are mostly under a creature's actor folder goes to Creature, even when it
    is about fighting. Dragon Combat Animations and the wolf attacks are creature animations. An engine or framework
    (Pandora) stays in Character.
- Dragon mods named by their phrases ("diverse dragons", "dragons collection", "GoT HotD") go to Creatures - Monster
  Appearance.
- A creature's barking or howling is behaviour: those mods go to NPC - AI and Behaviour, and animation files no longer
  weaken that vote.
- "War horns" are items, not face horns.
- Today's name-only keyword rows now carry their own weight, so they no longer switch an older row with the same
  weight to name-only.

## 1.0.3 - 2026-09-27 - working

- One plugin name, two copies. When enabled mods ship different copies of one plugin and only some of them have every
  master present, a copy that can load is the one MO2 takes. The mod with the unloadable copy sits below it, whatever
  the name evidence says. Masters outrank evidence. A copy just parked in Optional ESPs still counts, so the order stays
  safe wherever the files end up.
- A behaviour patch for skeleton mods, like Auto Skeleton Patch - Universal Behaviour Runtime, goes to Animation. It
  loads after every animation mod and every mod that ships a character skeleton. This does not count an animation mod
  that its own masters pull into a later block.
- "... of Light" in a name names an item, not a lighting mod. Auriel's Bow of Light is a weapon.
- Names are compared as whole words, not as squashed letters. "XP32 Maximum Skeleton Special Extended" no longer
  counts as an add-on of "Skeletons SE".
- One Nexus page, one plugin, two versions: the newer copy wins, when every plugin of the older copy is also in the
  newer one.
- An older copy from one Nexus page is switched off beside the newer version when the newer version ships every one
  of its files with the same path and the same size. Same paths with different contents are a choice, not a copy, and
  stay on.

## 1.0.2 - 2026-09-27 - working

- An add-on whose name opens with its parent's initials, counting small words ("LoY - ..." for Legacy of Ysgramor),
  sits with the parent when it replaces the parent's files.
- A mod that ships a plugin with the same file name as its parent's replaces that plugin. It sits with the parent and
  loads after it. An example is an older copy of one patch from a patch collection, kept because it fits the installed
  master.
- The optional-file rule now also holds when the two files sit in different blocks.
- A bridge joins its block: a mod whose own main plugin is built on two or more mods of one block sits in that block.
  Ultimate College of Winterhold, built on Immersive and Obscure's College, now sits with them.
- Fixed: a mod name's [tags] were not removed before names were compared. A "[Patch]"-tagged parent was then never
  recognised in its children's names.

## 1.0.1 - 2026-09-27 - working

Add-ons stay with their parent mod, and a few more plugin states are decided from what the plugins hold.

- An add-on that ships only art and replaces files of its parent sits with that parent, whatever its words say. The
  parent is the mod it is named for, or the main file of its own Nexus page. An SMP physics file for an armour now
  sits with the armour, not in Physics. A mesh fix for a weapon set now sits with the weapon set, not in Models and
  Textures.
- An optional file from a mod's own Nexus page loads after that page's main file. The main file is the one with the
  plugin, or the larger one. This holds however you renamed the optional file.
- A patch published on its target's own page, whose other targets are not enabled, sits with that target instead
  of in Patches.
- One download installed twice: when two enabled mods come from the same archive and hold the same files, the copy
  whose name matches the download stays on and the others are switched off beside it. Their folders are left alone,
  and the preview lists each one.
- A patch made for a different version of its master waits in Optional ESPs. That means a patch that changes records
  from a master when not one of those records exists in any installed copy of that master. A patch that is only
  partly out of date keeps loading. Such a patch is also no longer brought back from Optional ESPs just because its
  masters are present.
- FOMOD alternatives: when two plugins from one page are named as variants of each other, and the fuller one changes
  every record the smaller one does with more masters, the smaller one waits in Optional ESPs.
- The version MO2 shows is read from the plugin's own version number.

## 1.0.0 - 2026-09-26 - working

First release, with ten placement rules for where mods go and in what order.

- Lighting loads after every architecture, town, city, clutter and furniture block it re-authors (P1); the world runs
  broad to specific - weather, landscape, water, architecture, buildings, towns and cities, then roads, trees, grass,
  plants, seasons, then models and textures, PBR, visual effects and lighting (P2). Location Overhauls and Buildings
  move from tier 4 into the world tier.
- Core by mechanism (P3): Bug Fixes (plugin), Script Fixes, SKSE Plugin Fixes, Mesh and Texture Fixes; an SKSE-only
  tweak of the world, items, audio or visuals goes to SKSE Plugin Tweaks, while an SKSE-only gameplay, combat or AI
  system keeps its subject (Precision, Maxsu Poise, Modern Combat AI). A ruling that names "Bug
  Fixes" is met by any block of the fix family.
- Performance Optimization moves after Patches (P4); a location or quest mod with ten or more mods named for it or built
  on it gets a separator of its own right after its category's block (P5); a patch that names two or more mods and ships
  loose files goes to Patches (P6); Physics loads after Hair and Races (P7); Icon Overhauls after the UI overhaul,
  never a mod with fonts or fontconfig.txt (P9); a new Optional Addons tier after the generated outputs for
  [Addon] / [Optional] / [Ultrawide] variants, with DynDOLOD.esp and Occlusion.esp still ending the plugin order (P10).
- Inside a block, nothing else deciding (P8): a family together, its patches and patch collections last, then
  alphabetical - no longer today's position. The order is now the same whatever order the list starts in.
- No Nexus request: the category fetch is gone (the owner: "we don't need it to check Nexus"). Nexus category names
  come from MO2's nexuscatmap.dat plus a built-in Skyrim SE list; the Shape rule's "the body itself" reads body meshes,
  and a CBBE/3BA-named texture-only mod (overlays, tattoos) is no longer a refit.
- Self-check: every ruling met on both test profiles, launch audit clean on both.
- Where it matters in game - the WINNERS of real conflicts (the owner, 2026-09-26: "is it functionally meaningful"; 99.96%
  of mod pairs never share a file or record): three evidence rules. A mod named by another's initials is its addon
  ("EFM SE - Racemenu plugin" after Expressive Facegen Morphs SE). A complex-material, parallax or PBR version wins over
  the plain one in the same block, after specificity (ERM - Complex Materials over ERM; the small FYX fixes still win).
  A patch whose targets all sit in one block stays in that block rather than going to Patches (Audio Overhaul -
  Immersive Sounds Integration stays in Audio; about 680 records went to the wrong winner).
- A reference-order check in tools\selfcheck.py fails any change that makes the manager pick different winners for
  contested files and records than before; the package gate runs it.
- The toolbar button follows the theme (the owner: "make sure that the button ... responds to theme changes and style
  sheet changes"): the icon is painted in the colour the current stylesheet gives MO2's toolbar buttons and repainted
  when that changes - light on Njordlinger (#f1f1f1), black on Paper Light, where a fixed pale icon disappeared.
- The lists are written the way MO2 2.5.2 writes them (MO2-REFERENCE.md; the owner kept these in 1.0.0 because the
  plugin is unreleased). Foreign mods in modlist.txt (`*DLC: Dawnguard` and the like) are carried through at the bottom
  instead of dropped. plugins.txt leaves out the game's primary plugins (the five base masters and whatever Skyrim.ccc
  lists) and is written in the system code page, not UTF-8. An empty plugin list is never written.
- A planned separator that differs from an existing one only in letter case keeps the existing folder's spelling. Before,
  Apply could create "Player homes" and then retire "Player Homes" - the same folder on Windows - so both separators
  vanished. The self-check now fails such a plan.

### The first build (2026-09-23, never released)

The evidence model: every signal a mod carries votes (files and their paths, the plugins' record
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

The UI overhaul wins every UI element (the owner, 2026-09-24): the UI Overhaul block is the last content block, after
Maps and before Patches, so Norden UI's restyled SWFs and fontconfig.txt outrank QuickLoot, BTPS, TDM, Alternate
Perspective, the minimap and every other mod shipping the same interface files; a mod that ships fonts or its own
fontconfig.txt is a UI addition (R37: User Interface) and a font mod always sits above every UI overhaul (an edge).

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

The order passes the launch audit (2026-09-24). Two ordering edges the category order did not know: a mod that ships a
"for Skyrim 1.5" port of an SKSE DLL sits below the AE build of the same DLL so the port wins it (Magic Fixes and
Tweaks for Skyrim 1.5 had landed in Bug Fixes above Magic Tweaks SKSE - spells), and a framework's own mod wins its
DLL over a copy bundled in another mod (PapyrusUtil SE over Campfire's); DynDOLOD's output (DynDOLOD.esp,
Occlusion.esp) is the last of the generated outputs (PGPatcher's PG_1.esp had landed after it). `tools\selfcheck.py`
dry-runs every Njordlinger profile, audits the proposed order with nj-order-audit.py and meets every ruling; gate rule
modlist-manager-order-passes-the-launch-audit runs it before the plugin is packaged.
