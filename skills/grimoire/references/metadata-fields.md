# Identifying a book and filling its metadata

How to work out what a file is, and what to put in each Grimoire metadata field.
The rule over all of it: **record what the book says about itself, and leave a
field empty rather than guess.** An empty field is a gap the user or a later
lookup can fill; a wrong value is a fact that is quietly false.

## Contents

1. Evidence, strongest first
2. Traps
3. The metadata fields
4. Confidence
5. Looking it up: Grimoire Codex DB and add-ons

---

## 1. Evidence, strongest first

1. **The book's own front and legal pages** - title page, credits, copyright
   block (`page_text`, `credit_lines`, `copyright_years`, `isbn_in_text`,
   `product_codes_in_text`). The publisher wrote these; they are the best source
   for title, authors, artists, publisher, year, ISBN and product code.
2. **The cover image** (`cover_image`). Read it when the text is thin or absent:
   title, logo, edition badge, "Compatible with 5E" seals, publisher logo.
3. **A metadata record** - a Grimoire Codex DB or add-on match (section 5), or
   a `.opf` sidecar beside the file (`sidecar_opf`, usually from Calibre).
4. **The table of contents** (`toc`) - tells you what kind of book it is: chapters
   named for classes and spells mean a core book or options supplement; "Part 1:
   ... / Appendix: Pregenerated Characters" means an adventure.
5. **Embedded PDF metadata** (`embedded_metadata`, `xmp`). Often right for books
   from the publisher's own pipeline, often junk elsewhere. `junk_fields` lists
   values the extractor already rejected (`Untitled`, `Microsoft Word - x.doc`,
   `Layout 1`, the filename echoed back).
6. **Filename and folder path** (`filename`, `folders`) - useful clues, the least
   reliable source. Someone else's folder names are their guesses.
7. **Page geometry** (`page_size`, `pages`, `form_fields`): landscape → screen,
   cards or handout; 1-6 pages with form fields → character sheet; digest/A5 →
   indie or OSR zine; landscape `spreads_of` → a two-pages-per-sheet scan.

When sources disagree, prefer the book's own pages, and say what disagreed.

## 2. Traps

- **Purchase watermarks.** Store copies stamp the buyer's name and order number
  on every page. The extractor strips them; never copy a person's name from a
  page footer into `authors`, and never put an order number anywhere.
- **Scan-group and uploader credits** in embedded metadata ("DRO/EPC of EPC
  CREW", "Scanned by ...", "Administrator") are not authors.
- **Software in the author field** - `Adobe InDesign`, `Acrobat PDFMaker`, `Word`.
- **Excerpts, previews, samples and playtests** are not the full book. Keep the
  word in the file name and title (`Hermetic Law and Politics (Excerpt).pdf`) and
  tag them (`Preview`, `Playtest`). A bookmark list longer than the file is a
  clue.
- **Translations** keep the translated title as `title` and set `language`; the
  original title can go in `description`.
- **Collected editions / bundles**: one PDF containing several books is one book
  - title it as the collection.
- **Same title, different editions** (`Player's Handbook` exists for 1e, 2e, 3e,
  3.5e, 4e, 5e (2014), 5e (2024)): decide the edition from the evidence before
  filing - it changes the system.
- **Fan-made** content uses official names in titles. Check the legal page for a
  community-programme notice or the absence of the publisher's copyright.

## 3. The metadata fields

What `PATCH /api/books/:id` accepts, and how to fill each. Only set a field you
have evidence for.

| Field | Fill with | Notes |
|---|---|---|
| `title` | The title as printed on the title page, subtitle after ` - ` or `: ` | Title case as the publisher styles it. No edition suffix unless the book's title carries it |
| `authors` | Writers / designers, as a list | From "Written by", "Design", "Authors", "Writing". Lead designers and writers - not editors, layout, playtesters or "special thanks". Keep each name as printed |
| `artists` | Cover and interior artists, as a list | From "Cover Art", "Interior Art", "Illustrations", "Cartography". Cartographers count |
| `publisher` | The company that published it | As printed in the copyright block (`Chaosium Inc.` → `Chaosium` is fine). A licensee publishing someone else's game is the publisher |
| `year` / `month` / `day` | First publication date of *this edition* | Usually the copyright year. Month/day only if printed. Never invent precision |
| `isbn` | ISBN-10 or ISBN-13, digits only | Only checksum-valid values (the extractor validates). Print and PDF ISBNs may differ; either is fine |
| `product_code` | Publisher's stock number - `PZO2101`, `CHA23137`, `AG0256` | From the back cover/legal page, or a confident filename match |
| `version` | Version or printing - `1.2`, `2nd Printing`, `Remastered` | From the legal page or file name. Leave empty if unknown |
| `language` | The book's language, written out - `English`, `German` | Match whatever form the library already uses (check a few existing books) |
| `license` | The licence it is released under | Use the library's license list (`grimoire_api.py lookups`): `OGL 1.0a`, `ORC`, `CC-BY-4.0`, ... Only from an explicit licence text in the book. Leave empty for ordinary all-rights-reserved books |
| `genres` | One to three genres | Only values from the library's genre list (`lookups`). Genres usually live on the *system*; set them on a book only when it departs from its system's |
| `tags` | A few useful facets | Setting name, adventure level/tier, "Solo", "Pregens", series name. Not the system or category - those are already structured. Plan tags are added, never replacing the user's |
| `description` | One to three sentences on what the book is and contains | Paraphrase the book's own introduction or back-cover blurb. Never invent contents you have not seen |
| `urls` | `[{label, url}]` - the publisher's product page | Only a URL you have actually seen in the book or a lookup result. Never construct one |
| `is_explicit` | `true` for explicit content | See classification.md section 10 |
| `codex_id` | Grimoire Codex DB record id | Only from an accepted Codex DB lookup |

Never set `category` - the folder decides it, and changing it moves the file.

## 4. Confidence

Give every identification a confidence, because it decides what happens next:

- **high** - title and system confirmed by the book's own pages or cover, or by a
  lookup that matches title, system and page count. Goes into the plan as is.
- **medium** - identity clear, but edition, category or some fields inferred
  (from the filename, a folder, a TOC). Goes into the plan, called out in review.
- **low** - cannot tell what it is, or only the filename speaks. Goes to a
  `Needs Review` list - not into the library - with what you did find and what
  would settle it (a password, a better scan, the user's knowledge).

## 5. Looking it up: Grimoire Codex DB and add-ons

Once a book is in Grimoire, the server can search metadata sources for it:
Grimoire Codex DB (the community metadata database, when the server has it
configured) and any installed metadata add-ons.

```bash
grimoire_api.py sources <book-id>                      # which sources this server has
grimoire_api.py lookup <book-id> --source grimoire-codex
grimoire_api.py lookup <book-id> --source <addon-id> --query "Gradient Descent"
grimoire_api.py fetch <book-id> --source grimoire-codex --identity <candidate identity>
```

`lookup` returns ranked candidates (`label`, `score`, `identity`); `fetch` returns
one candidate's fields *diffed against the book*, changing nothing. Apply what
you accept with `patch`.

- Accept a Codex DB match when its title and system agree with the book and its
  score is high (0.9+); the label says why it matched. Below that, compare
  fields and decide; when two candidates are close, say so instead of picking.
- A Codex DB match is evidence, not authority: if it disagrees with the book's
  own legal page, the book wins, and the disagreement is worth reporting.
- Linking (`codex_id`) is the valuable part - it connects the book to the shared
  record for future updates. Set it whenever you accept a Codex DB match.
- Fill empty fields from a lookup freely; replace a field the book already has
  only when the existing value is clearly wrong (a filename-derived title, an
  `Administrator` author) or the user asked for it.
