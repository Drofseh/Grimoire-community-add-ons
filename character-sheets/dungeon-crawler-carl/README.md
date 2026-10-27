# Dungeon Crawler Carl

An unofficial crawler sheet for the **Dungeon Crawler Carl Roleplaying Game**,
following the content, order and look of the printed character sheet.

## What it covers

Five pages, in the printed sheet's order:

- **Crawler** - name, race, pronouns, level, crawler number, class and floor;
  the five stats, each enhanced and unenhanced with its modifier; **health** as
  ten boxes of 10%; **evade** (DEX modifier + buffs) and **damage resistance**
  (armor + buffs) as the sums the sheet prints, with move, step, AI favor and
  size; mana; debuffs and up to three external buffs; and five **attacks**, each
  with its to-hit (rank + stat modifier) and damage (dice + stat modifier)
- **Hotlist & Gear** - the hotlist, gear slots, accessories (a warning past ten),
  popularity, past trauma, loose ends, regrets and notes
- **Skills & Inventory**
- **Companions & Life** - pet, mount or vehicle, important things you've killed,
  personal space, clubs and societies, and your deity
- **Abilities & Sponsors** - racial and class abilities and three sponsors

A sixth tab, **Catalog**, is not on the printed sheet. It picks entries from an
installed content pack: a race, class and deity, and lists of skills (with your
rank), spells (with your rank), gear (worn or not) and achievements. Each pick
opens the entry's full text. The printed-sheet tabs are unchanged, so a crawler
can be kept either way, or both.

## Content types

For a content pack written for this sheet (`schema_id: dungeon-crawler-carl`),
one file per type:

| Type | Properties |
| --- | --- |
| `race` | `name`, `origin` (Earth or Alien), `size`, `prerequisites`, `description` |
| `class` | `name`, `class_type`, `prerequisites`, `description` |
| `deity` | `name`, `title`, `temple`, `signature_skills`, `signature_stat`, `description` |
| `skill` | `name`, `kind` (Attack, Damage Effect or Utility), `category`, `keywords`, `stat`, `ai_favor`, `base_damage`, `description` |
| `spell` | `name`, `keywords`, `favored`, `mana_cost`, `range`, `duration`, `cooldown`, `base_damage`, `description` |
| `gear` | `name`, `slot` (one of the sheet's gear slots), `gear_slot` (as printed), `found_in`, `book`, `description` |
| `achievement` | `name`, `location`, `floor`, `reward`, `contents`, `description` |

## Rules not included

The sheet carries the structure of a crawler and the sums the printed sheet
itself shows; it includes no rules text, stat tables, artwork or logo. Stat
modifiers are fields you fill in from your book rather than formulas. No content
pack ships with it - the game's text is not openly licensed.

Dungeon Crawler Carl is a trademark of Matt Dinniman LLC; the roleplaying game
is © Renegade Game Studios. This sheet is not affiliated with, endorsed by, or
approved by either.
