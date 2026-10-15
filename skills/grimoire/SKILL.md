---
name: grimoire
description: Work with a self-hosted Grimoire TTRPG library - connect to it (browser sign-in or API key), organise and import piles of unsorted RPG PDFs into it, find corrupt or incomplete books, identify unlabelled books and file them by game system and category, fill in and fix book metadata (including Grimoire Codex DB links), answer rules and lore questions from the user's own books with page citations, and prep the next session of a campaign from its notes and wiki. Use whenever the user mentions Grimoire or their RPG library, wants RPG books sorted, checked, identified, imported or described, asks a rules question they want answered from their books, or wants help preparing a game session.
argument-hint: "[setup | organize <folder> | health <folder> | identify <files> | enrich [system] | ask <question> | prep [campaign] | status]"
---

# Grimoire

One entry point for everything an assistant can do with a Grimoire library.
Each job is a workflow in `workflows/`; this file picks the right one, makes
sure there is a connection, and holds the rules every workflow shares.

`<skill-dir>` is the folder this SKILL.md is in. `G` below means
`python3 <skill-dir>/scripts/grimoire_api.py` - the bundled command-line client
(Python 3.9+, standard library only).

## 1. Pick the workflow

Match the user's request, or the first word after `/grimoire`, and read that
workflow file before doing anything else:

| Request | Workflow |
|---|---|
| `setup`, `login`, connect to a library, add another library | `workflows/setup.md` |
| `organize` / `import` / sort / clean up a folder of books | `workflows/organize.md` |
| `health` / check for broken, corrupt or incomplete PDFs | `workflows/health.md` |
| `identify` / "what is this book" / where should this go | `workflows/identify.md` |
| `enrich` / fix or fill in metadata for books already in Grimoire | `workflows/enrich.md` |
| `ask` / a rules or lore question to answer from their books | `workflows/ask.md` |
| `prep` / plan or prepare the next session of a campaign | `workflows/prep.md` |
| `status`, or `/grimoire` with nothing after it | Run `G check` and `G profiles`, say which library is connected, and list the workflows above in a sentence each |

If a request spans several (e.g. "import this folder, then link it all to
Codex DB"), run them in order. If it is ambiguous, ask which one they mean.

## 2. Make sure there is a connection

Every workflow except `health` and `identify` on local files needs a Grimoire
server. Run `G check` first:

- It answers with `can_read` results → connected. Note which `profile` is in use.
- It says "not connected" → follow `workflows/setup.md`, then come back.
- Several saved libraries (`G profiles`) and the request doesn't say which →
  ask, then pass `--profile <name>` to every command.

Never ask the user to paste an API key into the chat. `G login` gets one
through their browser, or reads it from their own terminal (setup workflow).

## 3. Read the library notes

```bash
G notes
```

Each saved library has a notes file (`~/.config/grimoire/libraries/<profile>.md`)
holding what has been learned about that library and what the user wants:
system naming, category folder spellings, where community content goes, how
languages are marked, tags they use, things they asked never to do. **The notes
override the defaults in `references/`** - they are how one user's /grimoire
behaves differently from another's without anyone editing this skill.

Update the notes when you learn something durable: a convention discovered in
setup, a correction the user makes ("community stuff goes in `3rd Party`, not
Homebrew"), a preference they state. Tell the user in one line when you add
something. Keep it short Markdown with headings `## Conventions`,
`## Preferences`, `## History` (one line per import or cleanup, with the date).

## 4. Rules every workflow follows

- **Their files are theirs.** A folder being imported is only ever read.
  Grimoire is changed only after the user approves a plan, nothing is overwritten
  or deleted, and name clashes are questions, not things to resolve.
- **Evidence, not guesses.** Metadata comes from the book's own pages, its cover,
  or a lookup - a field without evidence stays empty. Answers to rules questions
  come from the user's books with book and page, or say plainly that the books
  don't cover it.
- **Say what you're unsure of.** Every identification carries a confidence;
  every quarantined file a reason.
- **Respect visibility.** The key sees only what its owner may see. Do not try to
  work around a 403 or a hidden book; say what access is missing.
- **Purchase watermarks stay private.** Never copy a buyer's name, email or
  order number from a page into metadata, notes or chat.

## The pieces

| Path | What it is |
|---|---|
| `scripts/grimoire_api.py` | Client: login and saved libraries, browsing, uploads and moves, metadata, lookups, search, campaigns, plan apply |
| `scripts/pdf_health.py` | Health checker for PDFs and e-books |
| `scripts/extract_evidence.py` | Pulls identification evidence (metadata, title/credits/legal pages, codes, ISBNs, covers) out of files |
| `scripts/inventory.py` | Sorts a pile of files into books, media, archives, junk and unsupported formats |
| `references/classification.md` | Where things go: systems, editions, categories, containers, groups, file names |
| `references/metadata-fields.md` | How to identify a book and fill each metadata field; lookups |
| `references/plan-format.md` | The organise plan file and how `G apply` executes it |

If the user has the Grimoire MCP server connected (tools such as
`search_library`, `read_pages`, `get_campaign`), the `ask` and `prep` workflows
can use those tools instead of `G` - same rules, same citations.
