# Enrich metadata for books already in Grimoire

For libraries that are on the shelves but thinly described: titles like
`cbrpnk 02 runner file lowink letter`, no authors, no year, no Codex DB link.
This reads each book through the Grimoire API, works out what it is, and
proposes metadata for the user to approve. It changes metadata only - for
moving books between shelves, hand off to the organize workflow (`workflows/organize.md`).

`references/metadata-fields.md` defines what belongs in each field, and
`references/classification.md` is the yardstick for misfiled books.

## 1. Connect

A GM or admin key with *Read and write* on **Books** and *Read* on **Systems**
and **Lookups** is enough - metadata lookups, Codex DB included, run through the
Books permission. `G check` confirms it; if it is not connected, run the setup
workflow first.

## 2. Choose the books

Agree the scope with the user - one system, one category, books missing certain
fields, or everything:

```bash
G systems                                   # find a system's id
G books --system <id> --missing authors publisher year
G books --category adventure --missing title description
```

`--missing` fetches every book's details, so it is slow on thousands of books -
narrow by system first. A title counts as "missing" in spirit when it is the
file name with underscores turned into spaces; look for those in the list too.

## 3. Read each book

The book's own pages are the evidence. Through the API:

```bash
G book <id>                     # current metadata, path, page count
G toc <id>                      # bookmarks
G page-text <id> 1              # title page; also 2-6 for credits/legal
G thumbnail <id> work/<id>.webp # the cover - look at it
G page-image <id> 2 work/<id>-p2.webp   # when a page has no text layer
```

Read the first page or two and the credits/copyright page (usually 2-4, or the
last pages); that is normally enough for title, authors, artists, publisher,
year, ISBN and product code. Scans without a text layer may already be OCRed
by Grimoire - if `page-text` is empty, look at the page image instead.

For a large batch with the library on local disk (or after `G
download <id> <file>`), `<skill-dir>/scripts/extract_evidence.py` pulls all of
this out of many files at once.

## 4. Look it up

```bash
G sources <id>                                   # Codex DB and add-ons available
G lookup <id> --source grimoire-codex            # ranked candidates
G fetch <id> --source grimoire-codex --identity <identity>   # diff vs the book
```

Accept a match when title and system agree with what the book's pages say
(Codex DB scores of 0.9+ usually do); compare fields when the score is lower,
and say so when two candidates are close. The book's own legal page outranks a
lookup when they disagree. Always include `codex_id` for an accepted Codex DB
match - the link is what keeps the book connected to the shared record.

## 5. Propose, then apply

Build one table per batch - book, field, current value, proposed value, source
of the evidence - and show it to the user. Rules for proposals:

- **Fill empty fields freely** when there is evidence.
- **Replace a non-empty value only when it is clearly wrong**: a file-name title,
  `Administrator` or `Adobe InDesign` as author, a year that contradicts the
  copyright page. Show the old value beside the new one.
- **Never touch** `category` (that moves the file) or `access_level`, and leave
  tags the user set alone - new tags are added, not swapped.
- Values only from evidence: no constructed URLs, no guessed ISBNs, no
  descriptions of content you have not read.

After approval, apply each book's changes:

```bash
G patch <id> '{"title": "...", "authors": ["..."], "year": 2019, "codex_id": "..."}'
G patch <id> @work/<id>.json     # or from a file
```

`patch` drops `category` if it is included by mistake. For many books, write one
JSON file per book and loop over them; report any that fail.

## 6. Misfiled books and damaged files

While reading, note books that are on the wrong shelf - a supplement in `Core`,
a 2e book under the 5e system, a character sheet filed as an adventure, a
duplicate of another book. Do not move them here; list them with the proposed
destination and offer to hand the list to the organize workflow (`workflows/organize.md`) as a
library-mode plan (`action: "move"`), which keeps each book's record, tags and
bookmarks.

A book whose pages fail to render, are blank, or stop short of its page count
may be damaged: download it and run the health workflow (`workflows/health.md`) on it, then
tag it (`G tag <id> --tags "Health: missing pages"`) so the user
can find it to replace.

## 7. Report

Summarise: books updated (and how many fields), Codex DB links made, matches
declined or ambiguous, books still unidentified, and the misfiled/damaged lists.
