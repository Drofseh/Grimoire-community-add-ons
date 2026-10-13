# Writing a character importer

A character importer reads a character built in another tool - a Forge Steel
hero, a Pathbuilder export - and maps it onto the fields of one of the
[character sheets](../character-sheets/README.md) in this repository. Grimoire
users then pick **Characters → Import a character**, drop the file in, and get
a character on that sheet.

Grimoire has no built-in knowledge of any tool. Every importer is an add-on here,
so a tool that changes its export format is fixed by a pull request, not a
Grimoire release.

**Who can install it depends on what it does.** An importer that reads uploaded
files with YAML alone - no `script`, no `url` - makes no network request and runs
no code, so any user may install it for their own account from the import
dialog, as they would a character sheet. One that fetches links has the server
contact another site, and one with a script runs code, so an admin installs
those for everyone under **Settings → Add-ons → Character importers**. Keep an
importer file-only and YAML when you can; it reaches far more people.

Most importers are a page of YAML. The two shipped ones are worth reading
before you start:

| Importer | Reads | Shows how to |
| --- | --- | --- |
| [`pathbuilder-2e`](../importers/pathbuilder-2e/pathbuilder-2e.yml) | A flat JSON export | Look values up (`values`), read member names (`keys`), fill list rows (`columns`) |
| [`forge-steel`](../importers/forge-steel/forge-steel.yml) | A file that embeds every option with the choices marked | Read only what is in play with filters, and tell same-named content apart (`match`) |

- [The manifest](#the-manifest)
- [Recognising input](#recognising-input)
- [Paths](#paths)
- [Fields](#fields)
- [Catalog fields](#catalog-fields)
- [List fields](#list-fields)
- [Scripts](#scripts)
- [Testing](#testing)
- [What an importer should not do](#what-an-importer-should-not-do)

## The manifest

An importer lives in `importers/<id>/<id>.yml`:

```yaml
$schema: ../../schema/addon.schema.json
id: my-builder
name: My Builder
kind: character-importer
version: 1.0.0
description: Characters from My Builder's JSON export.
homepage: https://my-builder.example
author: your-github-name
attribution: My Builder by Someone (my-builder.example)
grimoire_min_version: 1.9.0

importer:
  sheet: dnd-5e-2024           # the sheet id in character-sheets/
  extensions: [.mbchar]        # optional
  detect: [$.character.stats]  # optional
  name: $.character.name
  fields:
    hero_name: $.character.name
    level: $.character.level
```

`id`, `name`, `version`, `description`, `homepage`, `author`, `attribution` and
`grimoire_min_version` mean what they do for a scraper - see
[`format.md`](format.md#identity). `kind` is `character-importer`; `target` is
always `character` and can be left out. Set `grimoire_min_version` to `1.9.0`
or later: older Grimoire does not know this kind.

`attribution` credits the tool. Grimoire shows it in the import dialog.

## Recognising input

Users do not pick an importer - they drop a file in, and Grimoire works out
whose it is. An importer needs at least one of these:

| Key | Matches |
| --- | --- |
| `extensions` | Files with one of these extensions, lowercase with the dot: `[.ds-hero]` |
| `detect` | Files where every one of these [paths](#paths) selects something that is not empty, `false` or `0` |
| `url` | Pasted links - see [Links](#links) |

With both `extensions` and `detect`, a file needs both. Declaring only
`extensions` is fine for a format with its own extension. A tool that exports
plain `.json` needs `detect`, or it would claim every JSON file anyone uploads.
Choose `detect` paths that only that tool's export has.

When two importers claim the same file, the user is asked to choose one, so
`detect` that is too loose is an annoyance, not a disaster - but make it tight.

Grimoire's own export files never reach an importer.

### Links

```yaml
  url:
    pattern: 'my-builder\.example/c/(\d+)'
    fetch: https://api.my-builder.example/characters/{identity}.json
    hint: https://my-builder.example/c/123456
```

`pattern` is a regular expression with exactly one capture group: the
character's id. `fetch` is the JSON endpoint Grimoire requests with that id in
place of `{identity}`. `hint` is the paste box's placeholder.

Grimoire never requests the link the user pasted - only your `fetch` URL - so a
pasted link cannot point the server anywhere you did not name. The id must be
plain (`A-Z a-z 0-9 . _ ~ -`, 200 characters at most). Responses are never
cached; they are someone's character. When the importer also has `detect`, a
fetched document has to pass it too, so a "no such character" answer reads as
one.

Check that the endpoint answers a server. Some sites put their whole domain
behind a bot challenge that only a browser passes - Pathbuilder does, which is
why its importer reads files only. Do not try to get past one.

## Paths

Values are read with JSONPath. `$` is the root of the document; `@` is the
current item (inside a filter, and in `name`, `description`, `match` and
`columns`).

| Path | Selects |
| --- | --- |
| `$.class.level` | A member |
| `$['class']['level']` | The same, for names with spaces or dots |
| `$['ancestry', 'career']` | Several members |
| `$.feats[0]`, `$.feats[-1]` | An item by index, from the end with a minus |
| `$.feats[1:3]` | A slice |
| `$.feats[*]`, `$.class.*` | Every item or member |
| `$..selected` | `selected` at any depth |
| `$..[?(@.type == 'Perk')]` | Anything at any depth that passes the filter |
| `$.items[?(@.qty > 1)]` | The items that pass the filter |

Filters compare with `==`, `!=`, `<`, `<=`, `>`, `>=` and `in`; combine with
`&&`, `||` and `!`; and group with parentheses. Either side may be a path
(`@...` or `$...`), a quoted string, a number, `true`, `false` or `null`.

- **A bare path is a truthiness test.** `[?(@.selected)]` keeps items whose
  `selected` is set and not `false`, `0` or empty.
- **A path that selects several values matches when any of them does.**
- **`in` looks inside a list.** `$.abilities[?(@.id in $..selectedIDs)]` keeps
  the abilities whose id is among the ids selected anywhere in the file.
- **Comparing different kinds never matches.** `'Might' < 3` is simply false,
  and `false == 0` is false, as in JSON.
- **An absolute path inside a filter** reads from the root:
  `$.class.featuresByLevel[?(@.level <= $.class.level)]` keeps the levels the
  hero has reached.

There is no arithmetic and no function call. If a value needs working out,
leave it to the sheet - see [What an importer should not do](#what-an-importer-should-not-do).

## Fields

`fields` maps a sheet field to where its value comes from. A field the sheet
does not declare is dropped, so check the names against the sheet - Grimoire's
test suite fails an importer that maps a field its sheet lacks.

The shortest form is a path:

```yaml
    level: $.build.level
```

The long form is an object with exactly one source:

| Key | Gives |
| --- | --- |
| `from` | A path, or a list of paths whose results are concatenated |
| `template` | Text with `{$.path}` or `{@.path}` placeholders: `"{$.career.name}: {$.career.motto}"`. Dropped when every placeholder is empty |
| `value` | A constant |

and any of:

| Key | Does |
| --- | --- |
| `transform` | A named transform, or a list applied in order - see below |
| `values` | A lookup from the tool's vocabulary to the sheet's: `{cha: charisma}`. A value with no entry passes through |
| `keys` | Read the member names a path selects instead of their values. `{from: "$.proficiencies[?(@ == 2)]", keys: true}` gives the skills ranked 2 |
| `join` | Join every value into one string with this separator, dropping repeats |

Transforms run first, then `values`, then `join`. They are the scraper
transforms (`slugify`, `titlecase`, `upper`, `lower`, `trim`, `upper_dice`,
`strip_query`, `strip_html`) plus two for characters:

| Transform | Does |
| --- | --- |
| `modifier` | An ability score as its modifier: `18` → `4`, `9` → `-1` |
| `signed` | A number with its sign: `4` → `+4` |

A field may also take a **list of mappings**, whose values are concatenated -
useful when one field is fed from places that need different settings:

```yaml
    equipment:
      - from: $.build.armor[*]
        columns: { name: "@.display", qty: "@.qty" }
      - from: $.build.equipment[*]
        columns: { name: "@[0]", qty: "@[1]" }
```

### What each field type keeps

Mappings yield a list of values; the field's type in the sheet decides what is
kept, so a definition does not have to say:

| Sheet field | Keeps |
| --- | --- |
| `number`, `checkbox`, `select` | The first value |
| `text`, `textarea` | The first value; several are joined with `, ` (a newline in a `textarea`) unless you set `join` |
| `multiselect` | Every value that is one of the field's options |
| `content_ref` | The first value, as a [catalog](#catalog-fields) entry |
| `content_list` | Every value, as catalog entries, without repeats |
| `list` | Every row - see [List fields](#list-fields) |

Values are then checked exactly as a hand-edited sheet's are: numbers clamped
to `min`/`max`, a select value that is not an option dropped. A field whose
paths select nothing is left out entirely, so the sheet's own default or
`default_from` formula still applies.

`name` (beside `fields`) is the character's name; without it, the sheet's
`name_field` is used. `portrait` is a path to a `data:image/...;base64,` URL (PNG,
JPEG, WebP or GIF, 5 MB at most). An image link is ignored: an uploaded file
must not be able to send the server off to fetch an address of its choosing.

## Catalog fields

`content_ref` and `content_list` fields hold references to content-pack and
ruleset entries. An importer gives **names**, and Grimoire matches each one,
ignoring case, against the entries of the field's content type that are
installed and that the user can read. A match becomes a reference; anything
else is kept on the character as a custom entry, so nothing is lost when the
user lacks a pack.

A value can be a plain string, or an object. For objects, say where the name
and description are - paths relative to each object:

```yaml
    abilities:
      from: $.class.abilities[?(@.id in $..selectedIDs)]
      name: "@.name"            # the default
      description: "@.description"
```

The description is only used for a custom entry, so a user without the pack
still has the text.

### Same name, different entry

Content often reuses names: every Draw Steel class has a feature called
"Skills". `match` lists properties an entry must also have to count:

```yaml
    features:
      - from: $.class.featuresByLevel[?(@.level <= $.class.level)].features[*]
        match:
          origin: $.class.name
      - from: $.class.subclasses[?(@.selected)].featuresByLevel[*].features[*]
        match:
          origin:
            template: "{$.class.name} ({$.class.subclasses[?(@.selected)].name})"
```

Each value is read like any other mapping, for each item. When an entry with the
right name fails the criteria, the item becomes a custom entry rather than
borrowing the wrong one.

## List fields

A `list` field's rows are built with `columns`, mapping each column key to a
path relative to each row:

```yaml
    strikes:
      from: $.build.weapons[*]
      columns:
        name: "@.display"
        bonus: { from: "@.attack", transform: signed }
        damage: { template: "{@.die} {@.damageType}" }
```

A row may itself be a list - Pathbuilder's `["Rope", 1]` - read with `@[0]`.
Columns you do not map get the sheet's default.

## Scripts

When YAML cannot express a format - a binary or XML export, an API that needs
several requests or a key - an importer may ship a script, on the same terms as
a scraper: the admin must allow add-on scripts and approve this one, and it
runs in a subprocess with no database. Prefer YAML; a script is code someone
has to trust. See [`scripts.md`](scripts.md) for the security model.

```yaml
kind: character-importer
script:
  entry: my_builder.py
importer:
  sheet: dnd-5e-2024
  extensions: [.xml]
  url:
    pattern: 'my-builder\.example/c/(\d+)'   # `fetch` may be left out
```

The script gets an `import` request:

```json
{
  "action": "import",
  "document": { "...": "the file, parsed, or the fetched link - null when neither is JSON" },
  "text": "the file as uploaded",
  "filename": "Hero.xml",
  "identity": "123456",
  "inputs": { "api_key": "..." },
  "addon_dir": "/data/add-ons/my-builder"
}
```

`identity` is set for a link whose importer has no `fetch`, so the script can
make the requests itself. `inputs` holds what the user typed for the importer's
[inputs](#inputs). It answers with what the YAML engine would produce:

```json
{
  "name": "Ash",
  "portrait": "data:image/png;base64,...",
  "fields": {
    "level": 3,
    "skills": ["Climb", "Hide"],
    "spells": ["Fireball", { "name": "Homebrew Bolt", "description": "Mine." }],
    "equipment": [{ "name": "Rope", "qty": 1 }]
  }
}
```

The same rules apply to the answer: each field is kept according to its type,
catalog values are matched by name (an object may carry `match`), and
everything is checked against the sheet. A script that wants a remote portrait
fetches it and returns a data URL.

### Inputs

Some sources need something from the user: an API key for a private character,
a password. Declare it, and the import dialog shows a field for it:

```yaml
importer:
  inputs:
    - key: api_key
      label: DiceCloud API key
      help: Only needed for a private character. Find it under Account → API.
      secret: true       # a password field
      when: link         # always | file | link
      required: false
```

| Key | Means |
| --- | --- |
| `key` | What the script reads it as: lowercase letters, digits and `_` |
| `label`, `help` | What the dialog shows |
| `secret` | Show a password field rather than a text field |
| `when` | Which kind of import it belongs to - a key for a link means nothing to an uploaded file |
| `required` | Ask for it before the script runs |

Up to five per importer. Inputs need a script: a YAML importer has nowhere to
send them.

What the user types goes to the script in that one import's request, as
`inputs`, and nowhere else. Grimoire never stores it, never logs it, and passes
the script only the keys it declared for that kind of import. Hold up your end:
**never echo an input back** - not in an error message, not in a field - and
send it only to the service it is for.

Most credentials are only sometimes needed - a public DiceCloud sheet imports
without a key, a private one does not. Leave those `required: false`, and when
the script finds it needs one, ask for it by naming it in `needs_input`:

```json
{ "error": "This character is private - paste your API key.", "needs_input": ["api_key"] }
```

The dialog shows the error, selects this importer, highlights the field, and
offers **Try again** with the same file or link. A key the importer did not
declare is ignored and the error is reported as an ordinary failure.

A server-wide fallback - one key the admin sets for everyone - is the script's
business: read an environment variable of your own naming
(`os.environ.get("DICECLOUD_API_KEY")`) when `inputs` has none. Scripts run
with the server's environment.

## Testing

Before opening a PR:

1. **Build the index.** `python3 scripts/build_index.py` checks the manifest
   against the JSON Schema and adds it to `index.json`.
2. **Load it in Grimoire.** With the `grimoire` repository checked out beside
   this one, `python3 -m pytest backend/tests/test_bundled_importers.py` loads
   every importer through Grimoire's own validator - which compiles every path,
   and checks every mapped field exists on the sheet.
3. **Import a real export.** Drop the directory into `DATA_PATH/add-ons/<id>/`
   of a Grimoire instance and restart, or point **Settings → Add-ons** at a
   local index (`python3 -m http.server 8000`, then
   `http://localhost:8000/index.json`). Import a few characters from the tool
   and read the result on the sheet, including **All values**.

Do not commit someone else's character as a test file. Build a small one by
hand that has the shape of the real thing.

## What an importer should not do

Importers follow the same [rules as sheets](../character-sheets/README.md#what-belongs-in-a-sheet).

- **Leave derived values to the sheet.** Hit points, armour class, speed and
  stamina are worked out from the class, ancestry and kit. Setting them makes
  them the player's own value, frozen at whatever the file said, and they stop
  following the character as it levels up. Import what the player chose -
  scores, picks, skills, equipment - and let the arithmetic happen.
- **Import what is in play, not what is on offer.** Some tools put every option
  in the file and mark the choices. Read the choices, and only for the levels
  the character has reached.
- **Never send the character anywhere.** An importer reads; it does not
  upload, sync or phone home.
