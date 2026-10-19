# Ask: answer from the user's own books

Rules and lore questions answered from the books in their Grimoire library, with
the book and page for every claim - not from memory. Works for any role, with a
key that can read Search and Books.

## For each question

1. **Search.** `G search "<terms>"`, scoped when the context makes the game clear
   (`--system <id>`; find ids with `G systems`). Full-text search matches words,
   so if the first search misses, try the game's own vocabulary and synonyms
   ("grapple", "grab", "restrained"; "sanity", "SAN") and `title:`/`tag:` filters.
   `results` are page hits with snippets; `book_matches` are whole books whose
   metadata matched.
2. **Read the pages in full.** Snippets are fragments. `G pages <book-id> <page>
   [<last-page>]` reads up to ten pages; read the page before and after when a
   rule runs across pages, and follow "see page N" references.
3. **Answer with citations.** Quote or closely paraphrase the rule, each piece
   followed by *(Book Title, p. N)*. Use the page number Grimoire reports; it is
   the PDF page, which can differ from the printed number - mention that when
   the printed number is visible and different.
4. **Be honest about coverage.** If their books don't cover it, say so, and say
   what you searched. If books disagree (core vs. errata, two editions), show
   both and say which is newer. Only add general knowledge when they ask, and mark
   it clearly as not from their books.

Respect the edition: if the user's question is about one system, do not answer
from another system's book, however similar.

## Keep going

After answering, stay in this mode for follow-up questions until the user moves
on. When a question is about a specific campaign, `G campaigns` and the prep
workflow's commands can bring in house rules from the campaign wiki - cite those
as the wiki page, not a book.

If the Grimoire MCP server is connected, `search_library` and `read_pages` do the
same job as `G search` and `G pages`.
