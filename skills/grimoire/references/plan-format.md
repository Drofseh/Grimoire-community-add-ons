# The organisation plan (`plan.json`)

The plan is the single reviewed artifact between "what we found" and "what we
change". `grimoire_api.py apply` reads it and does exactly what it says - no
judgement happens at apply time - so everything the user should approve must be
in it.

## Shape

```json
{
  "version": 1,
  "source": {"kind": "local", "root": "/Users/me/Downloads/unsorted-rpg"},
  "folders": [
    {"path": "books/Starfall", "container_kind": "parent"},
    {"path": "books/Velvet Knives", "nsfw": true}
  ],
  "items": [
    {
      "id": "0001",
      "source": "Starfall [multi]/2e/SF2_core_FINAL(1).pdf",
      "action": "upload",
      "dest_dir": "books/Starfall/2nd Edition/Core",
      "dest_name": "Starfall Second Edition.pdf",
      "confidence": "high",
      "reason": "title page; EXP2001 on back cover; (c) 2019 Example Press",
      "health": "ok",
      "health_tags": [],
      "variant_of": null,
      "metadata": {
        "title": "Starfall Second Edition",
        "authors": ["Jane Writer", "Lee Designer"],
        "publisher": "Example Press",
        "year": 2019,
        "product_code": "EXP2001",
        "language": "English"
      }
    },
    {
      "id": "0002",
      "source": "Starfall [multi]/2e/SF2_core_print.pdf",
      "action": "upload",
      "dest_dir": "books/Starfall/2nd Edition/Core",
      "dest_name": "Starfall Second Edition (Printer Friendly).pdf",
      "confidence": "high",
      "reason": "same book as 0001, white background, no art",
      "variant_of": "0001",
      "metadata": {"title": "Starfall Second Edition (Printer Friendly)"}
    },
    {
      "id": "0003",
      "source": "misc/Agon 2E.pdf",
      "action": "quarantine",
      "reason": "unfinished download: middle of the file is zero bytes; pages 9-59 blank"
    }
  ]
}
```

## Fields

**`source`**
- `kind: "local"` - files on this machine; `root` is the folder item `source`
  paths are relative to. Items use `action: "upload"`.
- `kind: "library"` - files already inside the Grimoire library (an inbox folder,
  or a messy existing shelf); item `source` values are library paths such as
  `books/Inbox/x.pdf`. Items use `action: "move"`, which keeps each book's record,
  tags, bookmarks and campaign links.

**`folders`** - folders that need a marker. Only list folders with a
`container_kind` (`parent`, `family`, `publisher`, `generic`, `one-page`,
`agnostic`) or `nsfw: true`; every other destination folder is created
automatically, parents included. Existing folders get their markers updated.

**`items[]`**

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable, unique string. The state file is keyed on it, so never renumber a plan that has been partly applied |
| `source` | yes | Path relative to `source.root` (local) or a library path (library) |
| `action` | yes | `upload`, `move`, or a non-acting `skip` / `quarantine` / `review` |
| `dest_dir` | for upload/move | Library folder, starting with a collection: `books/...`, `maps/...` |
| `dest_name` | no | New file name, extension included. Defaults to the source name |
| `confidence` | yes | `high` / `medium` / `low` - low items should be `review`, not placed |
| `reason` | yes | One line: the evidence the decision rests on, or why the file is held back |
| `health` | no | The health verdict (`ok` / `warn`) |
| `health_tags` | no | Tags added to the book after import, e.g. `["Health: missing pages"]` |
| `variant_of` | no | `id` of the main version of this book; recorded for linking after import |
| `metadata` | no | Fields for `PATCH /api/books/:id` - see the identify skill's `references/metadata-fields.md`. `category` is ignored |

Actions `skip`, `quarantine` and `review` are never applied; they exist so the
plan accounts for every file and the report can list them.

## How `apply` behaves

1. Creates the marked folders, then every missing destination folder.
2. Uploads (`on_conflict=skip`) or moves each item, renaming to `dest_name`.
   A name clash is an error for that item only - nothing is ever overwritten. On
   a re-run, a file already at the destination with the same size counts as done.
3. Looks up each placed file's record. Moves keep theirs; uploads are indexed by
   one scoped rescan per top-level folder (`books/<System>`), and only when
   something is still unindexed.
4. Patches metadata. For **uploads** the plan's values win (the record only holds
   the scanner's filename guesses). For **moves** it only fills empty fields -
   plus a title the scanner derived from the old file name - unless `--overwrite`.
5. Adds `health_tags` (additive; existing tags are kept).

Progress is written to `<plan>.state.json` after every step, so an interrupted
apply is resumed by running the same command again. `--dry-run` prints every
action and creates nothing.

Variant linking is not automatic: after apply, run Grimoire's duplicate scan
(Settings → Maintenance → Duplicates) or tell the user which ids belong
together (`records` in the apply report maps plan ids to book ids).

## Health tags

Use one consistent vocabulary so the user can filter on it later:

| Tag | When |
|---|---|
| `Health: missing pages` | `missing_pages`, `toc_tail_unresolved`, `toc_points_past_end` |
| `Health: incomplete` | A partial file imported deliberately (renders only up to some page) |
| `Health: blank pages` | `blank_pages` at warning level |
| `Health: damaged pages` | `unreadable_pages` at warning level |
| `Health: repaired` | A rebuilt copy from `--repair-out` was imported instead of the original |

## Plan review summary (`plan.md`)

Show the user a summary rather than the JSON:

1. Totals: files found, to import, held back (quarantine / review / skip).
2. **New game systems and containers** this creates - the decisions most
   worth checking, listed first.
3. The destination tree with counts per folder.
4. Renames worth seeing (a sample, plus every one where the identity changed).
5. **Needs review** (low confidence) with what was found and what would settle it.
6. **Quarantine** with the reason for each file.
7. Health warnings that will become tags.
