# Identify TTRPG books and classify them for Grimoire

Turn "a file called `ARM5_dl_final(2).pdf`" into "Ars Magica 5th Edition core
rulebook, Atlas Games, 2004 - `books/Ars Magica/5th Edition/Core/Ars Magica Fifth
Edition.pdf`", with metadata, a confidence and a one-line reason.

Two references hold the rules - read them before classifying anything, and
let the library notes (`G notes`) override them where they differ:

- `references/classification.md` - where things go: collections, systems and
  editions, categories and how folder names are read, containers, special
  collections, groups, file names, versions.
- `references/metadata-fields.md` - how to identify a book, what goes in each
  metadata field, confidence levels, Codex DB lookups.

## 1. Learn the target library first

When a Grimoire library is connected, look at it before deciding anything, so new books join the
user's existing shelves instead of forming parallel ones:

```bash
G systems          # existing systems, containers, editions
G tree books       # existing category and group folders
G lookups          # the genre and license names the library uses
```

Note the library's conventions - system naming (`D&D 5e` or `Dungeons & Dragons
5e`), category folder spellings, how it marks languages and third-party content
- and follow them over the defaults in the references. With no server, use the
defaults.

## 2. Extract the evidence

```bash
python3 -c "import fitz" 2>/dev/null || pip install pymupdf
python3 <skill-dir>/scripts/extract_evidence.py <folder-or-files> \
    --out evidence.jsonl --digest digest.md --covers covers/ \
    [--skip-broken health.jsonl]
```

Keep outputs in a working folder outside the source. `--skip-broken` takes the
the health workflow report and skips files that cannot be opened.

- `digest.md` - one row per file (path, pages, embedded title/author, opening
  text, clues). Read this first to see the shape of the pile.
- `evidence.jsonl` - the full record per file: filename clues (title guess,
  product codes, edition, version, variant and status words, series numbers),
  folder path, embedded and XMP metadata, page size and count, form fields,
  bookmarks, the text of the opening, credits and legal pages, ISBNs, copyright
  years, credit lines, licence and third-party-programme phrases, a language
  guess, any `.opf` sidecar, and a rendered cover.
- Covers are PNGs - look at them (Read the image) whenever the text is missing
  (`text_layer: false`), ambiguous, or the title is artwork.

## 3. Identify and classify

Work through the files in batches - one folder, series or system at a time,
around 10-25 files per batch - so related books are decided together:

1. **What is it?** Title, system, edition, publisher, and what kind of book,
   from the evidence in priority order (metadata-fields.md section 1). Use your
   own knowledge of published RPG lines to recognise products and product codes,
   but confirm against the book's pages; say when you are relying on knowledge
   alone.
2. **Where does it go?** System folder (an existing one if it exists), category
   (classification.md section 4), group folder when it is part of a series or
   product, and the cleaned file name.
3. **Which versions belong together?** Same book, different file (printer
   friendly, A4, spreads, v1.1) → same folder, distinct names, `variant_of` the
   main copy.
4. **What metadata?** Only fields with evidence (metadata-fields.md section 3).
5. **How sure?** high / medium / low, with a one-line reason naming the
   evidence ("title page + AG0256 on back cover", "filename only").

Decide consistently across the batch: every volume of an adventure path in the
same group, every book of one game under the same system name.

For a large pile, independent batches (different systems) can be identified in
parallel by subagents, each told to read this workflow and its references, given its batch of evidence records and
the library's conventions from step 1; merge their results and check the merged
set for conflicting system names before going on.

## 4. Output

For each file produce:

```json
{
  "source": "relative/path/as/found.pdf",
  "collection": "books",
  "dest_dir": "books/Mothership/Adventures",
  "dest_name": "The Drowned Spire.pdf",
  "confidence": "high",
  "reason": "title page and credits; (c) 2023 Example Press; 'a module for Mothership 1e' on the cover",
  "variant_of": null,
  "metadata": {
    "title": "The Drowned Spire",
    "authors": ["Jane Writer"],
    "artists": ["Sam Painter"],
    "publisher": "Example Press",
    "year": 2023,
    "language": "English",
    "description": "A flooded research-station module for Mothership, with a station map and six pregenerated crew."
  }
}
```

When this runs inside the organize workflow, these become the items of its
plan (see `references/plan-format.md`). On its own, present the
results as a table grouped by system - file, proposed location, confidence,
reason - followed by the low-confidence files and what would identify them.
