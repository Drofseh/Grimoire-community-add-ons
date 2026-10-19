# Grimoire PDF health check

Find the books that are broken or incomplete *before* they go into a Grimoire
library, and say plainly what is wrong with each. The source files are never
changed.

## Run the checker

`<skill-dir>/scripts/pdf_health.py` does the work. It needs no Grimoire
connection - only Python 3.9+ and, for page-level checks, PyMuPDF (the PDF engine
Grimoire itself uses):

```bash
python3 -c "import fitz" 2>/dev/null || pip install pymupdf
python3 <skill-dir>/scripts/pdf_health.py <folder-or-files> --hash --out health.jsonl
```

- Write the report somewhere outside the source folder (a working directory
  for this job), never inside the pile being checked.
- `--hash` adds a SHA-256 per file and lists exact duplicates in the summary.
- `--quick` samples ~60 pages per book instead of reading every page - use it
  for a first pass over thousands of files, then re-run the flagged ones in full.
  Quick mode skips the missing-page check, which needs every page.
- Full mode runs at roughly 4-5 books per second on 8 cores for typical PDFs; a
  large library takes minutes to an hour. Run big jobs in the background and
  report progress.
- Each file is opened in its own worker process with a timeout (`--timeout`,
  default 300s), so a file that crashes or hangs the PDF engine is reported as
  broken instead of stopping the run.

Each line of the JSONL report is one file: `verdict`, `pages`, `text_layer`,
and an `issues` list of `{code, severity, detail}`, plus details such as
`blank_pages`, `unreadable_pages` and `page_number_gaps`.

## Read the verdicts

| Verdict | Meaning | What to do |
|---|---|---|
| `ok` | Opens, every page renders, nothing missing | Import |
| `warn` | Usable, but damaged, padded or incomplete | Import if wanted, tagged so the user can find and replace it later |
| `broken` | Will not open, is not a book, or is mostly unreadable | Do not import. Quarantine and list it |
| `locked` | Needs a password | Do not import. Ask the user for the password or a clean copy |

Issue codes, worst first:

- **`wrong_type`** - the extension lies. `html` is a saved web page: a failed,
  expired or login-walled download link. `zero-filled` is an unfinished download.
  `zip` usually means a bundle that should be extracted first.
- **`zero_filled`** - part of the file was never written (torrent, sync client or
  copy interrupted). The pages before the hole may still render, which is why
  these files open but fail part-way through.
- **`empty_file`**, **`unreadable`**, **`crashed`**, **`timeout`**, **`no_pages`**,
  **`archive_corrupt`**, **`epub_invalid`** - unusable.
- **`unreadable_pages`** - specific pages fail to render. An error when more than
  ~5% fail, otherwise a warning.
- **`truncated`** - no end-of-file marker. On its own it is a warning (some
  generators omit it); together with `unreadable_pages` it means the end of the
  book is missing.
- **`xref_repaired`** - the file's index was damaged and rebuilt on open. Usually
  fine to import; `--repair-out` writes a clean copy.
- **`missing_pages`** - the printed page numbers jump (printed 64 is followed by
  printed 90). Only numbers confirmed by a neighbouring page count, numbering
  restarts are ignored, and scans of two-page spreads are allowed for. A single
  one-page skip is reported as info: digital editions often drop a blank verso.
- **`toc_tail_unresolved`** / **`toc_points_past_end`** - the last bookmarks lead
  nowhere, so the end of the book is probably gone. Check the filename first: an
  "excerpt", "preview" or "sample" keeps the full book's bookmarks on purpose.
- **`blank_pages`** - a warning for a run of 3+ blank pages or 4+ blanks making up
  15%+ of the book. Long runs in the middle of a book alongside `zero_filled` are
  damage; scattered single blanks are usually deliberate (inside covers,
  "intentionally left blank").
- Informational only: `no_text_layer` (a scan - Grimoire OCRs it after import),
  `duplicate_pages` (card backs and handout packs repeat pages on purpose; a
  doubled scan page loses nothing), `toc_unresolved`.

## Judge the edge cases

The checker reports evidence; you make the call, using the rest of the context:

- **Salvageable partial books.** A broken file whose first 75 pages render may
  still be the user's only copy. Say how much is readable ("pages 1-76 of 233")
  and let them decide whether to import it tagged as incomplete or wait for a
  replacement. Never decide to discard on their behalf.
- **Duplicates.** Exact duplicates (same SHA-256) need only one copy imported.
  When one copy of a book is broken and another is fine, keep the good one.
  Different files with the same title are *versions*, not duplicates - see the
  identify workflow.
- **Card decks, maps and sheets** produce duplicate and blank-looking pages by
  design. A 2-page character sheet with one blank back page is fine.
- **Non-PDF formats** get structural checks only: EPUB/CBZ/ZIP archives are
  tested for corruption, other formats only for a lying extension.

## Repaired copies

`--repair-out <dir>` writes rebuilt copies of damaged-but-readable PDFs (damaged
index, truncation, unreadable pages) into `<dir>`, mirroring the source layout.
`--drop-blank` also removes the blank pages from those copies. Originals are never
touched. Rebuilding fixes the file's structure, not lost content - a page that
failed to render stays missing. Tell the user which files were rewritten and why,
and import the repaired copy instead of the original only with their agreement.

## Report

Give the user a short summary, not the raw JSON:

1. Counts by verdict.
2. **Broken and locked files**, one line each: the file and the reason in plain
   words ("unfinished download - the second half is empty").
3. **Warnings** grouped by kind: missing pages (with where), blank padding,
   repaired structure.
4. Exact duplicate groups, and which copy to keep.

When this runs as part of the organize workflow, hand the report back to it: broken and locked files go to its quarantine list, and warnings become
health tags on the imported books.
