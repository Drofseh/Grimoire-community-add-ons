# Where a book goes in Grimoire

Grimoire has no "category" field you set by hand at import: the **folder a file
sits in is its classification**. This reference is the rulebook for choosing
that folder. It mirrors the scanner's behaviour - get the path right and the
system, edition, category and grouping all follow.

## Contents

1. The five collections
2. The books path: system / category / group / file
3. Categories, and how folder names are read
4. Choosing the category - decision guide
5. Game systems and editions
6. Containers and special collections
7. Subfolder groups
8. File names
9. Versions of one book (variants)
10. NSFW and restricted content
11. Things that are not books

---

## 1. The five collections

| Top folder | Holds |
|---|---|
| `books/` | Rulebooks, supplements, adventures, sheets, handouts, magazines - anything read as pages. PDF, EPUB, DjVu, CBZ/CBR/CB7/CBT, TXT/MD/RTF, single images, and archives kept beside a book |
| `maps/` | Battle maps and map packs for play (images, PDFs, animated `.webm`/`.mp4`, `.uvtt`/`.dd2vtt`), organised by creator or collection |
| `tokens/` | Token and portrait images, by type or creator |
| `audio/` | Music, ambience and audiobooks (`.mp3 .ogg .opus .flac .wav .m4a .m4b .aac`) |
| `models/` | 3D printing files (`.stl .obj .ply .3mf .glb .gltf`, sliced resin formats) |

Nothing may be placed directly in the library root, and Grimoire refuses
`.doc`/`.docx`/`.odt`/`.mobi`/`.azw*` - convert those to PDF or leave them out.

## 2. The books path

```
books/<System>/<Category>/<Group>/<Sub-group>/<File>
       └ game system └ category  └ optional groups (any depth)
```

- `books/Mothership/Adventures/Gradient Descent.pdf` - system *Mothership*,
  category *adventure*, no group.
- `books/Pathfinder 2e/Adventures/Abomination Vaults/Ruins of Gauntlight.pdf` -
  grouped under *Abomination Vaults*.
- A file directly in the system folder is filed as **core**.
- Only the **first folder under the system** decides the category. Deeper folder
  names are group labels and never change the category, so a group can be named
  anything.

## 3. Categories, and how folder names are read

Use these exact folder names. They are what Grimoire's own "Create standard
category folders" action creates, and each is read back as its category:

| Folder name | Category slug | |
|---|---|---|
| `Core` | `core` | |
| `Starter Sets` | `starter-set` | |
| `Supplements` | `supplement` | |
| `Adventures` | `adventure` | |
| `Character Sheets` | `character-sheet` | |
| `Handouts` | `handout` | |
| `Maps` | `map` | |
| `Homebrew` | `homebrew` | |
| `Magazines` | `magazine` | |

If the system folder already exists with its own spellings (`core`,
`Rulebooks`, `Modules`), **use the existing folders** - Grimoire treats them
as the same categories, and a second `Adventures` beside `Modules` would split
one shelf in two.

**Any other first-level folder name becomes a custom category** (slugified):
`Fiction`, `Art Books`, `Bestiaries`, `Cards`. Matching is case-insensitive,
treats `-`, `_` and spaces alike, and any *word* in the name that is a keyword
claims the folder for that category:

| Keyword (any word of the name) | Category |
|---|---|
| core, rulebook, rules, phb, dmg, mm, basic | core |
| supplement, expansion, sourcebook, guide, companion | supplement |
| adventure, module, campaign, scenario, quest | adventure |
| "character sheet", charsheet | character-sheet |
| map, battlemap, "battle map", "dungeon map" | map |
| handout, reference, cheat, "quick ref", screen | handout |
| homebrew, custom, "house rules", unofficial | homebrew |
| "starter set", "starter kit", "beginner box", "boxed set", essentials | starter-set |
| magazine, zine, fanzine, periodical | magazine |

Whole-name-only words: `Players`, `GMs`, `Game Masters` → core; `Sheets` →
character-sheet; `Sources` → supplement; `Journals`, `Issues`, `Back Issues` →
magazine.

So a custom category name must avoid those words unless you mean them:
`Campaign Settings` is read as *adventure* (campaign), `Setting Guides` as
*supplement*, `Basic Fantasy` as *core*. Name a custom shelf for what it holds
without a keyword (`Settings`, `Fiction`, `Art Books`), or put the book in a
standard category and use a group folder for the finer label.

## 4. Choosing the category - decision guide

Decide from what the book *is for*, using its own text (introduction, back-cover
blurb, table of contents), not just its title.

**Core** - what you need to play the game at all.
- The main rulebook(s): Player's Handbook, Game Master's Guide, the core monster
  book of a "core three" (PHB/DMG/MM). Complete-game books (`Mothership Player's
  Survival Guide`, `Blades in the Dark`).
- Revised/remastered core books are core books of the same system or edition.
- *Not* core: player-option books, extra bestiaries, setting books - those are
  supplements even when "Player's" is in the title.

**Starter Sets** - an introductory, cut-down way in.
- Starter sets, beginner boxes, essentials kits, quickstart rules, Free RPG Day
  quickstarts, "ashcan" introductory editions.
- A starter box's adventure book stays with the starter set, grouped:
  `Starter Sets/Lost Mine of Phandelver Starter Set/`.

**Supplements** - adds options or setting to a game you already have.
- Sourcebooks, setting and campaign-setting books, gazetteers, splatbooks, class
  and ancestry options, equipment/magic/spell books, bestiaries beyond the core
  one, GM toolkits, rules expansions, system-specific random tables.
- Third-party *published* supplements are supplements, not homebrew (Kobold
  Press for 5e, Frog God Games for Pathfinder).

**Adventures** - something to run.
- Modules, one-shots, scenarios, campaigns and adventure paths, organized-play
  scenarios, Free RPG Day adventures, convention modules, dungeons with a key.
- A campaign *setting* without a plot is a supplement; a campaign *book* with a
  plot is an adventure. When a book is both (most Paizo/Chaosium campaign
  books), pick adventure if most of its pages are the plot.

**Character Sheets** - sheets to fill in.
- Character sheets (fillable or printable), character keepers, pregenerated
  characters delivered as sheets, NPC sheets, ship/vehicle/mech sheets.
- A PDF with form fields (`form_fields: true`) of 1-6 pages is almost always a
  sheet.

**Handouts** - at-the-table reference and props.
- GM screens and their inserts, quick-reference and cheat sheets, rules summaries,
  card decks (spell, item, condition, initiative cards), player handouts and
  props from an adventure, tokens/standees *printed as a PDF*, cheat sheets.
- An adventure's own handouts can stay grouped with the adventure instead:
  `Adventures/Gradient Descent/Gradient Descent - Handouts.pdf`.

**Maps** (the `books/` category) - maps that belong to a game's books.
- An adventure's map booklet, a setting's poster map, a printed map pack for one
  system. Put it beside what it belongs to (`Adventures/<Adventure>/`) or in
  `Maps/`.
- Standalone battle maps sold for any system, especially as images for virtual
  tabletops, belong in the **`maps/` collection**, not `books/` (see section 11).

**Homebrew** - community and fan content, not from the game's publisher or a
licensed third party.
- Fan supplements, house rules, community-programme releases (DMs Guild,
  Pathfinder Infinite, Storytellers Vault, Miskatonic Repository, Jonstown
  Compendium, Chronicle System, Explorer's Society), itch.io fan works for an
  existing game, conversions.
- When the user's library shows they file community content elsewhere
  (`3rd Party/`, `Community/`), follow that instead.

**Magazines** - periodicals and zines.
- *Dragon*, *Dungeon* (adventures, but a periodical), *White Dwarf*,
  *Polyhedron*, *Knock!*, system zines, fanzines, numbered newsletters,
  Patreon monthly issues. Group by title: `Magazines/Dragon Magazine/Dragon 101.pdf`.

**Custom categories** for what fits none of the above, kept few:
- `Fiction` for novels and anthologies set in the game's world.
- `Art Books` for art collections.
- Use the custom category the library already has rather than inventing one.

## 5. Game systems and editions

The top folder under `books/` is the game system. Get it right first.

1. **Reuse what exists.** List the library's systems before choosing a name
   (`grimoire_api.py systems` / `tree`). If *Call of Cthulhu 7e* already exists,
   that exact folder name is the system - not `Call of Cthulhu 7th Edition`, not
   `CoC7`. A near-duplicate system name is the most damaging mistake an import
   can make: it splits the user's shelf in two.
2. **Name a new system the way its publisher does**, with the edition when the
   game has had incompatible editions: `Dungeons & Dragons 5e`,
   `Call of Cthulhu 7e`, `Shadowrun 6e`, `Mothership`, `Blades in the Dark`.
   Keep the publisher's spelling and punctuation (`Mörk Borg`, `Cyberpunk RED`,
   `Vampire: The Masquerade 5e`); avoid characters filesystems dislike (`/ \ : *
   ? " < > |`), replacing a `:` with ` - ` if needed.
3. **Several editions of one game** → a parent-system container (section 6):
   `books/Ars Magica/` + `.parent-system-container`, holding `3rd Edition/`,
   `5th Edition/`. Grimoire then names them "Ars Magica 3rd Edition" and so on,
   and fills in *parent system* and *edition* itself. Use a container when the
   import holds two or more editions, or the library already has one.
4. **Which edition is this book?** Look for: the edition on the cover or title
   page, product codes, copyright year against the edition's publication years,
   rules vocabulary (THAC0 vs. armour class bonuses; 5e "advantage"; PF2
   "three actions"), and the core book it says it requires ("requires the
   Fifth Edition Player's Handbook"). Third-party books state compatibility on
   the cover or legal page ("Compatible with 5E", "for Old-School Essentials").
5. **A book for several systems** (dual-statted, "5E and PF2") goes under the
   system it treats first or most; record the others as tags. A book that is
   genuinely system-neutral goes in the system-agnostic collection.
6. **Licensed engines are not the game.** A *Powered by the Apocalypse*,
   *Forged in the Dark* or *Year Zero Engine* game is its own system (`Monster
   of the Week`, `Scum and Villainy`, `Alien RPG`). A *system family* container
   can group them if the user wants (`Powered by the Apocalypse (system-family)/`).
7. **Retro-clones and OSR**: file under the game the book says it is for (`Old-
   School Essentials`, `Basic Fantasy RPG`, `Shadowdark`). Generic "OSR
   compatible" material with no single target goes to system agnostic (custom
   category `OSR`).

## 6. Containers and special collections

A container is a folder of *systems* rather than of categories, declared by a
marker the file manager writes for you (`grimoire_api.py mkdir <path>
--container <kind>`). Only folders standing where a system belongs (directly
under `books/`, or inside another container) can be containers.

| Kind (`--container`) | Use for | Children become |
|---|---|---|
| `parent` | Editions of one game - `Dungeons & Dragons/` holding `3e/`, `5e/` | "Dungeons & Dragons 5e", with parent system + edition set |
| `family` | Related, distinct systems - `d20 System/`, `Powered by the Apocalypse/` | Independent systems with *system family* set |
| `publisher` | One company's games - `Free League/` | Independent systems with *publisher* set |
| `generic` | A shelf with no claimed relationship - `Kickstarter Hauls/` | Independent systems, no metadata |
| `one-page` | Many tiny games - `One-Page RPGs/` | Each loose file *and* each subfolder is its own system |
| `agnostic` | System-neutral material (see below) | Not systems - its subfolders are categories |

Containers nest: a family can hold a parent-system container.

**System Agnostic** (`books/System Agnostic/`, or `Generic`/`Any`): GM advice,
generic random tables, worldbuilding guides, generic dungeons and maps meant for
any game, game-design books, RPG history and criticism. Its subfolders are
**category headings used as written** (no keyword matching): `System Agnostic/GM
Advice/`, `System Agnostic/Random Tables/`, `System Agnostic/OSR/`. Files loose
in its root show as Uncategorized - always give them a heading.

**One-Page RPGs** (`books/One-Page RPGs/`, also `Micro RPGs`, `One-Shot RPGs`):
complete tiny games - one-page RPGs, game-jam entries, itch.io micro-games,
*Honey Heist*, *Lasers & Feelings*. A single-file game is placed loose in the
collection root (it becomes a one-book system named after the file, so name the
file after the game); a game with several files gets its own folder, which can
hold category folders. Supplements and adventures for a *real* system are never
one-page RPGs just because they are short.

## 7. Subfolder groups

Inside a category, a folder groups related books into a collapsible section.
Group when it helps someone find things; do not group a single book alone.

- **Adventure paths and campaigns in parts**: `Adventures/Abomination Vaults/`
  holding the three volumes.
- **Series and product lines**: `Supplements/Lost Omens/`, `Supplements/13th
  Age Monthly/`, `Magazines/Dragon Magazine/`.
- **A product and its pieces**: a boxed set's books, an adventure with its map
  pack, handouts and pregens.
- **Language editions**: `Core/German/` - or the library's existing convention
  (some libraries use `[DE]`).
- **Community content** when it is filed under a standard category rather than
  Homebrew: `Supplements/3rd Party/<Publisher>/`.

Number volumes so they sort in order: `01 - Ruins of Gauntlight.pdf`, or
`Part 1 - ...`. Match the existing pattern if the folder already has one.

## 8. File names

The file name is what the user sees in the file manager and the first title
Grimoire gives the book. Rename on import:

- **The book's real title**, as printed on its title page, with subtitle after a
  ` - `: `Gradient Descent.pdf`, `Lost Omens - World Guide.pdf`.
- **Drop store and pipeline noise**: product codes (they go in the metadata),
  `_print`, `(1)`, `final`, `[DriveThruRPG]`, `v2_compressed`, underscores,
  scan-group tags, the system name when the folder already says it
  (`Ars Magica 4e - Wonders of Art & Magic.pdf` → `Wonders of Art & Magic.pdf`).
- **Keep what distinguishes versions** in parentheses: `(Printer Friendly)`,
  `(No Art)`, `(Spreads)`, `(Letter)`, `(A4)`, `(v1.1)`, `(2nd Printing)`,
  `(German)`.
- Fix mangled characters (`&amp;` → `&`, `Ã©` → `é`), keep real accents and
  apostrophes, and avoid `/ \ : * ? " < > |`.
- Keep the extension; Grimoire infers the format from it.

## 9. Versions of one book (variants)

The same book as different files - screen and printer-friendly, letter and A4,
single pages and spreads, v1.0 and v1.2, colour and low-ink, with and without
background art - are **versions**, not separate books. Keep them together in the
same folder, named so each is distinguishable:

```
Core/Player's Survival Guide.pdf
Core/Player's Survival Guide (Printer Friendly).pdf
```

Mark the plain one as main and the others with `variant_of` in the plan; after
import, Grimoire's duplicate scanner (Settings → Maintenance → Duplicates) offers
to link them, which folds them into one shelf entry with a version picker. When
two files are *older and newer printings* and the user only wants the newest,
say so and let them decide - never drop a version on your own.

Exact byte-for-byte duplicates (same SHA-256) are not versions: import one.

## 10. NSFW and restricted content

- A system whose content is explicit gets the NSFW marker
  (`mkdir <path> --nsfw`); individual explicit books get `is_explicit: true`
  in their metadata. Decide from what the book itself says (content warnings,
  "adults only"), not from genre - horror is not NSFW. If unsure, flag it for
  the user rather than guessing.
- GM-only material that players in a shared library should not see (adventure
  modules, GM screens) is controlled by access levels, which are the library
  owner's choice. Mention the option; do not set `access_level` unless asked.

## 11. Things that are not books

| Found | Goes to |
|---|---|
| Battle maps sold standalone (images, VTT packs, gridded PDFs meant for any game) | `maps/<Creator or Collection>/<Pack>/` |
| Token, portrait and standee images | `tokens/<Type or Creator>/` |
| Music, ambience, sound effects, audiobooks | `audio/<Creator or Collection>/` |
| STL/OBJ/3MF minis and terrain | `models/<Creator or Set>/` |
| An archive that is a bundle (VTT module, Foundry pack, map pack with sources) | Beside what it belongs to, kept zipped |
| An archive that is just a delivery wrapper for PDFs | Extract it (to a working folder, never into the source) and import the contents |
| `.doc`/`.docx`/`.odt`/`.mobi` | Not importable - list them; offer to convert to PDF if a converter is available |
| Store receipts, `.url` links, `readme.txt`, `.nfo` from a download, `Thumbs.db` | Not imported - list as junk |
| Not tabletop RPG material at all (tax forms, unrelated e-books) | Not imported - list for the user to decide |
