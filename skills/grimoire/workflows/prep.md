# Prep: plan the next session of a campaign

Help a GM prepare their next session from what is already recorded in Grimoire -
the campaign's description, its wiki and session notes, and the books linked to
it - and pull supporting material from their library with book and page
references. Needs a key that can read Campaigns (and Search/Books for the
library references).

## 1. Find the campaign

```bash
G campaigns
```

Match what the user said (a word from the name is enough). If nothing or several
match, list them and ask. Archived campaigns are hidden unless asked for.

## 2. Read where things stand

```bash
G campaign <id>                 # description, system, members, linked books and resources
G wiki <id>                     # the wiki outline: pages, session pages, nesting
G wiki <id> <page-id>           # a page in full
G wiki-search <id> "<term>"     # find pages about an NPC, place or thread
```

Read the most recent session pages (`page_type`/`session_date` in the outline)
and anything they link to - NPCs, places, factions, open threads. Only GM-visible
pages are returned if the key's owner is the GM; never surface a page the key
cannot see, and keep GM-only material clearly labelled as such in your answer so
it does not end up in something shared with players.

## 3. Ask what the GM wants

Before writing a plan, ask briefly: which session is next, how long it runs,
what they want from it (a fight, a reveal, wrapping up a thread), and anything
the players said they would do. Skip what the notes already answer.

## 4. Build the prep

A useful default, adjusted to what they asked for:

- **Where we left off** - two or three lines from the last session's notes.
- **Threads in play** - open hooks and what each faction or NPC wants now.
- **Likely scenes** - three to five, each with its purpose, who is there, and
  what could go wrong; not a script.
- **NPCs** - names, wants, a line of voice; existing NPCs from the wiki first.
- **Rules and stats to have at hand** - from their books, found with
  `G search` / `G pages` (as in the ask workflow), each cited *(Book, p. N)*:
  monster stat blocks, the subsystem a scene will lean on, a table to roll on.
- **Loose ends** - things in the notes that contradict each other or were
  never resolved.

Stay inside what the campaign has established; mark invented material as
suggestion.

## 5. Writing it down

Do not write into the campaign unless the GM asks. If they want the plan saved,
offer it as text to paste into a new wiki page; the REST client does not create
wiki pages. With the Grimoire MCP server connected, `create_wiki_page` adds a new
page (private to the user by default) without touching existing ones.

If the Grimoire MCP server is connected, `list_campaigns`, `get_campaign`,
`read_wiki_page` and `search_library` do the same reading as the `G` commands.
