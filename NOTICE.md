# Notice

MO2 Modlist Manager - a Mod Organizer 2 plugin that generates the left pane from the evidence each mod carries.
Copyright (C) 2026 ApocryphaRealm.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later
version. It is distributed WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See LICENSE for the full text.

It links against nothing but Mod Organizer 2's own Python plugin API (`mobase`) and the PyQt bindings MO2 ships. The
Nexus Mods v2 GraphQL endpoint is queried only for a mod's category name (cached), and the community-verdict exchange
sends only what README.md's disclosure lists, and only when the user presses Send.
