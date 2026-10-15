# Organise a TTRPG library into Grimoire

The end-to-end workflow: from a folder nobody has sorted to books on the right
shelves in Grimoire, named properly, with metadata, and the broken files set
aside with an explanation. It uses the health and identify workflows (`workflows/health.md`,
`workflows/identify.md`) and owns the plan and the changes to Grimoire.

## Ground rules

These hold for the whole job. They exist because a library import touches
hundreds of files the user cares about, and undoing a bad one is miserable.

- **The source is read-only.** Never move, rename, delete or write into the
  pile being imported. Copies, reports and extracted archives go in a working
  folder outside it.
- **Nothing changes in Grimoire until the user approves the plan.** Everything
  before the apply step is reading.
- **Never overwrite, never delete.** Uploads and moves refuse name clashes; a
  clash is a question for the user, not something to resolve with
  `--on-conflict replace`.
- **Every file is accounted for.** Each one ends up imported, held for review,
  quarantined or skipped as junk - with a reason - so nothing silently vanishes.
- **Ask, don't guess** when a decision is the user's: whether to keep a partial
  book, which edition naming they prefer, whether something is NSFW, whether to
  restructure shelves that already exist.

## 0. Set up

1. **Connection.** `G check` must show the file manager and library reachable
   (`can_read` true for files and library) - organising needs an **admin's** key
   with write access to Files, Library and Books. If not connected, or connected
   read-only, run the setup workflow (`G login --url <address>` asks for the
   right access). The library must be mounted writable for uploads (the default).
2. **Working folder.** Create one outside the source, e.g.
   `~/grimoire-import-<date>/`. Everything below writes there.
3. **Dependencies.** Python 3.9+, and PyMuPDF for the PDF steps:
   `python3 -c "import fitz" || pip install pymupdf`.
4. **Which source?** A local folder (files get *uploaded*), or a folder already
   inside the Grimoire library such as `books/Inbox` or a messy existing shelf
   (files get *moved*, keeping their records, tags and bookmarks).

## 1. Learn the library

```bash
G systems > work/systems.json
G tree books --depth 3
G lookups > work/lookups.json
```

Start from the library notes (`G notes`), then write down the conventions the
library already follows: system names and editions,
containers, category folder spellings, language and third-party folders. New
books must join these shelves, not sit beside them. For an empty library, use
the defaults in `references/classification.md`.

## 2. Inventory

```bash
python3 <skill-dir>/scripts/inventory.py <source> --out work/inventory.json
```

Sorts every file into books, images, audio, models, archives, unsupported
formats, unfinished downloads, sidecars, Grimoire marker files and junk.

- **Archives**: list what is inside (`unzip -l`, `7z l`). A delivery wrapper
  around PDFs (a store or bundle download) is extracted into `work/extracted/`
  and inventoried with the rest. A bundle meant to stay together (VTT module, map
  pack with source files) is imported as an archive next to what it belongs to.
- **Unsupported documents** (`.doc`, `.docx`, `.mobi`...): Grimoire cannot
  index them. List them, and offer conversion to PDF if a converter is installed
  (LibreOffice: `soffice --headless --convert-to pdf --outdir work/converted <file>`).
- **Unfinished downloads** (`.part`, `.crdownload`) are reported, never imported.
- **Images**: decide per folder whether they are maps, tokens, book covers
  (`cover.jpg` beside a book - skip) or art.
- **Existing Grimoire markers or `.opf` sidecars** in the source are clues about
  how someone meant it to be organised.

## 3. Health check

Use the health workflow (`workflows/health.md`) on the book files:

```bash
python3 <skill-dir>/scripts/pdf_health.py <source> --hash --out work/health.jsonl
```

(Run it in the background for large piles; it takes minutes to an hour.) Then:

- `broken` / `locked` → quarantine (plan action `quarantine`), with the reason.
  For partially readable books, ask the user whether to import them tagged
  `Health: incomplete`.
- `warn` → import with a health tag (see `references/plan-format.md`).
- Exact duplicates (same SHA-256) → import one copy; mark the rest `skip`.

## 4. Identify

Use the identify workflow (`workflows/identify.md`) on every file that passed:

```bash
python3 <skill-dir>/scripts/extract_evidence.py <source> \
    --out work/evidence.jsonl --digest work/digest.md --covers work/covers \
    --skip-broken work/health.jsonl
```

and follow its process: batches by folder or system, decisions from the book's
own pages first, covers when the text is thin, a confidence and reason for each.
Its references decide system, category, groups, file name, versions and
metadata. Low-confidence files become `review` items, not imports.

## 5. Plan

Write `work/plan.json` in the format in `references/plan-format.md`: one item per
file (including quarantined, skipped and review files), plus the folders that
need container or NSFW markers. Then check it before showing anyone:

- No two system names for one game; every system name matches an existing one
  or is deliberately new.
- No two items with the same destination path.
- Every category folder name is read as the category you intend (classification
  section 3) - especially new custom categories.
- Versions of one book share a folder and have distinct names.
- Metadata only where there was evidence.

Then dry-run it against the server, which also proves the paths are valid:

```bash
G apply work/plan.json --dry-run
```

## 6. Review with the user

Write `work/plan.md` (the summary layout is in `references/plan-format.md`) and
walk the user through it: new systems and containers first, then the destination
tree, notable renames, the needs-review list, the quarantine list. Ask
specifically about anything you were unsure of. Apply their corrections to
`plan.json` and show the changed parts again.

**Stop here until the user explicitly approves.** For a large import, offer to
apply one system at a time so they can check the first result in Grimoire
before the rest.

## 7. Apply

```bash
G apply work/plan.json
```

It creates folders, uploads or moves the files, rescans only what needs
indexing, patches metadata and adds health tags, saving progress to
`work/plan.state.json` after every step. If anything fails or is interrupted,
fix the cause and run the same command again - finished items are not repeated.
Report per-item errors to the user rather than retrying blindly; a `409` is a
name clash that needs a decision.

Large uploads take time (a 7 GB pile is a long transfer) - run the apply in the
background and report progress.

## 8. Enrich from Grimoire Codex DB and add-ons

If `check` showed Codex DB enabled, or the server has metadata add-ons
(`G sources <id>`), look each imported book up - the apply report's
`records` maps plan ids to book ids - following
`references/metadata-fields.md` section 5. Batch the results into one table of
proposed changes for the user (or apply clear high-score matches if they said to),
then `patch`. Linking `codex_id` is worth doing for every confident match.

## 9. Verify and report

- `G tree books --depth 3` - the shelves look as planned.
- Spot-check a few books: `G book <id>` shows the right system,
  category and metadata; `G scan-status` shows OCR progress for
  scans (Grimoire OCRs image-only PDFs in the background).
- If the plan has `variant_of` links, tell the user to run the duplicate scan
  (Settings → Maintenance → Duplicates) to fold versions into one entry, or list
  the book id groups.

Finish with a report (also saved to `work/report.md`):

1. What was imported, by system and category, with counts.
2. New systems and containers created.
3. **Quarantined files** and why - the user's to-replace list.
4. **Needs review** files and what would identify them.
5. Books imported with health tags, and what each tag means.
6. Junk and unsupported files that were left behind.
7. Follow-ups: duplicate linking, OCR still running, Codex DB matches declined.

The source folder is left exactly as it was; the user decides what to delete.

Add a line to the library notes' `## History` (date, source, counts), and any
convention or preference the user settled during review to `## Conventions` /
`## Preferences`, so the next import starts from them.
